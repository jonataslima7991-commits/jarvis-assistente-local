from __future__ import annotations

import asyncio
import hashlib
import queue
import sys
import threading
from pathlib import Path

import edge_tts
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from config import settings

# ── STT constants ─────────────────────────────────────────────────────────────
_SAMPLE_RATE  = 16000
_CHUNK        = 1024
_SILENCE_RMS  = 0.00040  # limiar de detecção de voz (baixo para mics de ganho médio)
_SILENCE_SEC  = 0.55     # silêncio após fala para cortar
_MIN_SPEECH   = 3        # chunks mínimos (~190 ms) de voz antes de transcrever

# ── TTS constants ─────────────────────────────────────────────────────────────
_TTS_RATE = 22050

# ── TTS cache — evita re-sintetizar frases repetidas via edge-tts ──────────────
_TTS_CACHE_DIR       = Path.home() / ".jarvis_tts_cache"
_TTS_CACHE_MAX_FILES = 300


def _tts_cache_path(text: str, voice: str) -> Path:
    key = hashlib.sha1(f"{text}|{voice}".encode("utf-8")).hexdigest()
    return _TTS_CACHE_DIR / f"{key}.mp3"


def _tts_cache_evict() -> None:
    files = sorted(_TTS_CACHE_DIR.glob("*.mp3"), key=lambda p: p.stat().st_atime)
    if len(files) > _TTS_CACHE_MAX_FILES:
        for f in files[: len(files) - _TTS_CACHE_MAX_FILES]:
            try:
                f.unlink()
            except OSError:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────
def _jarvis_effect(samples: np.ndarray, sr: int) -> np.ndarray:
    n = len(samples)
    stretched = np.interp(
        np.linspace(0, n - 1, int(n / 0.96)), np.arange(n), samples
    )
    out = stretched[:n].astype(np.float32)
    d1 = int(0.030 * sr)
    rev = np.zeros(n, dtype=np.float32)
    rev[d1:] = out[:-d1] * 0.14
    out = out + rev
    mx = np.max(np.abs(out))
    return (out / mx * 0.92).astype(np.float32) if mx > 0 else out


def _get_output_samplerate() -> int:
    try:
        return int(sd.query_devices(kind="output").get("default_samplerate", 44100))
    except Exception:
        return 44100


