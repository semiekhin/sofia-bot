"""
voice_asterisk.py — AudioSocket сервер для Asterisk → Sofia Voice Pipeline

Фаза 2: Приём аудио от Asterisk через AudioSocket, отправка тишины обратно.
Фаза 3: STT → LLM → TTS pipeline.

Asterisk AudioSocket protocol (TCP):
  Packet: [1 byte type] [2 bytes length BE] [payload]
  Types:  0x01=hangup, 0x10=UUID, 0x11=audio, 0x12=silence, 0xFF=error
  Audio:  signed linear 16-bit PCM, 8kHz mono (from G.711 channels)

Запуск: /opt/sofia-voice/venv/bin/python3 voice_asterisk.py
"""

import asyncio
import struct
import time
from loguru import logger

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

# Audio params: Asterisk sends slin (signed linear 16-bit) at 8kHz
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes per sample
CHANNELS = 1


# ============================================================
# AudioSocket Connection Handler
# ============================================================


class AudioSocketCall:
    """Handles one AudioSocket connection (one phone call)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.call_uuid: str | None = None
        self.caller_id: str = "unknown"
        self.start_time = time.time()
        self.audio_frames_received = 0
        self.audio_bytes_received = 0
        self._closed = False

    async def run(self):
        """Main loop: read packets from Asterisk, process them."""
        peer = self.writer.get_extra_info("peername")
        logger.info(f"📞 New AudioSocket connection from {peer}")

        try:
            while not self._closed:
                # Read 3-byte header: [1 byte type] [2 bytes length BE]
                header = await self.reader.readexactly(3)
                msg_type = header[0]
                msg_len = struct.unpack(">H", header[1:3])[0]

                # Read payload
                payload = b""
                if msg_len > 0:
                    payload = await self.reader.readexactly(msg_len)

                await self._handle_packet(msg_type, payload)

        except asyncio.IncompleteReadError:
            logger.info(
                f"📞 Connection closed by Asterisk (call_uuid={self.call_uuid})"
            )
        except ConnectionResetError:
            logger.info(f"📞 Connection reset (call_uuid={self.call_uuid})")
        except Exception as e:
            logger.error(f"❌ AudioSocket error: {e}")
        finally:
            await self._cleanup()

    async def _handle_packet(self, msg_type: int, payload: bytes):
        if msg_type == AS_TYPE_UUID:
            # UUID is 16 bytes binary, convert to standard string format
            if len(payload) == 16:
                import uuid as _uuid

                self.call_uuid = str(_uuid.UUID(bytes=payload))
            else:
                self.call_uuid = payload.hex()
            logger.info(f"📞 Call UUID: {self.call_uuid}")

        elif msg_type in (AS_TYPE_AUDIO, AS_TYPE_AUDIO_16K):
            self.audio_frames_received += 1
            self.audio_bytes_received += len(payload)

            # Detect sample rate from type
            if msg_type == AS_TYPE_AUDIO_16K:
                self._audio_rate = 16000
            elif msg_type == AS_TYPE_AUDIO:
                self._audio_rate = 8000
            self._audio_type = msg_type

            # Log periodically (every ~1 second at 8kHz, 20ms frames = 50 frames/sec)
            if self.audio_frames_received % 50 == 1:
                elapsed = time.time() - self.start_time
                logger.info(
                    f"🎤 Audio: frame #{self.audio_frames_received}, "
                    f"{len(payload)} bytes, rate={getattr(self, '_audio_rate', '?')}Hz, "
                    f"total {self.audio_bytes_received} bytes, "
                    f"elapsed {elapsed:.1f}s"
                )

            # Phase 2: send silence back (same type and length as received)
            # This keeps the call alive — client hears silence, not busy tone
            await self._send_audio(b"\x00" * len(payload), msg_type)

        elif msg_type == AS_TYPE_HANGUP:
            logger.info(f"📞 Hangup received (call_uuid={self.call_uuid})")
            self._closed = True

        elif msg_type == AS_TYPE_ERROR:
            error_msg = (
                payload.decode("utf-8", errors="replace") if payload else "unknown"
            )
            logger.error(f"❌ Asterisk error: {error_msg}")
            self._closed = True

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
            f"audio_bytes={self.audio_bytes_received}"
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
    server = await asyncio.start_server(
        handle_connection,
        AUDIOSOCKET_HOST,
        AUDIOSOCKET_PORT,
    )

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"🚀 AudioSocket server listening on {addrs}")
    logger.info(f"   Audio format: slin16, {SAMPLE_RATE}Hz, {CHANNELS}ch")
    logger.info("   Waiting for Asterisk connections...")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Sofia Voice — AudioSocket Server (Phase 2)")
    logger.info("=" * 60)
    asyncio.run(main())
