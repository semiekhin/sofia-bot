"""
voice_asterisk.py — AudioSocket сервер: Asterisk → Sofia Voice Pipeline

Pipeline: AudioSocket audio → VAD → STT (Yandex SpeechKit) →
          LLM (Groq via proxy → stream_voice_response) →
          TTS (ElevenLabs via proxy) → AudioSocket audio

Asterisk AudioSocket protocol (TCP):
  Packet: [1 byte type] [2 bytes length BE] [payload]
  Types:  0x00=hangup, 0x01=UUID(16 bytes binary), 0x10=audio(slin 8kHz),
          0x12=audio(slin 16kHz), 0xFF=error

API routing:
  - Yandex STT/TTS: direct (works from Russia)
  - Groq/OpenAI/ElevenLabs: via proxy on 72.56.64.91:8095

Запуск: cd /opt/sofia-voice && venv/bin/python3 voice_asterisk.py
"""

import asyncio
import re
import hashlib
import os
import struct
import sys
import time
import uuid as uuid_mod

import httpx
import numpy as np
import onnxruntime as ort
from dotenv import load_dotenv
from loguru import logger

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from core.pipeline import stream_voice_response, sanitize_for_tts  # noqa: E402
from state_manager import StateManager  # noqa: E402
from yandex_stt_grpc import YandexSTTStream  # noqa: E402

# ============================================================
# AudioSocket Protocol Constants
# ============================================================

AS_TYPE_HANGUP = 0x00
AS_TYPE_UUID = 0x01
AS_TYPE_AUDIO = 0x10
AS_TYPE_AUDIO_16K = 0x12
AS_TYPE_ERROR = 0xFF

AUDIOSOCKET_HOST = "127.0.0.1"
AUDIOSOCKET_PORT = 9090

# Audio params
SAMPLE_RATE_IN = 8000  # From Asterisk (G.711 channels)
SAMPLE_RATE_OUT = 8000  # Back to Asterisk
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1

# Voice user ID offset (avoid collision with other channels)
VOICE_USER_ID_OFFSET = 9_500_000

# VAD settings
VAD_SILENCE_THRESHOLD = 0.5  # seconds of silence to trigger end-of-speech
# Raised from 0.3s (call e177d7ad: 300ms endpoint cut "цена и <срок>" mid-sentence
# on natural speech pause). Temporary until Yandex STT v3 gRPC streaming (server EOU).
VAD_MIN_SPEECH_DURATION = 0.3  # minimum speech duration to process
VAD_ENERGY_THRESHOLD = (
    200  # RMS energy threshold for speech detection (energy dead branch)
)
BARGE_IN_COOLDOWN = (
    0.5  # ignore VAD for N seconds after TTS cancel (suppress echo cascade)
)
MIN_SPEECH_BYTES_FOR_STT = (
    10240  # 0.64s @ 8kHz 16-bit; shorter → likely noise, skip STT
)

# Silero VAD (neural) — default provider since 16.04
VOICE_VAD_PROVIDER = os.getenv("VOICE_VAD_PROVIDER", "silero")  # silero | energy
SILERO_VAD_THRESHOLD = 0.5  # speech probability threshold (normal VAD)
SILERO_VAD_THRESHOLD_BARGE_IN = 0.5  # same as normal: TTS-echo mix on SIP line
# depresses speech prob below 0.6 → barge-in silently failed on call 2852fd23.
# Defense-in-depth kept: 5-frame consecutive confirm + 500ms cooldown + MIN_BYTES.
BARGE_IN_SILENCE_RESET = 0.3  # sec of sustained silence before clearing barge-in buffer

# API Proxy (for Groq/OpenAI/ElevenLabs from Russian VPS)
LLM_PROXY_BASE = os.getenv("LLM_PROXY_BASE", "http://72.56.64.91:8095")

# ElevenLabs settings (via proxy)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "YjESejviApN7SHrbfnA2")  # Nastya
ELEVENLABS_MODEL = "eleven_v3"

# Yandex SpeechKit settings (direct, no proxy needed)
YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
YANDEX_API_KEY = os.getenv("YANDEX_SPEECHKIT_API_KEY", "")

# STT mode selector — Phase 2B bifurcate (d)-light: method-pointer dispatch
# on AudioSocketCall._process_audio. rest=REST v1 accumulator, grpc=v3 stream.
STT_MODE = os.getenv("STT_MODE", "rest")  # rest | grpc

# EOU sensitivity (Phase 2D): default (conservative ~2240ms wait) | high (fast)
YANDEX_STT_EOU_MODE = os.getenv("YANDEX_STT_EOU_MODE", "default")

# VLAT-07 Phase 1: hint to Yandex DefaultEouClassifier for max inter-word pause.
# 0 = не передавать (Yandex internal default). 700ms = стартовое значение.
YANDEX_MAX_PAUSE_HINT_MS = int(os.getenv("YANDEX_MAX_PAUSE_HINT_MS", "700"))

# Yandex TTS settings
YANDEX_TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
YC_API_KEY = os.getenv("YC_API_KEY", "")
YC_FOLDER_ID = os.getenv("YC_FOLDER_ID", "")
YANDEX_TTS_VOICE = os.getenv("YANDEX_TTS_VOICE", "alena")
YANDEX_TTS_EMOTION = os.getenv("YANDEX_TTS_EMOTION", "neutral")
YANDEX_TTS_SPEED = float(os.getenv("YANDEX_TTS_SPEED", "1.1"))

# TTS provider selection (yandex / elevenlabs)
VOICE_TTS_PROVIDER = os.getenv("VOICE_TTS_PROVIDER", "yandex")