def _resample(samples: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    if from_sr == to_sr:
        return samples
    n_out = int(len(samples) * to_sr / from_sr)
    return np.interp(
        np.linspace(0, len(samples) - 1, n_out), np.arange(len(samples)), samples
    ).astype(np.float32)


def _resolve_mic_device():
    cfg = settings.mic_device.strip()
    if not cfg:
        return None
    try:
        return int(cfg)
    except ValueError:
        pass
    cfg_low = cfg.lower()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and cfg_low in d["name"].lower():
            return i
    print(f"[STT] MIC_DEVICE='{cfg}' não encontrado, usando padrão.", flush=True)
    return None


def _is_hallucination(text: str, audio_sec: float) -> bool:
    words = text.split()
    if len(words) > audio_sec * 3.5 + 5:
        return True
    if len(words) >= 8:
        phrase = " ".join(words[:4])
        if text.count(phrase) >= 3:
            return True
    return False


_INITIAL_PROMPT = (
    "JARVIS. Abre o chrome. Fecha o spotify. Pesquisa no Google. "
    "Volume em 50. Timer de 10 minutos. Status do sistema. "
    "Lembra que. Lê a tela. Contexto do VSCode. "
    "Agende uma reunião amanhã às 15h. Cancela a reunião com o cliente. "
    "Muda a reunião para 16h. Qual a minha agenda? O que tenho marcado essa semana? "
    "Tenho e-mail novo? Lê meu último e-mail. Manda um e-mail para o professor."
)


def _transcribe(model: WhisperModel, audio: np.ndarray) -> tuple[str, float]:
    """Transcreve e retorna (texto, no_speech_prob)."""
    segments, _ = model.transcribe(
        audio,
        language="pt",
        beam_size=2,
        temperature=0,
        condition_on_previous_text=False,
        no_speech_threshold=0.60,
        initial_prompt=_INITIAL_PROMPT,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )
    parts: list[str] = []
    max_ns = 0.0
    for seg in segments:
        max_ns = max(max_ns, seg.no_speech_prob)
        parts.append(seg.text)
    return " ".join(parts).strip(), max_ns


# ── TTS Engine ────────────────────────────────────────────────────────────────
class TTSEngine:
    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, threading.Event] | None] = queue.Queue()
        self._out_sr = _get_output_samplerate()
        print(f"[TTS] Dispositivo de saída: {sd.query_devices(kind='output')['name']}")
        print(f"[TTS] Sample rate de saída: {self._out_sr} Hz")
        threading.Thread(target=self._worker, daemon=True, name="TTS-worker").start()

    def speak(self, text: str, on_level=None) -> None:
        self.speak_async(text, on_level=on_level).wait()

    def speak_async(self, text: str, on_level=None) -> threading.Event:
        """Enfileira fala sem bloquear. Retorna Event que dispara ao terminar."""
        done = threading.Event()
        self._queue.put((text, done, on_level))
        return done

    def _worker(self) -> None:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            item = self._queue.get()
            if item is None:
                break
            text, done, on_level = item
            try:
                loop.run_until_complete(self._async_speak(text, on_level))
            except Exception as exc:
                print(f"[TTS ERRO] {exc}", flush=True)
            finally:
                done.set()

    async def _async_speak(self, text: str, on_level=None) -> None:
        _TTS_CACHE_DIR.mkdir(exist_ok=True)
        cache_path = _tts_cache_path(text, settings.voice)
        if not cache_path.exists():
            communicate = edge_tts.Communicate(text, settings.voice, rate="+15%")
            await communicate.save(str(cache_path))
            _tts_cache_evict()
        self._play(str(cache_path), on_level=on_level)

    def _play(self, mp3_path: str, on_level=None) -> None:
        import miniaudio
        decoded   = miniaudio.decode_file(
            mp3_path, output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1, sample_rate=_TTS_RATE,
        )
        samples   = np.frombuffer(decoded.samples, dtype=np.float32).copy()
        processed = _jarvis_effect(samples, _TTS_RATE)
        out       = _resample(processed, _TTS_RATE, self._out_sr)

        if on_level is None:
            sd.play(out, samplerate=self._out_sr, blocking=True)
            return

        # Callback-based playback — mede RMS em tempo real
        pos   = [0]
        ended = threading.Event()

        def _cb(outdata: np.ndarray, frames: int, _t, _s) -> None:
            n = min(frames, len(out) - pos[0])
            outdata[:n, 0] = out[pos[0]: pos[0] + n]
            if n < frames:
                outdata[n:, 0] = 0.0
            rms = float(np.sqrt(np.mean(outdata[:n, 0] ** 2))) if n > 0 else 0.0
            on_level(min(rms * 5.0, 1.0))
            pos[0] += n
            if pos[0] >= len(out):
                ended.set()
                raise sd.CallbackStop()

        with sd.OutputStream(
            samplerate=self._out_sr, channels=1, dtype="float32",
            blocksize=2048, callback=_cb,
        ):
            ended.wait()


