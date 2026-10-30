"""Ses katmani: mikrofondan PCM yakalama, hoparlore PCM/WAV calma ve VAD."""

from __future__ import annotations

import io
import queue
import threading
import time
import wave

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal

IN_RATE = 16000
OUT_RATE = 24000
BLOCK = 1024  # ~64 ms @ 16 kHz


# ------------------------------------------------------------------- yardimcilar
def pcm_to_wav(pcm: bytes, rate: int = IN_RATE, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_payload(data: bytes) -> tuple[bytes, int, int]:
    """WAV ise (pcm, rate, kanal); degilse dokunmadan 24k mono varsayar."""
    if not data or data[:4] != b"RIFF":
        return data, OUT_RATE, 1
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            return wf.readframes(wf.getnframes()), wf.getframerate(), wf.getnchannels()
    except Exception:
        return data, OUT_RATE, 1


def resample_pcm(pcm: bytes, src: int, dst: int, channels: int = 1) -> bytes:
    if src == dst or not pcm:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    n_out = int(round(len(samples) * dst / src))
    if n_out <= 1:
        return b""
    idx = np.linspace(0, len(samples) - 1, n_out)
    out = np.interp(idx, np.arange(len(samples)), samples).astype(np.int16)
    return out.tobytes()


def rms_of(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    data = block.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(np.square(data))))


# ------------------------------------------------------------------- hoparlor
class Speaker:
    """Kuyruga atilan PCM/WAV sesleri tek bir cikis akisinda calar."""

    def __init__(self, rate: int = OUT_RATE):
        self.rate = rate
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stream = None
        self._stop = threading.Event()
        self._last_write = 0.0
        self._lock = threading.Lock()
        self._error_sent = False
        self._out_rate = rate
        self.on_error = None

    def _ensure_stream(self):
        """Cikis akisini acar; cihaz 24 kHz desteklemiyorsa baska oran dener."""
        if self._stream is not None:
            return self._stream
        last_error = None
        for rate in (self.rate, 48000, 44100):
            try:
                stream = sd.RawOutputStream(
                    samplerate=rate, channels=1, dtype="int16", blocksize=0
                )
                stream.start()
                self._stream = stream
                self._out_rate = rate
                self._error_sent = False
                return stream
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise last_error or RuntimeError("Ses cihazı açılamadı")

    def _worker(self):
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                continue
            try:
                stream = self._stream
                if stream is None:
                    continue
                for i in range(0, len(item), 8192):
                    if self._stop.is_set():
                        break
                    stream.write(item[i : i + 8192])
                    self._last_write = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                if not self._error_sent and self.on_error:
                    self._error_sent = True
                    self.on_error(f"Ses çıkışı hatası: {exc}")

    def _start(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()

    def play_pcm(self, pcm: bytes, rate: int = OUT_RATE):
        if not pcm:
            return
        try:
            with self._lock:
                self._ensure_stream()
                data = resample_pcm(pcm, rate, self._out_rate) if rate != self._out_rate else pcm
                self._queue.put(data)
            self._start()
        except Exception as exc:  # noqa: BLE001
            if not self._error_sent and self.on_error:
                self._error_sent = True
                self.on_error(f"Ses çıkışı hatası: {exc}")

    def play_wav(self, data: bytes):
        pcm, rate, channels = wav_payload(data)
        if channels > 1:
            pcm = resample_pcm(pcm, rate, rate, channels)
        self.play_pcm(pcm, rate)

    def play_file(self, path: str):
        try:
            with open(path, "rb") as fh:
                self.play_wav(fh.read())
        except Exception:
            pass

    def clear(self):
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._last_write = 0.0

    @property
    def is_playing(self) -> bool:
        return not self._queue.empty() or (time.monotonic() - self._last_write) < 0.25

    def stop(self):
        self._stop.set()
        self.clear()
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None


# --------------------------------------------------------------- mikrofon + VAD
class VoiceListener(QObject):
    """Mikrofonu dinler, konusma bitince WAV klip olarak yayinlar."""

    clip_ready = Signal(bytes)
    level = Signal(float)
    error = Signal(str)

    def __init__(self, threshold: float = 0.016, silence_s: float = 0.65, max_s: float = 8.0):
        super().__init__()
        self.threshold = threshold
        self.silence_frames = max(4, int(silence_s * IN_RATE / BLOCK))
        self.max_frames = int(max_s * IN_RATE / BLOCK)
        self.gate = None  # callable -> True ise ses yok sayilir
        self._thread: threading.Thread | None = None
        self._stream = None
        self._stop = threading.Event()
        self._buffer: list[bytes] = []
        self._pre: list[bytes] = []
        self._silence = 0
        self._recording = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread = None

    def _run(self):
        def callback(indata, frames, t, status):  # noqa: ANN001
            if self._stop.is_set():
                return
            try:
                level = rms_of(indata)
                self.level.emit(level)
                ignore = bool(self.gate and self.gate())
                chunk = indata.tobytes()
                if ignore:
                    self._buffer = []
                    self._pre = []
                    self._recording = False
                    self._silence = 0
                    return
                if not self._recording:
                    self._pre.append(chunk)
                    self._pre = self._pre[-3:]
                    if level > self.threshold:
                        self._recording = True
                        self._buffer = list(self._pre)
                        self._silence = 0
                    return
                self._buffer.append(chunk)
                if level > self.threshold * 0.85:
                    self._silence = 0
                else:
                    self._silence += 1
                if self._silence >= self.silence_frames or len(self._buffer) >= self.max_frames:
                    pcm = b"".join(self._buffer)
                    self._buffer = []
                    self._pre = []
                    self._recording = False
                    self._silence = 0
                    if len(pcm) > IN_RATE * 0.3 * 2:  # en az ~0.3 sn
                        self.clip_ready.emit(pcm_to_wav(pcm, IN_RATE))
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

        try:
            self._stream = sd.InputStream(
                samplerate=IN_RATE,
                channels=1,
                dtype="int16",
                blocksize=BLOCK,
                callback=callback,
            )
            self._stream.start()
            while not self._stop.is_set():
                time.sleep(0.1)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Mikrofon açılamadı: {exc}")
        finally:
            try:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
            except Exception:
                pass
            self._stream = None