# Auto-hangup after Sofia farewell (RIZALTA only, env-gated).
# Detection: keyword match in last 80 chars of response OR state.dialog_finished
# (set by core/pipeline.py:1055-1060 when Sofia emits [END] marker).
VOICE_PROMPT_MODE = os.getenv("VOICE_PROMPT_MODE", "atlantis")
AUTO_HANGUP_ENABLED = os.getenv("AUTO_HANGUP_ENABLED", "true").lower() == "true"
FAREWELL_KEYWORDS = (
    "хорошего дня",
    "всего доброго",
    "удачного дня",
    "удачной дороги",
    "до свидания",
    "не буду занимать",
)
AUTO_HANGUP_DELAY_SEC = 1.5

# Database
SOFIA_PATH = os.getenv("SOFIA_PATH", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("DB_PATH", "sofia_voice.db")
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(SOFIA_PATH, DB_PATH)


def call_id_to_user_id(call_uuid: str) -> int:
    """Convert call UUID to stable user_id."""
    h = hashlib.md5(call_uuid.encode()).hexdigest()[:8]
    return VOICE_USER_ID_OFFSET + (int(h, 16) % 1_000_000)


# ============================================================
# Simple Energy-based VAD
# ============================================================


def compute_rms(audio_bytes: bytes) -> float:
    """Compute RMS energy of 16-bit PCM audio."""
    if len(audio_bytes) < 2:
        return 0.0
    samples = struct.unpack(f"<{len(audio_bytes) // 2}h", audio_bytes)
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


# ============================================================
# Silero VAD (neural) — module-level singleton + per-call instance
# Model: Silero VAD v4 ONNX (1.8MB, md5 03da8de2fec4108a089b39f1b4abefef).
# v5 underperforms at 8kHz (benchmark 13% recall vs v4's 73%); v5 kept as
# silero_vad_v5.onnx.legacy for future re-test when upstream improves 8kHz.
# ============================================================

SILERO_VAD_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "silero_vad.onnx"
)
SILERO_CHUNK_SAMPLES_8K = 256  # Silero expects 256 samples @ 8kHz (32ms)
SILERO_CHUNK_BYTES_8K = SILERO_CHUNK_SAMPLES_8K * 2  # 512 bytes int16
SILERO_LSTM_DIM = 64  # v4 LSTM state dim (v5 used 128)

_silero_session: ort.InferenceSession | None = None


def _get_silero_session() -> ort.InferenceSession:
    """Lazy singleton ONNX session. One model instance shared across calls."""
    global _silero_session
    if _silero_session is None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        _silero_session = ort.InferenceSession(
            SILERO_VAD_MODEL_PATH,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        with open(SILERO_VAD_MODEL_PATH, "rb") as _f:
            _md5 = hashlib.md5(_f.read()).hexdigest()
        logger.info(
            f"Silero VAD loaded: {SILERO_VAD_MODEL_PATH} " f"(v4, 8kHz, md5={_md5})"
        )
    return _silero_session


class SileroVAD:
    """Per-call Silero VAD v4: buffers AudioSocket frames into 512-byte chunks,
    keeps LSTM (h, c) state between chunks, returns True if any processed
    chunk exceeded the given speech-probability threshold.
    """

    def __init__(self, sample_rate: int = 8000):
        self._session = _get_silero_session()
        self._buffer = bytearray()
        self._h = np.zeros((2, 1, SILERO_LSTM_DIM), dtype=np.float32)
        self._c = np.zeros((2, 1, SILERO_LSTM_DIM), dtype=np.float32)
        self._sr = np.array(sample_rate, dtype=np.int64)
        self._chunk_bytes = SILERO_CHUNK_BYTES_8K

    def is_speech(self, pcm_bytes: bytes, threshold: float) -> bool:
        """Accumulate bytes, run Silero on each complete 512-byte chunk.
        Returns True if ANY chunk produced probability > threshold.
        """
        self._buffer.extend(pcm_bytes)
        speech = False
        while len(self._buffer) >= self._chunk_bytes:
            chunk = bytes(self._buffer[: self._chunk_bytes])
            del self._buffer[: self._chunk_bytes]
            audio_int16 = np.frombuffer(chunk, dtype=np.int16)
            audio_float = audio_int16.astype(np.float32) / 32768.0
            prob, new_h, new_c = self._session.run(
                None,
                {
                    "input": audio_float.reshape(1, -1),
                    "sr": self._sr,
                    "h": self._h,
                    "c": self._c,
                },
            )
            self._h = new_h
            self._c = new_c
            if float(prob[0][0]) > threshold:
                speech = True
        return speech


# ============================================================
# STT: OpenAI Whisper API
# ============================================================


async def transcribe_audio(audio_pcm: bytes, sample_rate: int = 8000) -> str:
    """Send PCM audio to Yandex SpeechKit STT, return transcription."""
    t0 = time.monotonic()

    # Convert PCM to OGG/Opus for Yandex (or send as lpcm)
    # Yandex REST API accepts lpcm format directly
    params = {
        "lang": "ru-RU",
        "format": "lpcm",
        "sampleRateHertz": str(sample_rate),
    }
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                YANDEX_STT_URL,
                params=params,
                headers=headers,
                content=audio_pcm,
            )
            if resp.status_code != 200:
                logger.error(
                    f"❌ Yandex STT HTTP {resp.status_code}: {resp.text[:200]}"
                )
                return ""

            result = resp.json()
            text = result.get("result", "").strip()

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(f'🗣️ STT: "{text}" ({elapsed:.0f}ms, {len(audio_pcm)} bytes)')
        return text
    except Exception as e:
        logger.error(f"❌ STT error: {e}")
        return ""


# ============================================================
# TTS: ElevenLabs Streaming
# ============================================================


