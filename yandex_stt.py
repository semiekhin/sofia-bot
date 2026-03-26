"""
yandex_stt.py — Yandex SpeechKit STT v3 streaming процессор для Pipecat

gRPC streaming: stt.api.cloud.yandex.net:443
Авторизация: Api-Key в gRPC metadata
Формат: PCM 16kHz 16-bit mono (от DailyTransport)
"""

import asyncio
import sys
from typing import AsyncGenerator

import grpc
from loguru import logger

# Proto path
sys.path.insert(0, "/opt/sofia-gpt-dev/yandex_proto")
from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import STTService
from pipecat.utils.time import time_now_iso8601

YANDEX_STT_ENDPOINT = "stt.api.cloud.yandex.net:443"


class YandexSTTService(STTService):
    """Yandex SpeechKit STT v3 gRPC streaming для Pipecat.

    Принимает аудио-чанки, стримит в Yandex, пушит partial/final транскрипции.
    """

    def __init__(self, *, api_key: str, language: str = "ru-RU", model: str = "general:rc", **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key
        self._language = language
        self._model = model
        self._channel: grpc.aio.Channel | None = None
        self._stub: stt_service_pb2_grpc.RecognizerStub | None = None
        self._stream = None
        self._audio_queue: asyncio.Queue | None = None
        self._receive_task: asyncio.Task | None = None
        self._connected = False

    async def start(self, frame):
        await super().start(frame)
        await self._connect()

    async def stop(self, frame):
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame):
        await super().cancel(frame)
        await self._disconnect()

    async def _connect(self):
        """Устанавливает gRPC канал и запускает streaming."""
        try:
            creds = grpc.ssl_channel_credentials()
            self._channel = grpc.aio.secure_channel(YANDEX_STT_ENDPOINT, creds)
            self._stub = stt_service_pb2_grpc.RecognizerStub(self._channel)
            self._audio_queue = asyncio.Queue()

            # Запускаем bidirectional stream
            metadata = [("authorization", f"Api-Key {self._api_key}")]
            self._stream = self._stub.RecognizeStreaming(
                self._request_iterator(),
                metadata=metadata,
            )
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_responses())
            logger.info(f"{self}: Connected to Yandex STT")
        except Exception as e:
            logger.error(f"{self}: Failed to connect to Yandex STT: {e}")
            self._connected = False

    async def _disconnect(self):
        """Закрывает gRPC соединение."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None
        if self._audio_queue:
            await self._audio_queue.put(None)  # Signal iterator to stop
        if self._channel:
            await self._channel.close()
            self._channel = None
        self._stream = None
        logger.info(f"{self}: Disconnected from Yandex STT")

    async def _request_iterator(self):
        """Генератор запросов: сначала конфиг, потом аудио-чанки."""
        # Первый запрос — настройки сессии
        session_options = stt_pb2.StreamingOptions(
            recognition_model=stt_pb2.RecognitionModelOptions(
                model=self._model,
                audio_format=stt_pb2.AudioFormatOptions(
                    raw_audio=stt_pb2.RawAudio(
                        audio_encoding=stt_pb2.RawAudio.LINEAR16_PCM,
                        sample_rate_hertz=16000,
                        audio_channel_count=1,
                    )
                ),
                language_restriction=stt_pb2.LanguageRestrictionOptions(
                    restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                    language_code=[self._language],
                ),
                audio_processing_type=stt_pb2.RecognitionModelOptions.REAL_TIME,
            ),
        )
        yield stt_pb2.StreamingRequest(session_options=session_options)

        # Потом бесконечно аудио-чанки
        while True:
            audio_data = await self._audio_queue.get()
            if audio_data is None:
                break
            yield stt_pb2.StreamingRequest(
                chunk=stt_pb2.AudioChunk(data=audio_data)
            )

    async def _receive_responses(self):
        """Получает транскрипции из gRPC stream и пушит фреймы."""
        try:
            async for response in self._stream:
                # Partial result
                if response.HasField("partial"):
                    alternatives = response.partial.alternatives
                    if alternatives and alternatives[0].text:
                        text = alternatives[0].text
                        await self.push_frame(
                            InterimTranscriptionFrame(
                                text=text,
                                user_id=self._user_id if hasattr(self, "_user_id") else "",
                                timestamp=time_now_iso8601(),
                            )
                        )

                # Final result
                elif response.HasField("final"):
                    alternatives = response.final.alternatives
                    if alternatives and alternatives[0].text:
                        text = alternatives[0].text
                        logger.info(f"{self}: Final transcription: [{text}]")
                        await self.push_frame(
                            TranscriptionFrame(
                                text=text,
                                user_id=self._user_id if hasattr(self, "_user_id") else "",
                                timestamp=time_now_iso8601(),
                            )
                        )

                # Final refinement (higher quality version of final)
                elif response.HasField("final_refinement"):
                    alternatives = response.final_refinement.normalized_text.alternatives
                    if alternatives and alternatives[0].text:
                        text = alternatives[0].text
                        logger.debug(f"{self}: Refined transcription: [{text}]")

        except grpc.aio.AioRpcError as e:
            if e.code() != grpc.StatusCode.CANCELLED:
                logger.error(f"{self}: gRPC error: {e.code()} {e.details()}")
                # Reconnect
                await self._reconnect()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"{self}: Receive error: {e}")

    async def _reconnect(self):
        """Переподключение при ошибке."""
        logger.info(f"{self}: Reconnecting...")
        await self._disconnect()
        await asyncio.sleep(0.5)
        await self._connect()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Отправляет аудио-чанк в gRPC stream."""
        if self._connected and self._audio_queue:
            await self._audio_queue.put(audio)
        yield None  # Транскрипции приходят через _receive_responses
