"""
yandex_stt_grpc.py — Yandex SpeechKit STT v3 gRPC streaming, callback-based.

Standalone (no Pipecat). One instance = one call-scoped stream.
Auth via Api-Key metadata (YANDEX_SPEECHKIT_API_KEY from .env).
Audio: LINEAR16_PCM, 8000 Hz mono (AudioSocket native). Language: ru-RU.

Callback signatures (async):
  on_partial(text: str, time_ms: int)
  on_final(text: str, time_ms: int)
  on_eou(time_ms: int)

Error handling:
  No auto-reconnect. On stream error → self._broken = True (unless we
  initiated close ourselves — then normal CANCELLED is expected and
  not a failure). Caller polls .is_broken and falls back to REST for
  subsequent turns. Fallback logic lives in voice_asterisk.py (Phase 2B).
"""

import asyncio
import os
import sys
import time
from typing import Awaitable, Callable, Optional

import grpc
from loguru import logger

_PROTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yandex_proto")
if _PROTO_DIR not in sys.path:
    sys.path.insert(0, _PROTO_DIR)
from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc  # noqa: E402

YANDEX_STT_ENDPOINT = "stt.api.cloud.yandex.net:443"

PartialCb = Callable[[str, int], Awaitable[None]]
FinalCb = Callable[[str, int], Awaitable[None]]
EouCb = Callable[[int], Awaitable[None]]