def add_ssml_breaks(text: str) -> str:
    """Add SSML <break> tags between sentences for more natural TTS pacing.

    Only wraps multi-sentence text. Max 2 breaks per utterance to avoid
    ElevenLabs Flash v2.5 artifacts.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= 1:
        return text
    parts = [sentences[0]]
    breaks_added = 0
    for s in sentences[1:]:
        if breaks_added < 2:
            parts.append('<break time="300ms"/>' + s)
            breaks_added += 1
        else:
            parts.append(s)
    return " ".join(parts)


async def synthesize_tts_yandex(text: str) -> bytes:
    """Synthesize speech via Yandex SpeechKit TTS v1 REST.

    Returns raw LPCM 8kHz 16-bit mono -- ready for AudioSocket, no ffmpeg needed.
    Uses ssml parameter when text contains <break> tags, otherwise plain text.
    """
    if not YC_API_KEY:
        logger.error("YC_API_KEY not set for Yandex TTS")
        return b""

    headers = {
        "Authorization": f"Api-Key {YC_API_KEY}",
    }
    data = {
        "voice": YANDEX_TTS_VOICE,
        "emotion": YANDEX_TTS_EMOTION,
        "speed": str(YANDEX_TTS_SPEED),
        "format": "lpcm",
        "sampleRateHertz": "8000",
        "folderId": YC_FOLDER_ID,
    }
    # Use ssml parameter if text contains SSML tags, otherwise plain text
    if "<break" in text:
        data["ssml"] = f"<speak>{text}</speak>"
    else:
        data["text"] = text

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                YANDEX_TTS_URL,
                headers=headers,
                data=data,
            )
            if resp.status_code != 200:
                logger.error(
                    f"Yandex TTS HTTP {resp.status_code}: " f"{resp.text[:200]}"
                )
                return b""
            elapsed = (time.monotonic() - t0) * 1000
            pcm_data = resp.content
            logger.info(
                f"Yandex TTS: {len(text)} chars -> {len(pcm_data)} bytes "
                f"({elapsed:.0f}ms)"
            )
            return pcm_data
    except Exception as e:
        logger.error(f"Yandex TTS error: {e}")
        return b""


async def stream_tts_audio(text: str):
    """Stream PCM audio from ElevenLabs TTS through ffmpeg resampler.

    ElevenLabs → MP3 stream → ffmpeg (proper resampling) → 8kHz PCM chunks.
    First chunk arrives in ~300-500ms. ffmpeg runs as a persistent pipe.
    """
    if not ELEVENLABS_API_KEY:
        logger.error("❌ ELEVENLABS_API_KEY not set")
        return

    url = (
        f"{LLM_PROXY_BASE}/elevenlabs/v1/text-to-speech/"
        f"{ELEVENLABS_VOICE_ID}/stream"
        # f"?optimize_streaming_latency=4"  # disabled for v3
    )
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.50,
            "similarity_boost": 0.85,
        },
        "speed": 1.10,
    }

    # Start ffmpeg as a streaming converter: MP3 stdin → PCM 8kHz stdout
    ffmpeg_proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-i",
        "pipe:0",  # Input from stdin (MP3 stream)
        "-f",
        "s16le",  # Output format: signed 16-bit little-endian
        "-ar",
        "8000",  # Output sample rate: 8kHz
        "-ac",
        "1",  # Mono
        "-acodec",
        "pcm_s16le",
        "pipe:1",  # Output to stdout
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _feed_ffmpeg(resp_stream, proc):
        """Feed MP3 chunks from ElevenLabs into ffmpeg stdin."""
        try:
            async for chunk in resp_stream.aiter_bytes(chunk_size=4096):
                proc.stdin.write(chunk)
                await proc.stdin.drain()
        except Exception as e:
            logger.debug(f"Feed ffmpeg ended: {e}")
        finally:
            proc.stdin.close()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(
                        f"❌ ElevenLabs HTTP {resp.status_code}: "
                        f"{body.decode('utf-8', errors='replace')[:200]}"
                    )
                    ffmpeg_proc.kill()
                    return

                # Feed MP3 into ffmpeg in background
                feed_task = asyncio.create_task(_feed_ffmpeg(resp, ffmpeg_proc))

                # Read PCM from ffmpeg stdout as it becomes available
                while True:
                    pcm_chunk = await ffmpeg_proc.stdout.read(4096)
                    if not pcm_chunk:
                        break
                    yield pcm_chunk

                await feed_task

    except Exception as e:
        logger.error(f"❌ TTS streaming error: {e}")
    finally:
        try:
            ffmpeg_proc.kill()
        except ProcessLookupError:
            pass
        await ffmpeg_proc.wait()


# ============================================================
# Message persistence (simplified — no web_api dependency)
# ============================================================

import sqlite3  # noqa: E402


def _ensure_tables(db_path: str):
    """Create messages table if not exists."""
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT, user_id INTEGER, role TEXT, content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, stage TEXT
        )""")
    conn.commit()
    conn.close()


def save_message(chat_id: str, user_id: int, role: str, content: str):
    """Save message to database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO messages (chat_id, user_id, role, content) VALUES (?,?,?,?)",
        (chat_id, user_id, role, content),
    )
    conn.commit()
    conn.close()


def get_history(chat_id: str, limit: int = 20) -> list:
    """Get conversation history."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE chat_id=? "
        "ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


# ============================================================
# AudioSocket Connection Handler
# ============================================================


