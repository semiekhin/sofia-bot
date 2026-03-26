"""
voice_pipecat_daily.py — Голосовой бот Sofia v2 на Pipecat + Daily
Daily WebRTC + OpenAI STT (Whisper) + gpt-4.1-mini + ElevenLabs TTS

Запуск: python3 voice_pipecat_daily.py
Порт: 8083
"""

import asyncio
import os

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transports.daily.utils import DailyRESTHelper, DailyRoomParams

load_dotenv()

# ============================================================
# Конфигурация
# ============================================================

VOICE_SYSTEM_PROMPT = """Ты — София, AI-ассистент компании Oazis Estate по недвижимости в курортных регионах России.

ТВОЯ ЗАДАЧА: квалифицировать клиента — узнать цель, бюджет, предпочтения по локации и предложить созвон с экспертом.

ФОРМАТ ОТВЕТОВ (ты разговариваешь ГОЛОСОМ по телефону):
- Отвечай 1-2 предложениями максимум
- Используй разговорный русский, короткие фразы
- Никаких списков, буллетов, markdown, ссылок, URL
- Не перечисляй больше 2 вариантов за раз

ПРАВИЛА ДИАЛОГА:
- Если клиент задаёт прямой вопрос — СНАЧАЛА ответь конкретно, потом можешь уточнить
- Если клиент говорит "не знаю", "покажите что есть", "сами подскажите" — НЕ переспрашивай. Предложи конкретный вариант: "Например, у моря в Сочи от 8 млн с доходностью до 15% годовых. Интересно?"
- НИКОГДА не задавай один и тот же вопрос дважды
- Не повторяй одни и те же фразы-филлеры
- Подтверждай что услышал: "Понял, значит вас интересует..."

ЧТО ЗНАЕШЬ:
- Направления: Сочи (от 8 млн), Туапсе (от 5 млн), Геленджик (от 7 млн), горные курорты (от 9 млн)
- Форматы: квартиры, апартаменты, таунхаусы
- Оплата: 100%, рассрочка, ипотека
- Доходность аренды: 10-18% годовых в зависимости от локации и формата

СЦЕНАРИЙ:
1. Поздоровайся, представься, спроси удобно ли говорить
2. Узнай цель: для себя, инвестиция, или и то и другое
3. Узнай бюджет (если не знает — предложи диапазоны)
4. Узнай предпочтения по локации (море/горы)
5. Предложи созвон с экспертом: "Давайте наш эксперт подберёт 2-3 лучших варианта под ваш запрос. Когда удобно созвониться?"

Если клиент дважды отказался от созвона — не настаивай, предложи отправить подборку в мессенджер."""

ELEVENLABS_VOICE_ID = "FZGeNF7bE3syeQOynDKC"  # Victoria — Engaging and Expressive, ru
ELEVENLABS_MODEL = "eleven_multilingual_v2"


# ============================================================
# Bot pipeline
# ============================================================


async def run_bot(room_url: str, token: str):
    """Создаёт и запускает pipeline для одного клиента."""
    logger.info(f"Starting bot in room: {room_url}")

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
                    stop_secs=0.8,
                )
            ),
        ),
    )

    # STT: OpenAI Whisper (временно, потом Yandex SpeechKit)
    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAISTTService.Settings(
            model="gpt-4o-mini-transcribe",
            language="ru",
        ),
    )

    # LLM: gpt-4.1-mini
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model="gpt-4.1-mini",
            max_completion_tokens=800,
        ),
    )

    # TTS: ElevenLabs
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(
            voice=ELEVENLABS_VOICE_ID,
            model=ELEVENLABS_MODEL,
        ),
        sample_rate=24000,
    )

    # Context + aggregators
    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": VOICE_SYSTEM_PROMPT,
            }
        ]
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(),
    )

    # Pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
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

    # Когда клиент подключился — София здоровается
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected: {client}")
        context.add_message(
            {"role": "user", "content": "[Клиент подключился к голосовому чату]"}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected: {client}")
        await task.cancel()

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

        # Создаём комнату
        import time

        room = await rest.create_room(
            DailyRoomParams(
                properties={
                    "exp": int(time.time()) + 3600,  # 1 час
                    "enable_chat": False,
                }
            )
        )
        logger.info(f"Room created: {room.url}")

        # Получаём токен для бота
        token = await rest.get_token(room.url, expiry_time=3600)

        logger.info(f"Bot token obtained")
        logger.info(f"")
        logger.info(f"========================================")
        logger.info(f"  ТЕСТ: откройте в браузере:")
        logger.info(f"  {room.url}")
        logger.info(f"========================================")
        logger.info(f"")

        # Запускаем бот
        await run_bot(room.url, token)


if __name__ == "__main__":
    asyncio.run(main())