class YandexSTTStream:
    """Per-call Yandex STT v3 streaming wrapper with user-supplied callbacks."""

    def __init__(
        self,
        api_key: str,
        sample_rate: int = 8000,
        language: str = "ru-RU",
        model: str = "general:rc",
        on_partial: Optional[PartialCb] = None,
        on_final: Optional[FinalCb] = None,
        on_eou: Optional[EouCb] = None,
        eou_mode: str = "default",
        call_uuid: str = "",
    ):
        self._api_key = api_key
        self._sample_rate = sample_rate
        self._language = language
        self._model = model
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_eou = on_eou
        self._eou_mode = eou_mode.lower() if eou_mode else "default"
        if self._eou_mode not in ("default", "high"):
            logger.warning(
                f"YandexSTTStream: unknown eou_mode={eou_mode!r}, using DEFAULT"
            )
            self._eou_mode = "default"

        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[stt_service_pb2_grpc.RecognizerStub] = None
        self._audio_queue: Optional[asyncio.Queue] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._started = False
        self._closed = False
        self._broken = False

        # EOU instrumentation (VLAT-07 prep): wall-clock gap between last
        # partial-text change and eou_update arrival. -1 if no partial seen.
        self._call_uuid: str = call_uuid
        self._last_partial_text: str = ""
        self._last_partial_change_ts: Optional[float] = None
        self._turn_idx: int = 0

    @property
    def is_broken(self) -> bool:
        return self._broken

    @property
    def is_started(self) -> bool:
        return self._started and not self._closed

    async def start(self) -> None:
        """Open gRPC channel, send session_options, start receive loop."""
        if self._started:
            return
        try:
            creds = grpc.ssl_channel_credentials()
            self._channel = grpc.aio.secure_channel(YANDEX_STT_ENDPOINT, creds)
            self._stub = stt_service_pb2_grpc.RecognizerStub(self._channel)
            self._audio_queue = asyncio.Queue()
            metadata = [("authorization", f"Api-Key {self._api_key}")]
            stream = self._stub.RecognizeStreaming(
                self._request_iterator(), metadata=metadata
            )
            self._recv_task = asyncio.create_task(self._receive_loop(stream))
            self._started = True
            logger.info("YandexSTTStream: gRPC stream opened")
        except Exception as e:
            logger.error(f"YandexSTTStream: start failed: {e}")
            self._broken = True

    async def send_audio(self, pcm_chunk: bytes) -> None:
        """Enqueue PCM chunk for streaming."""
        if self._broken or self._closed or not self._audio_queue:
            return
        await self._audio_queue.put(pcm_chunk)

    async def close(self) -> None:
        """Close stream cleanly. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._audio_queue:
            await self._audio_queue.put(None)
        if self._recv_task:
            try:
                await asyncio.wait_for(self._recv_task, timeout=1.0)
            except asyncio.TimeoutError:
                self._recv_task.cancel()
            except Exception:
                pass
            self._recv_task = None
        if self._channel:
            try:
                await self._channel.close()
            except Exception:
                pass
            self._channel = None
        self._started = False
        logger.info("YandexSTTStream: closed")

    async def _request_iterator(self):
        """First message: session_options. Then PCM chunks until None sentinel."""
        eou_type = (
            stt_pb2.DefaultEouClassifier.EouSensitivity.HIGH
            if self._eou_mode == "high"
            else stt_pb2.DefaultEouClassifier.EouSensitivity.DEFAULT
        )
        session_options = stt_pb2.StreamingOptions(
            recognition_model=stt_pb2.RecognitionModelOptions(
                model=self._model,
                audio_format=stt_pb2.AudioFormatOptions(
                    raw_audio=stt_pb2.RawAudio(
                        audio_encoding=stt_pb2.RawAudio.LINEAR16_PCM,
                        sample_rate_hertz=self._sample_rate,
                        audio_channel_count=1,
                    )
                ),
                language_restriction=stt_pb2.LanguageRestrictionOptions(
                    restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                    language_code=[self._language],
                ),
                audio_processing_type=stt_pb2.RecognitionModelOptions.REAL_TIME,
            ),
            eou_classifier=stt_pb2.EouClassifierOptions(
                default_classifier=stt_pb2.DefaultEouClassifier(type=eou_type),
            ),
        )
        yield stt_pb2.StreamingRequest(session_options=session_options)

        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield stt_pb2.StreamingRequest(chunk=stt_pb2.AudioChunk(data=chunk))

    async def _receive_loop(self, stream) -> None:
        """Dispatch server events to callbacks. Mark broken only on unexpected
        RPC error — if we initiated close (_closed=True), CANCELLED/any error
        during teardown is expected and must not poison is_broken."""
        try:
            async for response in stream:
                if response.HasField("partial"):
                    alts = response.partial.alternatives
                    if alts and alts[0].text:
                        # EOU instrumentation: record wall time of last
                        # partial-text change (proxy for "user stopped
                        # speaking"). Fires regardless of user callback.
                        if alts[0].text != self._last_partial_text:
                            self._last_partial_text = alts[0].text
                            self._last_partial_change_ts = time.monotonic()
                        if self._on_partial:
                            await self._on_partial(
                                alts[0].text,
                                response.audio_cursors.partial_time_ms,
                            )
                elif response.HasField("final"):
                    alts = response.final.alternatives
                    if alts and alts[0].text and self._on_final:
                        await self._on_final(
                            alts[0].text, response.audio_cursors.final_time_ms
                        )
                elif response.HasField("eou_update"):
                    # EOU instrumentation: compute wall-clock wait and log.
                    if self._last_partial_change_ts is not None:
                        eou_wait_ms = (
                            time.monotonic() - self._last_partial_change_ts
                        ) * 1000
                    else:
                        eou_wait_ms = -1
                    logger.info(
                        f"EOU_WAIT uuid={self._call_uuid} "
                        f"turn={self._turn_idx} "
                        f"eou_wait_ms={eou_wait_ms:.0f} "
                        f"text_len={len(self._last_partial_text)}"
                    )
                    self._turn_idx += 1
                    self._last_partial_change_ts = None
                    self._last_partial_text = ""
                    if self._on_eou:
                        await self._on_eou(response.audio_cursors.eou_time_ms)
        except grpc.aio.AioRpcError as e:
            if e.code() != grpc.StatusCode.CANCELLED:
                logger.error(f"YandexSTTStream: gRPC error {e.code()} {e.details()}")
                if not self._closed:
                    self._broken = True
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"YandexSTTStream: receive error: {e}")
            if not self._closed:
                self._broken = True