class AudioSocketCall:
    """Handles one AudioSocket connection (one phone call) with full pipeline."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.call_uuid: str | None = None
        self.start_time = time.time()
        self.audio_frames_received = 0
        self.audio_bytes_received = 0
        self._closed = False
        self._audio_type = AS_TYPE_AUDIO  # Default audio type for responses

        # VAD state
        self._speech_buffer = bytearray()
        self._silence_start: float | None = None
        self._is_speaking = False
        self._speech_start: float | None = None
        self._vad: SileroVAD | None = (
            SileroVAD(sample_rate=SAMPLE_RATE_IN)
            if VOICE_VAD_PROVIDER == "silero"
            else None
        )

        # Pipeline state
        self._user_id: int = 0
        self._chat_id: str = ""
        self._state_manager: StateManager | None = None
        self._is_responding = False  # True while STT→LLM→TTS pipeline is active
        self._tts_playing = False  # True only while TTS is actively streaming to client
        self._greeting_sent = False

        # Barge-in state
        self._barge_in_buffer = bytearray()  # Audio accumulated during response
        self._barge_in_detected = False  # Client started speaking during response
        self._last_user_text: str = ""  # Last processed user text (for combining)
        self._cancel_playback = False  # Signal to stop current TTS playback
        self._barge_in_cooldown_until: float = (
            0.0  # monotonic ts; drop VAD frames until then
        )
        self._last_barge_in_speech_ts: float | None = (
            None  # monotonic ts of last is_speech=True in _detect_barge_in
        )

        # Timings for current turn
        self._turn_timings: dict = {}

        # STT mode + gRPC stream state (Phase 2B)
        self._stt_mode: str = STT_MODE
        self._stt_stream: YandexSTTStream | None = None
        self._stt_stream_turn_t0: float | None = None
        self._grpc_final_buffer: str = ""
        self._grpc_partials_count: int = 0
        self._grpc_finals_count: int = 0
        self._stt_grpc_broken_logged: bool = False

        # Method-pointer dispatch for audio processing (Phase 2B bifurcate).
        # REST path: _process_audio_vad (accumulate → REST STT on EOU).
        # gRPC path: _stream_audio_to_grpc (forward each frame to open stream).
        if self._stt_mode == "grpc":
            self._process_audio = self._stream_audio_to_grpc
        else:
            self._process_audio = self._process_audio_vad

    async def run(self):
        """Main loop: read packets from Asterisk, process them."""
        peer = self.writer.get_extra_info("peername")
        logger.info(f"📞 New AudioSocket connection from {peer}")

        try:
            while not self._closed:
                header = await self.reader.readexactly(3)
                msg_type = header[0]
                msg_len = struct.unpack(">H", header[1:3])[0]

                payload = b""
                if msg_len > 0:
                    payload = await self.reader.readexactly(msg_len)

                await self._handle_packet(msg_type, payload)

        except asyncio.IncompleteReadError:
            logger.info(f"📞 Connection closed (uuid={self.call_uuid})")
        except ConnectionResetError:
            logger.info(f"📞 Connection reset (uuid={self.call_uuid})")
        except Exception as e:
            logger.error(f"❌ AudioSocket error: {e}")
        finally:
            await self._cleanup()

    async def _handle_packet(self, msg_type: int, payload: bytes):
        if msg_type == AS_TYPE_UUID:
            if len(payload) == 16:
                self.call_uuid = str(uuid_mod.UUID(bytes=payload))
            else:
                self.call_uuid = payload.hex()

            # Initialize pipeline for this call
            self._user_id = call_id_to_user_id(self.call_uuid)
            self._chat_id = str(self._user_id)
            self._state_manager = StateManager(DB_PATH)
            logger.info(f"📞 Call UUID: {self.call_uuid}, user_id: {self._user_id}")

            # Send greeting after short delay
            asyncio.create_task(self._send_greeting())

            # Open gRPC stream in parallel with greeting; cached PCM (~12s)
            # gives TLS handshake plenty of time.
            if self._stt_mode == "grpc":
                asyncio.create_task(self._open_grpc_stream())

        elif msg_type in (AS_TYPE_AUDIO, AS_TYPE_AUDIO_16K):
            self.audio_frames_received += 1
            self.audio_bytes_received += len(payload)
            self._audio_type = msg_type

            # Drop frames from VAD/STT during post-barge-in cooldown
            # (echo bleed-through from cancelled TTS otherwise retriggers VAD in a cascade)
            if time.monotonic() < self._barge_in_cooldown_until:
                return

            # Process audio via method-pointer dispatch (REST or gRPC)
            if not self._is_responding:
                await self._process_audio(payload)
            elif self._tts_playing:
                # TTS actively streaming — client voice is a barge-in candidate
                await self._detect_barge_in(payload)
            # else: _is_responding=True but TTS not yet streaming (STT/LLM phase).
            # Client finishing own utterance — ignore frames.
            # See call 89dadd55: pre-TTS barge-in killed TTS at 0s played.

        elif msg_type == AS_TYPE_HANGUP:
            logger.info(f"📞 Hangup (uuid={self.call_uuid})")
            self._closed = True

        elif msg_type == AS_TYPE_ERROR:
            error_msg = (
                payload.decode("utf-8", errors="replace") if payload else "unknown"
            )
            logger.error(f"❌ Asterisk error: {error_msg}")
            self._closed = True

    async def _send_greeting(self):
        """Send initial greeting when call connects.

        Uses pre-generated PCM cache if available, otherwise synthesizes live.
        Cache files: greeting_rizalta.pcm, greeting_atlantis.pcm
        To regenerate: see comments in code or Build Report.
        """
        await asyncio.sleep(0.3)  # Wait for audio stream to start
        if self._closed or self._greeting_sent:
            return
        self._greeting_sent = True

        voice_prompt_mode = os.getenv("VOICE_PROMPT_MODE", "atlantis")
        logger.info(f"Sending greeting... [prompt mode: {voice_prompt_mode}]")
        if voice_prompt_mode == "rizalta":
            greeting = (
                "Алло, здравствуйте! У меня для вас важная новость. "
                "Стартовали продажи апартаментов на Алтае с доходностью "
                "от двух с половиной миллионов и окупаемостью от семи лет. "
                "Хотите узнать подробности?"
            )
            cache_file = os.path.join(SOFIA_PATH, "greeting_rizalta.pcm")
        else:
            greeting = (
                "Здравствуйте! Меня зовут София, "
                "я консультант по курортной недвижимости. Чем могу помочь?"
            )
            cache_file = os.path.join(SOFIA_PATH, "greeting_atlantis.pcm")

        # Save to DB
        save_message(self._chat_id, self._user_id, "assistant", greeting)

        # Try cached PCM first (instant playback)
        if os.path.exists(cache_file):
            logger.info(f"Using cached greeting: {cache_file}")
            await self._speak_pcm(cache_file)
        else:
            logger.info("No cached greeting, synthesizing live")
            await self._speak(greeting)

    async def _process_audio_vad(self, audio_bytes: bytes):
        """VAD dispatch (silero | energy): detect speech end, trigger STT."""
        now = time.time()
        if self._vad is not None:
            is_speech = self._vad.is_speech(audio_bytes, SILERO_VAD_THRESHOLD)
        else:
            is_speech = compute_rms(audio_bytes) > VAD_ENERGY_THRESHOLD

        if is_speech:
            # Speech detected
            if not self._is_speaking:
                self._is_speaking = True
                self._speech_start = now
                logger.debug("🎤 Speech start detected")
            self._silence_start = None
            self._speech_buffer.extend(audio_bytes)

        elif self._is_speaking:
            # Silence during speech — might be end of utterance
            self._speech_buffer.extend(audio_bytes)

            if self._silence_start is None:
                self._silence_start = now
            elif (now - self._silence_start) >= VAD_SILENCE_THRESHOLD:
                # Enough silence — process the speech
                speech_duration = now - (self._speech_start or now)
                if speech_duration >= VAD_MIN_SPEECH_DURATION:
                    buf_len = len(self._speech_buffer)
                    if buf_len < MIN_SPEECH_BYTES_FOR_STT:
                        logger.debug(
                            f"Audio too short ({buf_len} bytes "
                            f"< {MIN_SPEECH_BYTES_FOR_STT}), skipping STT"
                        )
                        self._speech_buffer.clear()
                        self._is_speaking = False
                        self._silence_start = None
                        self._speech_start = None
                        return
                    speech_data = bytes(self._speech_buffer)
                    self._speech_buffer.clear()
                    self._is_speaking = False
                    self._silence_start = None
                    self._speech_start = None

                    # Process in background to not block audio reading
                    asyncio.create_task(self._process_turn(speech_data))
                else:
                    # Too short — discard
                    self._speech_buffer.clear()
                    self._is_speaking = False
                    self._silence_start = None

    async def _open_grpc_stream(self):
        """Open YandexSTTStream async; greeting (~12s cached PCM) gives
        TLS handshake plenty of time. No retries here — broken state
        handled by fallback logic in _stream_audio_to_grpc."""
        self._stt_stream = YandexSTTStream(
            api_key=YANDEX_API_KEY,
            sample_rate=SAMPLE_RATE_IN,
            language="ru-RU",
            model="general:rc",
            on_partial=self._on_grpc_partial,
            on_final=self._on_grpc_final,
            on_eou=self._on_grpc_eou,
            eou_mode=YANDEX_STT_EOU_MODE,
            max_pause_between_words_hint_ms=YANDEX_MAX_PAUSE_HINT_MS,
            call_uuid=self.call_uuid or "",
        )
        await self._stt_stream.start()
        if self._stt_stream.is_broken:
            logger.error("gRPC stream failed to start — falling back to REST")
            self._fallback_to_rest()
        else:
            logger.info(f"gRPC stream ready for call {self.call_uuid}")

    async def _stream_audio_to_grpc(self, payload: bytes):
        """gRPC audio path: forward each AudioSocket frame to open stream.
        Phase 2C: continuous streaming — frames flow even during TTS so
        that client continuation after Sofia's first reply is captured.
        TTS-echo is guarded in _on_grpc_* callbacks via _tts_playing flag."""
        # Stream not ready yet (UUID just arrived, TLS in flight)
        if self._stt_stream is None or not self._stt_stream.is_started:
            return
        # Broken stream → one-time fallback to REST
        if self._stt_stream.is_broken:
            if not self._stt_grpc_broken_logged:
                logger.warning("gRPC stream broken — falling back to REST")
                self._stt_grpc_broken_logged = True
            self._fallback_to_rest()
            # Still process this frame through REST path
            await self._process_audio_vad(payload)
            return
        # Start-of-turn timestamp (for 🗣️ STT (grpc) duration log)
        if self._stt_stream_turn_t0 is None:
            self._stt_stream_turn_t0 = time.monotonic()
        await self._stt_stream.send_audio(payload)

    async def _on_grpc_partial(self, text: str, time_ms: int):
        """Server partial — count for observability, no turn action."""
        # TTS playing but no barge-in — treat as TTS echo, ignore (Phase 2C)
        # NOTE: до _cancel_playback=True (Silero barge-in confirm, ~200мс)
        # первые partial с речью клиента игнорируются как возможное TTS-echo.
        # После confirm guard снимается и stream продолжает принимать речь
        # без cooldown-блока — остаток фразы и продолжения доходят целиком.
        if self._tts_playing and not self._cancel_playback:
            return
        self._grpc_partials_count += 1
        logger.debug(f"gRPC partial: [{text[:60]}] t={time_ms}ms")

    async def _on_grpc_final(self, text: str, time_ms: int):
        """Server final — accumulate into buffer. Multiple finals may
        precede one eou_update (Yandex segments long utterances)."""
        # TTS playing but no barge-in — treat as TTS echo, ignore (Phase 2C)
        if self._tts_playing and not self._cancel_playback:
            return
        self._grpc_final_buffer = (self._grpc_final_buffer + " " + text).strip()
        self._grpc_finals_count += 1
        logger.debug(
            f"gRPC final: [{text}] t={time_ms}ms "
            f"buffer_len={len(self._grpc_final_buffer)}"
        )

    async def _on_grpc_eou(self, time_ms: int):
        """Server EOU — assemble buffer, launch turn. Idempotent: if
        buffer empty or responding already, skip to keep turn ordering.
        TTS-echo guard (Phase 2C): keep buffer intact if echo suspected,
        so a later legit EOU (after barge-in cancel) still has the text."""
        # TTS playing but no barge-in — treat as TTS echo, ignore (Phase 2C)
        # Keep buffer intact — next legit EOU will use it.
        if self._tts_playing and not self._cancel_playback:
            return
        if not self._grpc_final_buffer or self._is_responding:
            self._grpc_final_buffer = ""
            return
        text = self._grpc_final_buffer
        stream_dur_ms = 0
        if self._stt_stream_turn_t0 is not None:
            stream_dur_ms = int((time.monotonic() - self._stt_stream_turn_t0) * 1000)
        logger.info(
            f'🗣️ STT (grpc): "{text}" '
            f"({stream_dur_ms}ms stream, {self._grpc_partials_count} partials, "
            f"{self._grpc_finals_count} finals)"
        )
        # Reset per-turn counters before dispatching turn
        self._grpc_final_buffer = ""
        self._grpc_partials_count = 0
        self._grpc_finals_count = 0
        self._stt_stream_turn_t0 = None
        asyncio.create_task(self._process_turn(None, text_override=text))

    def _fallback_to_rest(self):
        """Re-point _process_audio to REST path for the rest of the call.
        VAD fields in __init__ are inert until now — REST path works clean.
        Partial buffer discarded — avoid replying to incomplete utterance
        (mirrors broken-in-idle behaviour for consistency)."""
        self._process_audio = self._process_audio_vad
        self._grpc_final_buffer = ""
        self._stt_stream_turn_t0 = None

    async def _detect_barge_in(self, audio_bytes: bytes):
        """Detect if client is speaking while Sofia is responding (barge-in).

        Requires 5+ consecutive speech frames (~100ms) to avoid false triggers
        from noise or echo. Once confirmed, stops TTS and accumulates audio.
        """
        if self._vad is not None:
            is_speech = self._vad.is_speech(audio_bytes, SILERO_VAD_THRESHOLD_BARGE_IN)
        else:
            is_speech = compute_rms(audio_bytes) > VAD_ENERGY_THRESHOLD * 1.5
        if is_speech:  # Higher threshold during playback
            self._barge_in_buffer.extend(audio_bytes)
            self._last_barge_in_speech_ts = time.monotonic()
            if not self._barge_in_detected:
                # Count consecutive speech frames before confirming barge-in.
                # Silero: 10 frames — chunking mismatch gives ~200ms real speech
                # (call e177d7ad: 5 frames confirmed on a single "ээ"/breath).
                # Energy: 5 frames (100ms, 1:1 frame→RMS) — kept for rollback fidelity
                # via VOICE_VAD_PROVIDER=energy.
                speech_frames = len(self._barge_in_buffer) // 320
                confirm_frames = 10 if self._vad is not None else 5
                if speech_frames >= confirm_frames:
                    self._barge_in_detected = True
                    self._cancel_playback = True
                    self._barge_in_cooldown_until = time.monotonic() + BARGE_IN_COOLDOWN
                    logger.info(
                        f"🔇 BARGE-IN confirmed — stopping TTS, "
                        f"cooldown {int(BARGE_IN_COOLDOWN * 1000)}ms "
                        f"({len(self._barge_in_buffer)} bytes accumulated)"
                    )
        elif self._barge_in_detected:
            # Silence after confirmed barge-in — keep accumulating
            self._barge_in_buffer.extend(audio_bytes)
        else:
            if self._vad is not None:
                # Silero: chunking mismatch (512B chunk vs 320B frame) causes
                # True/False alternation on continuous speech. Clear only after
                # sustained silence, not on every False. See call bcf67956.
                if (
                    self._last_barge_in_speech_ts is None
                    or time.monotonic() - self._last_barge_in_speech_ts
                    > BARGE_IN_SILENCE_RESET
                ):
                    self._barge_in_buffer.clear()
                    self._last_barge_in_speech_ts = None
            else:
                # Energy: 1:1 frame→RMS, no alternation. Keep original instant
                # clear for VOICE_VAD_PROVIDER=energy rollback fidelity.
                self._barge_in_buffer.clear()

    async def _process_turn(
        self,
        audio_pcm: bytes | None,
        text_override: str | None = None,
    ):
        """Full turn: (STT | text_override) → LLM → TTS → send audio.

        text_override: provided by gRPC callback (bypasses REST STT).
        Handles barge-in via _cancel_playback flag in _speak.
        """
        if self._is_responding or self._closed:
            return
        self._is_responding = True
        self._cancel_playback = False
        self._barge_in_detected = False
        self._barge_in_buffer.clear()
        self._last_barge_in_speech_ts = None
        turn_start = time.monotonic()
        self._turn_timings = {}

        try:
            # 1. STT (REST) or skip (gRPC — text already assembled in callback)
            if text_override is not None:
                text = text_override
                self._turn_timings["stt_ms"] = 0  # logged in _on_grpc_eou
            else:
                t0 = time.monotonic()
                text = await transcribe_audio(audio_pcm, SAMPLE_RATE_IN)
                self._turn_timings["stt_ms"] = (time.monotonic() - t0) * 1000

            if not text or len(text.strip()) < 2:
                logger.debug("🎤 Empty transcription, skipping")
                return

            logger.info(f'🎤 USER: "{text}"')
            self._last_user_text = text
            save_message(self._chat_id, self._user_id, "user", text)

            # 2. LLM
            t0 = time.monotonic()
            history = get_history(self._chat_id)
            response = ""
            async for chunk in stream_voice_response(
                user_id=self._user_id,
                user_message=text,
                user_name="Voice Client",
                history=history,
                state_manager=self._state_manager,
                channel="voice_asterisk",
                call_id=self.call_uuid or "",
            ):
                if chunk:
                    response += chunk
            self._turn_timings["llm_ms"] = (time.monotonic() - t0) * 1000

            if not response:
                response = "Простите, повторите пожалуйста?"

            logger.info(f'🧠 SOFIA: "{response}"')
            save_message(self._chat_id, self._user_id, "assistant", response)

            # 3. TTS + send audio (may be interrupted by barge-in)
            t0 = time.monotonic()
            await self._speak(response)
            self._turn_timings["tts_ms"] = (time.monotonic() - t0) * 1000

            # Log timings
            total = (time.monotonic() - turn_start) * 1000
            self._turn_timings["total_ms"] = total
            logger.info(
                f"⏱️ Turn timings: "
                f"STT={self._turn_timings.get('stt_ms', 0):.0f}ms, "
                f"LLM={self._turn_timings.get('llm_ms', 0):.0f}ms, "
                f"TTS={self._turn_timings.get('tts_ms', 0):.0f}ms, "
                f"TOTAL={total:.0f}ms"
            )

            # Auto-hangup check (RIZALTA only, env-gated)
            should_hangup, reason = self._should_hangup(response)
            if should_hangup:
                logger.info(
                    f"AUTO_HANGUP detect uuid={self.call_uuid} " f"reason={reason}"
                )
                asyncio.create_task(self._delayed_hangup(reason))

        except Exception as e:
            logger.error(f"❌ Turn processing error: {e}")
        finally:
            self._is_responding = False
            self._tts_playing = False  # paranoid reset; _speak/_speak_pcm own it

            # After TTS cancel: discard barge-in buffer, let VAD listen fresh.
            # Re-feeding the accumulated buffer lets polluted fragments
            # (echo + speech mix) slip past MIN_SPEECH_BYTES_FOR_STT threshold —
            # live call 16.04 UUID 21b96626 cascaded into "плохо слышно" fallback.
            if self._barge_in_detected and self._barge_in_buffer:
                logger.debug(
                    f"barge-in buffer cleared after cooldown "
                    f"({len(self._barge_in_buffer)} bytes discarded)"
                )
            self._barge_in_buffer.clear()
            self._barge_in_detected = False
            self._last_barge_in_speech_ts = None

    async def _speak_pcm(self, pcm_file: str):
        """Send pre-generated PCM file to Asterisk. Used for cached greetings."""
        if self._closed:
            return
        frame_size = 320
        t0 = time.monotonic()
        total_bytes = 0
        try:
            with open(pcm_file, "rb") as f:
                pcm_data = f.read()
            total_bytes = len(pcm_data)
            offset = 0
            first_sent = False
            while offset < len(pcm_data):
                if self._closed or self._cancel_playback:
                    break
                end = min(offset + frame_size, len(pcm_data))
                frame = pcm_data[offset:end]
                if len(frame) < frame_size:
                    frame = frame + b"\x00" * (frame_size - len(frame))
                if not first_sent:
                    self._tts_playing = True
                await self._send_audio(frame, self._audio_type)
                if not first_sent:
                    logger.info(
                        f"TTS cached first frame: {(time.monotonic() - t0) * 1000:.0f}ms"
                    )
                    first_sent = True
                offset += frame_size
                await asyncio.sleep(0.018)
        except Exception as e:
            logger.error(f"Cached PCM playback error: {e}")
        finally:
            self._tts_playing = False
        elapsed = (time.monotonic() - t0) * 1000
        duration_sec = (
            total_bytes / (SAMPLE_RATE_OUT * SAMPLE_WIDTH) if total_bytes else 0
        )
        logger.info(
            f"TTS cached done: {total_bytes} bytes "
            f"({duration_sec:.1f}s audio, total={elapsed:.0f}ms)"
        )

    async def _speak(self, text: str):
        """Synthesize text and send audio to Asterisk.

        Yandex TTS (default): single request, returns full LPCM buffer, no ffmpeg.
        ElevenLabs (legacy): streaming MP3 via ffmpeg resample.
        """
        if self._closed:
            return

        clean_text = sanitize_for_tts(text)
        clean_text = add_ssml_breaks(clean_text)
        if not clean_text:
            return

        frame_size = 320  # 20ms @ 8kHz slin16
        buffer = bytearray()
        total_bytes = 0
        first_audio_time = None
        t0 = time.monotonic()

        try:
            if VOICE_TTS_PROVIDER == "yandex":
                # Yandex TTS: single request, full LPCM buffer
                pcm_data = await synthesize_tts_yandex(clean_text)
                if not pcm_data:
                    return
                total_bytes = len(pcm_data)
                offset = 0
                while offset < len(pcm_data):
                    if self._closed or self._cancel_playback:
                        if self._cancel_playback:
                            logger.info("TTS playback cancelled (barge-in)")
                        break
                    end = min(offset + frame_size, len(pcm_data))
                    frame = pcm_data[offset:end]
                    if len(frame) < frame_size:
                        frame = frame + b"\x00" * (frame_size - len(frame))
                    if first_audio_time is None:
                        self._tts_playing = True
                    await self._send_audio(frame, self._audio_type)
                    if first_audio_time is None:
                        first_audio_time = (time.monotonic() - t0) * 1000
                        logger.info(f"TTS first audio chunk: {first_audio_time:.0f}ms")
                    offset += frame_size
                    await asyncio.sleep(0.018)
            else:
                # ElevenLabs legacy: streaming via ffmpeg
                async for pcm_chunk in stream_tts_audio(clean_text):
                    if self._closed or self._cancel_playback:
                        if self._cancel_playback:
                            logger.info("TTS playback cancelled (barge-in)")
                        break

                    buffer.extend(pcm_chunk)
                    total_bytes += len(pcm_chunk)

                    while len(buffer) >= frame_size:
                        if self._cancel_playback:
                            break
                        frame = bytes(buffer[:frame_size])
                        del buffer[:frame_size]
                        if first_audio_time is None:
                            self._tts_playing = True
                        await self._send_audio(frame, self._audio_type)
                        if first_audio_time is None:
                            first_audio_time = (time.monotonic() - t0) * 1000
                            logger.info(
                                f"TTS first audio chunk: {first_audio_time:.0f}ms"
                            )
                        await asyncio.sleep(0.018)

                # Send remaining buffer
                if buffer and not self._closed and not self._cancel_playback:
                    remaining = bytes(buffer)
                    if len(remaining) < frame_size:
                        remaining = remaining + b"\x00" * (frame_size - len(remaining))
                    if first_audio_time is None:
                        self._tts_playing = True
                    await self._send_audio(remaining, self._audio_type)
                    if first_audio_time is None:
                        first_audio_time = (time.monotonic() - t0) * 1000
        finally:
            self._tts_playing = False

        elapsed = (time.monotonic() - t0) * 1000
        duration_sec = (
            total_bytes / (SAMPLE_RATE_OUT * SAMPLE_WIDTH) if total_bytes else 0
        )
        first_ms = f"{first_audio_time:.0f}" if first_audio_time is not None else "N/A"
        logger.info(
            f"TTS done: {len(clean_text)} chars -> {total_bytes} bytes "
            f"({duration_sec:.1f}s audio, first={first_ms}ms, "
            f"total={elapsed:.0f}ms)"
        )

    def _should_hangup(self, response: str) -> tuple[bool, str]:
        """Decide whether to fire auto-hangup after Sofia's last reply.
        RIZALTA only, env-gated. Returns (trigger, reason)."""
        if not AUTO_HANGUP_ENABLED or VOICE_PROMPT_MODE != "rizalta":
            return False, ""
        if self._state_manager is not None:
            state = self._state_manager.get_state(self._user_id)
            if state is not None and getattr(state, "dialog_finished", False):
                return True, "state"
        if response:
            tail = response[-80:].lower()
            if any(kw in tail for kw in FAREWELL_KEYWORDS):
                return True, "keyword"
        return False, ""

    async def _delayed_hangup(self, reason: str):
        """Wait AUTO_HANGUP_DELAY_SEC, abort if user speaks or connection
        already closed. Otherwise send AS_TYPE_HANGUP and close."""
        t0 = time.monotonic()
        chunk = 0.1
        while time.monotonic() - t0 < AUTO_HANGUP_DELAY_SEC:
            await asyncio.sleep(chunk)
            if self._closed:
                logger.info(f"AUTO_HANGUP cancel uuid={self.call_uuid} reason=closed")
                return
            if self._is_responding:
                logger.info(
                    f"AUTO_HANGUP cancel uuid={self.call_uuid} reason=user_spoke"
                )
                return
        logger.info(
            f"AUTO_HANGUP exec uuid={self.call_uuid} "
            f"after_delay={AUTO_HANGUP_DELAY_SEC}s"
        )
        await self._send_hangup()
        self._closed = True

    async def _send_hangup(self):
        """Send AS_TYPE_HANGUP (0x00) frame to Asterisk — protocol-level
        hangup request. Asterisk terminates the PJSIP leg."""
        if self._closed:
            return
        try:
            self.writer.write(struct.pack(">BH", AS_TYPE_HANGUP, 0))
            await self.writer.drain()
        except Exception as e:
            logger.debug(f"_send_hangup write error: {e}")

    async def _send_audio(self, audio_data: bytes, audio_type: int = AS_TYPE_AUDIO):
        """Send audio packet back to Asterisk."""
        if self._closed:
            return
        try:
            header = struct.pack(">BH", audio_type, len(audio_data))
            self.writer.write(header + audio_data)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self._closed = True

    async def _cleanup(self):
        """Clean up after call ends."""
        elapsed = time.time() - self.start_time
        logger.info(
            f"📞 Call ended: uuid={self.call_uuid}, "
            f"duration={elapsed:.1f}s, "
            f"audio_frames={self.audio_frames_received}, "
            f"user_id={self._user_id}"
        )
        if self._stt_stream is not None:
            try:
                await self._stt_stream.close()
            except Exception as e:
                logger.debug(f"gRPC stream close error: {e}")
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


# ============================================================
# AudioSocket TCP Server
# ============================================================


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle new AudioSocket connection from Asterisk."""
    call = AudioSocketCall(reader, writer)
    await call.run()


