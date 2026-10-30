"""Gemini Live API ile gercek zamanli sesli-sesli (speech-to-speech) oturum."""

from __future__ import annotations

import asyncio
import queue
import threading
import time

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from PySide6.QtCore import QObject, Signal

from .audio import IN_RATE, OUT_RATE, Speaker, rms_of
from .config import Config
from .gemini import build_system_prompt
from .tools import ToolRegistry


class LiveEngine(QObject):
    """Arka plan thread'inde Live API oturumunu yonetir."""

    user_text = Signal(str)
    ai_text = Signal(str)
    turn_complete = Signal()
    state = Signal(str)  # connecting | listening | speaking | thinking | stopped
    level = Signal(float)
    error = Signal(str)
    notice = Signal(str)
    connected = Signal(bool)

    def __init__(self, config: Config, brain, tools: ToolRegistry, speaker: Speaker):
        super().__init__()
        self.config = config
        self.brain = brain
        self.tools = tools
        self.speaker = speaker
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session = None
        self._stop_evt = threading.Event()
        self._mic_q: queue.Queue = queue.Queue()
        self._mic_on = True
        self._minimal = False
        self._mic_stream = None
        self._last_level = 0.0

    # ------------------------------------------------------------------ dis API
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._mic_on = self.config.mic_enabled
        self._minimal = False
        self._stop_evt.clear()
        self._drain_mic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass
        self.speaker.clear()

    def set_mic(self, enabled: bool) -> None:
        self._mic_on = bool(enabled)
        if not enabled:
            self._drain_mic()

    def send_text(self, text: str) -> None:
        text = (text or "").strip()
        loop = self._loop
        if not text or loop is None or self._session is None:
            return
        asyncio.run_coroutine_threadsafe(self._send_text_async(text), loop)

    def send_image(self, jpeg: bytes) -> None:
        loop = self._loop
        if not jpeg or loop is None or self._session is None:
            return
        asyncio.run_coroutine_threadsafe(self._send_image_async(jpeg), loop)

    # ------------------------------------------------------------------ ic akis
    def _drain_mic(self) -> None:
        while True:
            try:
                self._mic_q.get_nowait()
            except queue.Empty:
                break

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        except Exception as exc:  # noqa: BLE001
            self.error.emit(self._friendly(exc))
        finally:
            self._session = None
            self._loop = None
            self.connected.emit(False)
            self.state.emit("stopped")
            try:
                loop.close()
            except Exception:
                pass

    @staticmethod
    def _friendly(exc: Exception) -> str:
        text = str(exc)
        low = text.lower()
        if "api key" in low or "permission" in low or "401" in low or "403" in low:
            return "API anahtarı geçersiz veya yetkisiz. Ayarlardan kontrol et."
        if "quota" in low or "429" in low or "resource_exhausted" in low:
            return "Kota sınırına takıldın. Bir süre sonra tekrar dene."
        if "not found" in low or "404" in low:
            return f"Model bulunamadı: {text[:160]}"
        return text[:400]

    def _build_config(self) -> types.LiveConnectConfig:
        kwargs: dict = {
            "response_modalities": ["AUDIO"],
            "system_instruction": build_system_prompt(self.config, "live"),
            "tools": [types.Tool(function_declarations=ToolRegistry.declarations())],
        }
        if self._minimal:
            return types.LiveConnectConfig(**kwargs)
        try:
            kwargs["speech_config"] = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.config.voice
                    )
                )
            )
        except Exception:
            pass
        try:
            kwargs["input_audio_transcription"] = types.AudioTranscriptionConfig()
            kwargs["output_audio_transcription"] = types.AudioTranscriptionConfig()
        except Exception:
            pass
        try:
            kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    prefix_padding_ms=40, silence_duration_ms=650
                )
            )
        except Exception:
            pass
        try:
            kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                trigger_tokens=24000,
                sliding_window=types.SlidingWindow(target_tokens=12000),
            )
        except Exception:
            pass
        try:
            return types.LiveConnectConfig(**kwargs)
        except Exception:
            for key in (
                "context_window_compression",
                "realtime_input_config",
                "input_audio_transcription",
                "output_audio_transcription",
                "speech_config",
            ):
                kwargs.pop(key, None)
                try:
                    return types.LiveConnectConfig(**kwargs)
                except Exception:
                    continue
            raise

    # ------------------------------------------------------------------ asyncio
    async def _main(self) -> None:
        if not self.config.api_key.strip():
            self.error.emit("API anahtarı yok.")
            return
        client = genai.Client(api_key=self.config.api_key.strip())
        model = self.brain.resolve("live")
        self.state.emit("connecting")
        self.notice.emit(f"Canlı oturum açılıyor: {model}")
        reconnect = 0
        while not self._stop_evt.is_set():
            try:
                await self._session_once(client, model)
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                if self._stop_evt.is_set():
                    break
                if not self._minimal:
                    # Bazi hesaplarda gelismis oturum ayarlari reddedilebiliyor.
                    self._minimal = True
                    self.notice.emit("Oturum ayarları sadeleştirilerek yeniden denenecek.")
                    await asyncio.sleep(0.6)
                    continue
                reconnect += 1
                self.error.emit(self._friendly(exc))
                if reconnect > 1:
                    break
                await asyncio.sleep(1.2)
                self.state.emit("connecting")

    async def _session_once(self, client, model: str) -> None:
        config = self._build_config()
        async with client.aio.live.connect(model=model, config=config) as session:
            self._session = session
            self._last_level = 0.0
            self.connected.emit(True)
            self.state.emit("listening")
            self._open_mic()
            tasks = [
                asyncio.create_task(self._mic_loop()),
                asyncio.create_task(self._receive_loop()),
            ]
            stop_task = asyncio.create_task(self._watch_stop())
            try:
                done, pending = await asyncio.wait(
                    [*tasks, stop_task], return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    if task is stop_task:
                        continue
                    exc = task.exception()
                    if exc:
                        raise exc
            finally:
                self._close_mic()
                self._session = None
                self.speaker.clear()

    async def _watch_stop(self) -> None:
        while not self._stop_evt.is_set():
            await asyncio.sleep(0.2)

    # -------------------------------------------------------------------- mikrofon
    def _open_mic(self) -> None:
        def cb(indata, frames, t, status):  # noqa: ANN001
            if self._stop_evt.is_set():
                return
            level = rms_of(indata)
            now = time.monotonic()
            if now - self._last_level > 0.06:
                self._last_level = now
                self.level.emit(level)
            if not self._mic_on:
                return
            # Hoparlör calarken gelen zayif sesleri yok say (yanki onleme).
            if self.speaker.is_playing and level < 0.05:
                return
            self._mic_q.put(indata.tobytes())

        try:
            self._mic_stream = sd.InputStream(
                samplerate=IN_RATE,
                channels=1,
                dtype="int16",
                blocksize=1024,
                callback=cb,
            )
            self._mic_stream.start()
        except Exception as exc:  # noqa: BLE001
            self._mic_stream = None
            self.error.emit(f"Mikrofon açılamadı: {exc}")

    def _close_mic(self) -> None:
        try:
            if self._mic_stream is not None:
                self._mic_stream.stop()
                self._mic_stream.close()
        except Exception:
            pass
        self._mic_stream = None

    async def _mic_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                chunk = await asyncio.to_thread(self._mic_q.get, True, 0.2)
            except queue.Empty:
                continue
            except Exception:
                break
            if not self._mic_on or self._session is None:
                continue
            try:
                await self._session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            except Exception:
                break

    # --------------------------------------------------------------------- alim
    async def _receive_loop(self) -> None:
        while not self._stop_evt.is_set():
            async for message in self._session.receive():
                if self._stop_evt.is_set():
                    return
                tool_call = getattr(message, "tool_call", None)
                if tool_call:
                    await self._handle_tool_call(tool_call)
                    continue
                if getattr(message, "tool_call_cancellation", None):
                    continue
                go_away = getattr(message, "go_away", None)
                if go_away:
                    self.notice.emit("Oturum süresi doluyor, yeniden bağlanılacak.")
                    continue
                content = getattr(message, "server_content", None)
                if content is None:
                    continue
                if getattr(content, "interrupted", False):
                    self.speaker.clear()
                    self.state.emit("listening")
                turn = getattr(content, "model_turn", None)
                if turn:
                    for part in turn.parts or []:
                        blob = getattr(part, "inline_data", None)
                        if blob and blob.data:
                            self.speaker.play_pcm(blob.data, OUT_RATE)
                            self.state.emit("speaking")
                in_tr = getattr(content, "input_transcription", None)
                if in_tr and getattr(in_tr, "text", None):
                    self.user_text.emit(in_tr.text)
                    self.state.emit("thinking")
                out_tr = getattr(content, "output_transcription", None)
                if out_tr and getattr(out_tr, "text", None):
                    self.ai_text.emit(out_tr.text)
                if getattr(content, "turn_complete", False):
                    self.turn_complete.emit()
                    self.state.emit("listening")
            if self._stop_evt.is_set():
                return

    async def _handle_tool_call(self, tool_call) -> None:
        responses = []
        for call in tool_call.function_calls or []:
            name = call.name
            args = dict(call.args or {})
            self.state.emit("thinking")
            self.notice.emit(f"Araç çalıştırılıyor: {name}")
            try:
                result = await asyncio.to_thread(self.tools.call, name, args)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc)}
            payload = {"result": result}
            try:
                responses.append(
                    types.FunctionResponse(id=call.id, name=name, response=payload)
                )
            except Exception:
                responses.append(types.FunctionResponse(name=name, response=payload))
        if responses and self._session is not None:
            try:
                await self._session.send_tool_response(function_responses=responses)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"Araç yanıtı gönderilemedi: {exc}")
        self.state.emit("listening")

    # ---------------------------------------------------------------- yazili giris
    async def _send_text_async(self, text: str) -> None:
        session = self._session
        if session is None:
            return
        try:
            await session.send_client_content(
                turns=[types.Content(role="user", parts=[types.Part(text=text)])],
                turn_complete=True,
            )
        except TypeError:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )
        except Exception:
            try:
                await session.send_realtime_input(text=text)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"Mesaj gönderilemedi: {exc}")

    async def _send_image_async(self, jpeg: bytes) -> None:
        session = self._session
        if session is None:
            return
        blob = types.Blob(data=jpeg, mime_type="image/jpeg")
        try:
            await session.send_realtime_input(video=blob)
        except Exception:
            try:
                await session.send_realtime_input(media=blob)
            except Exception:
                pass
