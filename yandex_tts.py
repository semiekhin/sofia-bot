"""
yandex_tts.py — Yandex SpeechKit TTS процессор для Pipecat

REST API v1: https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize
Формат: lpcm 48000Hz (pipecat ресемплирует в 24000Hz для Daily)
Лимит: 250 символов на запрос → chunking по клаузам
"""

import re
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

import aiohttp
from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService


# Yandex REST API v1 поддерживает только 8000, 16000, 48000
YANDEX_SAMPLE_RATE = 48000
YANDEX_MAX_CHARS = 250
YANDEX_TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

# Паттерн разбивки: предложения и клаузы
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?;—])\s+|(?<=,)\s+")


def _split_text(text: str, max_chars: int = YANDEX_MAX_CHARS) -> list[str]:
    """Разбивает текст на куски ≤ max_chars по границам клауз."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    for part in _CLAUSE_SPLIT.split(text):
        if not part:
            continue
        if len(current) + len(part) + 1 <= max_chars:
            current = f"{current} {part}".strip() if current else part
        else:
            if current:
                chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks


@dataclass
class YandexTTSSettings(TTSSettings):
    voice: str = "marina"
    lang: str = "ru-RU"
    speed: float = 1.0
    emotion: Optional[str] = None


class YandexTTSService(TTSService):
    """Yandex SpeechKit TTS v1 REST API для Pipecat."""

    Settings = YandexTTSSettings
    _settings: YandexTTSSettings

    def __init__(
        self,
        *,
        api_key: str,
        settings: Optional[Settings] = None,
        **kwargs,
    ):
        super().__init__(
            sample_rate=YANDEX_SAMPLE_RATE,
            push_start_frame=True,
            settings=settings or self.Settings(),
            **kwargs,
        )
        self._api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self, frame):
        await super().start(frame)
        self._session = aiohttp.ClientSession()

    async def stop(self, frame):
        await super().stop(frame)
        if self._session:
            await self._session.close()
            self._session = None

    async def cancel(self, frame):
        await super().cancel(frame)
        if self._session:
            await self._session.close()
            self._session = None

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"{self}: Generating TTS [{text}]")

        chunks = _split_text(text)
        await self.start_tts_usage_metrics(text)
        first_byte = True

        for chunk_text in chunks:
            data = {
                "text": chunk_text,
                "lang": self._settings.lang,
                "voice": self._settings.voice,
                "format": "lpcm",
                "sampleRateHertz": str(YANDEX_SAMPLE_RATE),
                "speed": str(self._settings.speed),
            }
            if self._settings.emotion:
                data["emotion"] = self._settings.emotion

            try:
                async with self._session.post(
                    YANDEX_TTS_URL,
                    headers={"Authorization": f"Api-Key {self._api_key}"},
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"{self}: Yandex TTS error {resp.status}: {error_text}")
                        yield ErrorFrame(error=f"Yandex TTS error {resp.status}: {error_text}")
                        return

                    # Читаем весь ответ и отдаём выровненными чанками (2 байта = 1 сэмпл)
                    pcm_data = await resp.read()
                    if first_byte:
                        await self.stop_ttfb_metrics()
                        first_byte = False

                    # Обрезаем до чётного числа байт
                    if len(pcm_data) % 2 != 0:
                        pcm_data = pcm_data[:-1]

                    CHUNK_SIZE = self.chunk_size
                    # chunk_size уже чётный, но на всякий случай
                    CHUNK_SIZE = CHUNK_SIZE - (CHUNK_SIZE % 2)
                    for i in range(0, len(pcm_data), CHUNK_SIZE):
                        chunk = pcm_data[i : i + CHUNK_SIZE]
                        if chunk:
                            yield TTSAudioRawFrame(
                                audio=chunk,
                                sample_rate=YANDEX_SAMPLE_RATE,
                                num_channels=1,
                                context_id=context_id,
                            )
            except Exception as e:
                logger.error(f"{self}: Yandex TTS exception: {type(e).__name__}: {e}")
                yield ErrorFrame(error=f"Yandex TTS error: {type(e).__name__}: {e}")
                return
