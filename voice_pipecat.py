"""
voice_pipecat.py — Голосовой бот Sofia v2 на Pipecat
SmallWebRTC + OpenAI STT (Whisper) + gpt-4.1-mini + ElevenLabs TTS

Запуск: python3 voice_pipecat.py
Порт: 8082
Клиент: http://72.56.64.91:8082/client
"""

import asyncio
import os
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from uvicorn import Config, Server

from pipecat.audio.vad.silero import SileroVADAnalyzer
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
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

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

ELEVENLABS_VOICE_ID = "YjESejviApN7SHrbfnA2"  # Nastya
ELEVENLABS_MODEL = "eleven_flash_v2_5"

PORT = 8082

# ============================================================
# FastAPI app
# ============================================================

app = FastAPI(title="Sofia Voice Bot v2 (Pipecat)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prebuilt WebRTC frontend
try:
    from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

    app.mount("/client", SmallWebRTCPrebuiltUI, name="client")
    logger.info("Prebuilt WebRTC UI mounted at /client")
except (ImportError, RuntimeError) as e:
    logger.warning(f"Prebuilt WebRTC UI unavailable: {e}")

# SmallWebRTC request handler
webrtc_handler = SmallWebRTCRequestHandler(
    ice_servers=[{"urls": ["stun:stun.l.google.com:19302"]}],
)


# ============================================================
# Pipeline factory — создаёт pipeline для каждого подключения
# ============================================================


async def run_bot(webrtc_connection: SmallWebRTCConnection):
    """Создаёт и запускает pipeline для одного клиента."""
    logger.info(f"New client connected: {webrtc_connection.pc_id}")

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                params=SileroVADAnalyzer.VADParams(
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

    # TTS: ElevenLabs Nastya
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(
            voice=ELEVENLABS_VOICE_ID,
            model=ELEVENLABS_MODEL,
            language="ru",
            stability=0.5,
            similarity_boost=0.75,
            speed=1.0,
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

    # Pipeline: audio in → STT → context → LLM → TTS → audio out
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
        logger.info("Client connected, sending greeting")
        from pipecat.frames.frames import LLMRunFrame

        context.add_message(
            {"role": "user", "content": "[Клиент подключился к голосовому чату]"}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


# ============================================================
# API endpoints
# ============================================================


@app.post("/api/offer")
async def offer(request: dict, background_tasks: BackgroundTasks):
    """WebRTC SDP offer endpoint."""
    try:
        webrtc_request = SmallWebRTCRequest.from_dict(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    answer = await webrtc_handler.handle_web_request(
        webrtc_request,
        run_bot,
    )

    if answer is None:
        raise HTTPException(status_code=500, detail="Failed to create WebRTC answer")

    return JSONResponse(content=answer)


@app.post("/api/offer/patch")
async def offer_patch(request: dict):
    """ICE candidate patch endpoint."""
    from pipecat.transports.smallwebrtc.request_handler import (
        IceCandidate,
        SmallWebRTCPatchRequest,
    )

    try:
        patch = SmallWebRTCPatchRequest(
            pc_id=request["pc_id"],
            candidates=[IceCandidate(**c) for c in request.get("candidates", [])],
        )
        await webrtc_handler.handle_patch_request(patch)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "sofia-voice-v2-pipecat", "port": PORT}


# ============================================================
# Main
# ============================================================


async def main():
    config = Config(app=app, host="0.0.0.0", port=PORT, log_level="info")
    server = Server(config)
    logger.info(f"Sofia Voice Bot v2 starting on port {PORT}")
    logger.info(f"Open http://72.56.64.91:{PORT}/client to test")
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
