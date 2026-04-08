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
import hashlib
import os
import struct
import sys
import time
import uuid as uuid_mod

import httpx
from dotenv import load_dotenv
from loguru import logger

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from core.pipeline import stream_voice_response, sanitize_for_tts  # noqa: E402
from state_manager import StateManager  # noqa: E402

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
VAD_SILENCE_THRESHOLD = 0.4  # seconds of silence to trigger end-of-speech
VAD_MIN_SPEECH_DURATION = 0.3  # minimum speech duration to process
VAD_ENERGY_THRESHOLD = 200  # RMS energy threshold for speech detection

# API Proxy (for Groq/OpenAI/ElevenLabs from Russian VPS)
LLM_PROXY_BASE = os.getenv("LLM_PROXY_BASE", "http://72.56.64.91:8095")

# ElevenLabs settings (via proxy)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "YjESejviApN7SHrbfnA2")  # Nastya
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Yandex SpeechKit settings (direct, no proxy needed)
YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
YANDEX_API_KEY = os.getenv("YANDEX_SPEECHKIT_API_KEY", "")

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
        f"?optimize_streaming_latency=4"
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
            "stability": 0.35,
            "similarity_boost": 0.79,
        },
        "speed": 1.19,
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

        # Pipeline state
        self._user_id: int = 0
        self._chat_id: str = ""
        self._state_manager: StateManager | None = None
        self._is_responding = False  # True while STT→LLM→TTS pipeline is active
        self._greeting_sent = False

        # Barge-in state
        self._barge_in_buffer = bytearray()  # Audio accumulated during response
        self._barge_in_detected = False  # Client started speaking during response
        self._last_user_text: str = ""  # Last processed user text (for combining)
        self._cancel_playback = False  # Signal to stop current TTS playback

        # Timings for current turn
        self._turn_timings: dict = {}

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

        elif msg_type in (AS_TYPE_AUDIO, AS_TYPE_AUDIO_16K):
            self.audio_frames_received += 1
            self.audio_bytes_received += len(payload)
            self._audio_type = msg_type

            # Process audio through VAD
            if not self._is_responding:
                await self._process_audio_vad(payload)
            else:
                # During response: detect barge-in (client speaking over Sofia)
                await self._detect_barge_in(payload)

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
        """Send initial greeting when call connects."""
        await asyncio.sleep(0.3)  # Wait for audio stream to start
        if self._closed or self._greeting_sent:
            return
        self._greeting_sent = True

        voice_prompt_mode = os.getenv("VOICE_PROMPT_MODE", "atlantis")
        logger.info(f"🎙️ Sending greeting... [prompt mode: {voice_prompt_mode}]")
        if voice_prompt_mode == "rizalta":
            greeting = (
                "Алло? Добрый день! Это Софья, агентство Оазис. "
                "Две минуты есть? Хочу классное предложение быстро рассказать."
            )
        else:
            greeting = (
                "Здравствуйте! Меня зовут София, "
                "я консультант по курортной недвижимости. Чем могу помочь?"
            )

        # Save to DB
        save_message(self._chat_id, self._user_id, "assistant", greeting)

        # Synthesize and send
        await self._speak(greeting)

    async def _process_audio_vad(self, audio_bytes: bytes):
        """Simple energy-based VAD: detect speech end, trigger STT."""
        rms = compute_rms(audio_bytes)
        now = time.time()

        if rms > VAD_ENERGY_THRESHOLD:
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

    async def _detect_barge_in(self, audio_bytes: bytes):
        """Detect if client is speaking while Sofia is responding (barge-in).

        Requires 5+ consecutive speech frames (~100ms) to avoid false triggers
        from noise or echo. Once confirmed, stops TTS and accumulates audio.
        """
        rms = compute_rms(audio_bytes)
        if rms > VAD_ENERGY_THRESHOLD * 1.5:  # Higher threshold during playback
            self._barge_in_buffer.extend(audio_bytes)
            if not self._barge_in_detected:
                # Count consecutive speech frames before confirming barge-in
                speech_frames = len(self._barge_in_buffer) // 320
                if speech_frames >= 5:  # ~100ms of sustained speech
                    self._barge_in_detected = True
                    self._cancel_playback = True
                    logger.info(
                        f"🔇 BARGE-IN confirmed — stopping TTS "
                        f"({len(self._barge_in_buffer)} bytes accumulated)"
                    )
        elif self._barge_in_detected:
            # Silence after confirmed barge-in — keep accumulating
            self._barge_in_buffer.extend(audio_bytes)
        else:
            # Noise spike, not sustained — reset
            self._barge_in_buffer.clear()

    async def _process_turn(self, audio_pcm: bytes):
        """Full turn: STT → LLM → TTS → send audio. Handles barge-in."""
        if self._is_responding or self._closed:
            return
        self._is_responding = True
        self._cancel_playback = False
        self._barge_in_detected = False
        self._barge_in_buffer.clear()
        turn_start = time.monotonic()
        self._turn_timings = {}

        try:
            # 1. STT
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

        except Exception as e:
            logger.error(f"❌ Turn processing error: {e}")
        finally:
            self._is_responding = False

            # Check for barge-in: client spoke during our response
            if self._barge_in_detected and self._barge_in_buffer:
                barge_audio = bytes(self._barge_in_buffer)
                self._barge_in_buffer.clear()
                self._barge_in_detected = False
                logger.info(f"🔇 Processing barge-in audio: {len(barge_audio)} bytes")
                # Feed barge-in audio through normal VAD pipeline
                # Reset VAD state and process accumulated audio
                self._speech_buffer = bytearray(barge_audio)
                self._is_speaking = True
                self._speech_start = time.time()
                self._silence_start = time.time()  # Start silence timer
            else:
                self._barge_in_buffer.clear()
                self._barge_in_detected = False

    async def _speak(self, text: str):
        """Stream-synthesize text and send audio to Asterisk in real-time.

        Audio starts playing ~300-500ms after call, not 5-8s.
        """
        if self._closed:
            return

        clean_text = sanitize_for_tts(text)
        if not clean_text:
            return

        # Asterisk frame: 320 bytes = 20ms @ 8kHz slin16
        frame_size = 320
        buffer = bytearray()
        total_bytes = 0
        first_audio_time = None
        t0 = time.monotonic()

        async for pcm_chunk in stream_tts_audio(clean_text):
            if self._closed or self._cancel_playback:
                if self._cancel_playback:
                    logger.info("🔇 TTS playback cancelled (barge-in)")
                break

            if first_audio_time is None:
                first_audio_time = (time.monotonic() - t0) * 1000
                logger.info(f"🔊 TTS first audio chunk: {first_audio_time:.0f}ms")

            buffer.extend(pcm_chunk)
            total_bytes += len(pcm_chunk)

            # Send complete frames as they accumulate
            while len(buffer) >= frame_size:
                if self._cancel_playback:
                    break
                frame = bytes(buffer[:frame_size])
                del buffer[:frame_size]
                await self._send_audio(frame, self._audio_type)
                await asyncio.sleep(0.018)

        # Send remaining buffer (pad to frame size) — unless cancelled
        if buffer and not self._closed and not self._cancel_playback:
            remaining = bytes(buffer)
            if len(remaining) < frame_size:
                remaining = remaining + b"\x00" * (frame_size - len(remaining))
            await self._send_audio(remaining, self._audio_type)

        elapsed = (time.monotonic() - t0) * 1000
        duration_sec = (
            total_bytes / (SAMPLE_RATE_OUT * SAMPLE_WIDTH) if total_bytes else 0
        )
        first_ms = f"{first_audio_time:.0f}" if first_audio_time is not None else "N/A"
        logger.info(
            f"🔊 TTS done: {len(clean_text)} chars → {total_bytes} bytes "
            f"({duration_sec:.1f}s audio, first={first_ms}ms, "
            f"total={elapsed:.0f}ms)"
        )

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

    server = await asyncio.start_server(
        handle_connection,
        AUDIOSOCKET_HOST,
        AUDIOSOCKET_PORT,
    )

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"🚀 AudioSocket server listening on {addrs}")
    logger.info("   Pipeline: Whisper STT → Groq LLM → ElevenLabs TTS")
    logger.info(f"   DB: {DB_PATH}")
    logger.info("   Waiting for Asterisk connections...")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Sofia Voice — Asterisk AudioSocket Pipeline (Phase 3)")
    logger.info("=" * 60)
    asyncio.run(main())