# ── STT Engine ────────────────────────────────────────────────────────────────
class STTEngine:
    """faster-whisper base int8 — transcrição de comandos direta, sem wake word."""

    def __init__(self) -> None:
        self._cmd:    WhisperModel | None = None
        self._device = None

    def _load(self) -> None:
        if self._cmd is not None:
            return

        self._device = _resolve_mic_device()

        try:
            devs = sd.query_devices()
            print("[STT] Entradas disponíveis:", flush=True)
            for i, d in enumerate(devs):
                if d["max_input_channels"] > 0:
                    mark = " ◄ USANDO" if i == self._device else ""
                    print(f"         [{i}] {d['name']}{mark}", flush=True)
            if self._device is None:
                print(f"[STT] Usando padrão: {sd.query_devices(kind='input')['name']}", flush=True)
        except Exception:
            pass

        model_size = settings.whisper_model
        print(f"[STT] Carregando faster-whisper {model_size}...", flush=True)
        self._cmd = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("[STT] Pronto. Limiar RMS:", _SILENCE_RMS, flush=True)

    # ── Public API ────────────────────────────────────────────────────────────
    def listen(self, timeout: float = 15.0, fast: bool = False, on_level=None) -> str | None:
        self._load()
        audio = self._record(timeout, on_level=on_level)
        if audio is None:
            return None

        peak = float(np.max(np.abs(audio)))
        if peak < 0.002:
            return None

        audio_norm = (audio / peak * 0.85).astype(np.float32)
        text, no_sp = _transcribe(self._cmd, audio_norm)

        if no_sp > 0.60 or not text:
            return None

        audio_sec = len(audio) / _SAMPLE_RATE
        if _is_hallucination(text, audio_sec):
            print(f"[STT] Alucinação ignorada ({len(text.split())} palavras / {audio_sec:.1f}s)", flush=True)
            return None

        print(f"[STT] '{text}'  (no_speech={no_sp:.2f})", flush=True)
        return text

    # ── Recording ─────────────────────────────────────────────────────────────
    def _record(self, timeout: float, on_level=None) -> np.ndarray | None:
        q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata: np.ndarray, frames: int, time, status) -> None:
            if status:
                print(f"[MIC] {status}", flush=True)
            chunk = indata[:, 0].copy()
            q.put(chunk)
            if on_level is not None:
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                on_level(min(rms * 8.0, 1.0))

        frames: list[np.ndarray] = []
        speech_chunks = 0
        silent_chunks = 0
        max_silent = int(_SILENCE_SEC * _SAMPLE_RATE / _CHUNK)
        max_total  = int(timeout   * _SAMPLE_RATE / _CHUNK)
        log_every  = int(0.5       * _SAMPLE_RATE / _CHUNK)   # log a cada 0.5s
        _peak_rms  = 0.0

        try:
            with sd.InputStream(
                device=self._device,
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=_CHUNK,
                callback=callback,
            ):
                for i in range(max_total):
                    chunk = q.get()
                    rms   = float(np.sqrt(np.mean(chunk ** 2)))
                    _peak_rms = max(_peak_rms, rms)

                    if rms > _SILENCE_RMS:
                        if speech_chunks == 0:
                            print(f"[MIC] >>> VOZ DETECTADA  RMS={rms:.4f}", flush=True)
                        frames.append(chunk)
                        speech_chunks += 1
                        silent_chunks  = 0
                    elif speech_chunks > 0:
                        frames.append(chunk)
                        silent_chunks += 1
                        if silent_chunks >= max_silent:
                            break
                    else:
                        if i % log_every == 0:
                            bar = "█" * min(int(rms / _SILENCE_RMS * 10), 10)
                            print(f"[MIC] aguardando... RMS={rms:.5f}  limiar={_SILENCE_RMS}  [{bar:<10}]", flush=True)
        except Exception as exc:
            print(f"[STT ERRO] {exc}", flush=True)
            return None

        if _peak_rms < _SILENCE_RMS and speech_chunks == 0:
            print(f"[MIC] AVISO: pico máximo={_peak_rms:.5f} ficou abaixo do limiar={_SILENCE_RMS}. "
                  f"Tente falar mais alto ou ajuste MIC_DEVICE no .env", flush=True)

        if speech_chunks < _MIN_SPEECH:
            return None
        return np.concatenate(frames)


# ── Wake word engine ──────────────────────────────────────────────────────────
_WAKE_CHUNK     = 1280   # 80 ms @ 16 kHz — tamanho exigido pelo openWakeWord
_WAKE_THRESHOLD = 0.5


class WakeWordDetector:
    """Detecta 'hey jarvis' continuamente com custo de CPU quase nulo (openWakeWord),
    eliminando a necessidade de rodar Whisper só para checar a wake word."""

    def __init__(self) -> None:
        self._model:  "object | None" = None
        self._device = None

    def load(self) -> None:
        if self._model is not None:
            return
        import openwakeword.utils as oww_utils
        from openwakeword.model import Model

        oww_utils.download_models(["hey_jarvis"])
        self._model  = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        self._device = _resolve_mic_device()
        print("[WAKE] openWakeWord pronto (hey_jarvis)", flush=True)

    def wait(self, stop_check) -> bool:
        """Bloqueia até detectar a wake word. Retorna False se stop_check() virar True antes."""
        self.load()
        q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata: np.ndarray, frames: int, time, status) -> None:
            if status:
                print(f"[WAKE] {status}", flush=True)
            q.put(indata[:, 0].copy())

        try:
            with sd.InputStream(
                device=self._device,
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=_WAKE_CHUNK,
                callback=callback,
            ):
                while not stop_check():
                    try:
                        chunk = q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    pred  = self._model.predict(chunk)
                    score = pred.get("hey_jarvis", 0.0)
                    if score > _WAKE_THRESHOLD:
                        self._model.reset()
                        print(f"[WAKE] 'hey jarvis' detectado (score={score:.2f})", flush=True)
                        return True
        except Exception as exc:
            print(f"[WAKE ERRO] {exc}", flush=True)
            return False
        return False
