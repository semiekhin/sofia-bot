"""
voice_pipecat_daily.py — Голосовой бот Sofia v2 на Pipecat + Daily
Daily WebRTC + OpenAI Whisper STT + core/pipeline.py (Sofia) + Yandex TTS

Запуск: python3 voice_pipecat_daily.py
Порт: 8083
"""

import asyncio
import hashlib
import os
import re
import time as _time

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    LLMContextFrame,
    LLMRunFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.openai.stt import OpenAISTTService
from yandex_tts import YandexTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transports.daily.utils import DailyRESTHelper, DailyRoomParams

# Sofia pipeline imports
from state_manager import StateManager
from core.pipeline import stream_voice_response
from web_api import save_message, get_history

load_dotenv()

SOFIA_PATH = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(SOFIA_PATH, "sofia_gpt_dev.db"))
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(SOFIA_PATH, DB_PATH)

VOICE_USER_ID_OFFSET = 8_000_000

# Dummy system prompt — user_aggregator requires LLMContext with system message.
# Actual prompt lives in core/pipeline.py (sofia_prompt_v2.py).
VOICE_SYSTEM_PROMPT = "Ты — София, голосовой консультант по недвижимости."


def room_url_to_user_id(room_url: str) -> int:
    h = hashlib.md5(room_url.encode()).hexdigest()[:8]
    return VOICE_USER_ID_OFFSET + (int(h, 16) % 1_000_000)


def sanitize_for_tts(text: str) -> str:
    """Убирает латиницу, URL, email — чтобы TTS не спотыкался."""
    text = text.replace("Oazis Estate", "Оазис Эстэйт")
    text = text.replace("oazis estate", "Оазис Эстэйт")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\S+@\S+\.\S+", "", text)
    text = re.sub(r"\S+\.ru\b", "", text)
    text = text.replace("@oazis_expert", "наш эксперт")
    text = re.sub(r"@\w+", "", text)
    # Убираем двойные пробелы после удалений
    text = re.sub(r"  +", " ", text).strip()
    return text


# ============================================================
# SofiaPipelineProcessor — замена OpenAILLMService
# ============================================================