async def main():
    # Ensure database tables exist
    _ensure_tables(DB_PATH)

    # Eager-load Silero VAD (if enabled) so "loaded" log appears at startup,
    # not on first call — also moves ~200ms init out of first-call latency.
    if VOICE_VAD_PROVIDER == "silero":
        _get_silero_session()

    server = await asyncio.start_server(
        handle_connection,
        AUDIOSOCKET_HOST,
        AUDIOSOCKET_PORT,
    )

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"🚀 AudioSocket server listening on {addrs}")
    eou_desc = f", EOU={YANDEX_STT_EOU_MODE}" if STT_MODE == "grpc" else ""
    if STT_MODE == "grpc" and YANDEX_MAX_PAUSE_HINT_MS > 0:
        eou_desc += f", hint={YANDEX_MAX_PAUSE_HINT_MS}ms"
    logger.info(
        f"   Pipeline: Yandex STT ({STT_MODE.upper()}{eou_desc}) -> "
        f"{VOICE_TTS_PROVIDER.upper()} TTS"
    )
    logger.info(
        f"   Mode: {VOICE_PROMPT_MODE}, "
        f"auto_hangup={'on' if AUTO_HANGUP_ENABLED else 'off'}"
    )
    logger.info(f"   DB: {DB_PATH}")
    logger.info("   Waiting for Asterisk connections...")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Sofia Voice — Asterisk AudioSocket Pipeline (Phase 3)")
    logger.info("=" * 60)
    asyncio.run(main())