class SofiaPipelineProcessor(FrameProcessor):
    """Заменяет OpenAILLMService — вызывает core/pipeline.py.

    Получает LLMRunFrame от user_aggregator (turn complete).
    Читает последнее сообщение из LLMContext.
    Вызывает stream_voice_response() — полный промпт, RAG, Extractor.
    Буферизует ответ и пушит TTSSpeakFrame.
    """

    def __init__(self, *, context: LLMContext, user_id: int, state_manager: StateManager):
        super().__init__()
        self._context = context
        self._user_id = user_id
        self._chat_id = str(user_id)
        self._user_name = "Voice Client"
        self._state_manager = state_manager

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame):
            # user_aggregator пушит LLMContextFrame когда turn завершён
            await self._handle_turn()
        elif isinstance(frame, LLMRunFrame):
            # on_client_connected пушит LLMRunFrame для приветствия
            await self._handle_turn()
        else:
            await self.push_frame(frame, direction)

    async def _handle_turn(self):
        """Обрабатывает завершённый ход: pipeline → TTS."""
        # Читаем последнее user сообщение из LLMContext
        user_text = None
        for msg in reversed(self._context.messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        if not user_text:
            return

        logger.info(f"🎤 CLIENT SAID: \"{user_text}\"")

        # Сохраняем в БД
        save_message(self._chat_id, self._user_id, self._user_name, "user", user_text)

        # История из БД (не из LLMContext — pipeline управляет своим контекстом)
        history = get_history(self._chat_id)

        # Вызываем Sofia pipeline
        t0 = _time.time()
        full_response = ""
        try:
            async for chunk in stream_voice_response(
                user_id=self._user_id,
                user_message=user_text,
                user_name=self._user_name,
                history=history,
                state_manager=self._state_manager,
                channel="voice_v2",
            ):
                if chunk:
                    full_response += chunk
        except Exception as e:
            logger.error(f"❌ Pipeline error: {e}")
            full_response = "Простите, связь подвисла. Повторите?"

        elapsed = (_time.time() - t0) * 1000
        logger.info(f"🧠 PIPELINE COMPLETE: \"{full_response}\" ({elapsed:.0f}ms)")

        # Убираем [END] и латиницу из озвучки
        tts_text = full_response.replace("[END]", "").replace("[end]", "").strip()
        tts_text = sanitize_for_tts(tts_text)

        if tts_text:
            # Сохраняем ответ в БД
            save_message(self._chat_id, self._user_id, self._user_name, "assistant", full_response)

            # Обновляем LLMContext (для turn detection на следующем ходу)
            self._context.add_message({"role": "assistant", "content": full_response})

            # Отправляем в TTS целиком
            logger.info(f"🔊 TTS INPUT: \"{tts_text}\"")
            await self.push_frame(TTSSpeakFrame(text=tts_text))


# ============================================================
# Bot pipeline
# ============================================================


async def run_bot(room_url: str, token: str):
    """Создаёт и запускает pipeline для одного клиента."""
    user_id = room_url_to_user_id(room_url)
    chat_id = str(user_id)
    state_manager = StateManager(DB_PATH)

    logger.info(f"Starting bot in room: {room_url}, user_id: {user_id}")

    transport = DailyTransport(
        room_url=room_url,
        token=token,
        bot_name="Sofia",
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    min_volume=0.4,
                    start_secs=0.2,
                    stop_secs=0.3,
                )
            ),
        ),
    )

    # STT: OpenAI Whisper
    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAISTTService.Settings(
            model="gpt-4o-mini-transcribe",
            language="ru",
        ),
    )

    # TTS: Yandex SpeechKit — alena neutral
    tts = YandexTTSService(
        api_key=os.getenv("YANDEX_SPEECHKIT_API_KEY"),
        settings=YandexTTSService.Settings(
            voice="alena",
            emotion="neutral",
        ),
    )

    # LLMContext — нужен для user_aggregator (turn detection).
    # Реальный промпт живёт в core/pipeline.py.
    context = LLMContext(
        messages=[{"role": "system", "content": VOICE_SYSTEM_PROMPT}]
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(),
    )

    # Sofia pipeline processor (замена OpenAILLMService + LLMFullResponseBuffer)
    sofia = SofiaPipelineProcessor(
        context=context,
        user_id=user_id,
        state_manager=state_manager,
    )

    # Pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            sofia,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Когда клиент подключился — приветствие через pipeline
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected: {client['id']}")
        context.add_message(
            {"role": "user", "content": "[Клиент подключился к голосовому чату]"}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected: {client['id']}")
        await task.cancel()

    logger.info(f"📋 Pipeline: Whisper STT → core/pipeline.py (Sofia) → Yandex TTS alena")
    logger.info(f"📋 DB: {DB_PATH}, user_id: {user_id}")

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


# ============================================================
# Main
# ============================================================


async def main():
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise Exception("DAILY_API_KEY not set in .env")

    async with aiohttp.ClientSession() as session:
        rest = DailyRESTHelper(
            daily_api_key=daily_api_key,
            daily_api_url="https://api.daily.co/v1",
            aiohttp_session=session,
        )

        import time

        room = await rest.create_room(
            DailyRoomParams(
                properties={
                    "exp": int(time.time()) + 3600,
                    "enable_chat": False,
                }
            )
        )
        logger.info(f"Room created: {room.url}")

        token = await rest.get_token(room.url, expiry_time=3600)

        logger.info(f"")
        logger.info(f"========================================")
        logger.info(f"  ТЕСТ: откройте в браузере:")
        logger.info(f"  {room.url}")
        logger.info(f"========================================")
        logger.info(f"")

        await run_bot(room.url, token)


if __name__ == "__main__":
    asyncio.run(main())
