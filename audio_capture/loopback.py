"""
audio_capture/loopback.py
Captura áudio do sistema via WASAPI loopback (Windows).
Fallback automático para microfone com redução de ruído se loopback falhar.
"""

import os
import wave
import time
import threading
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Importações opcionais — não aborta se ausentes
try:
    import pyaudio
    _PYAUDIO_OK = True
except ImportError:
    _PYAUDIO_OK = False
    logger.warning("pyaudio não instalado. Use: pip install pyaudio")

try:
    import noisereduce as nr
    _NR_OK = True
except ImportError:
    _NR_OK = False

try:
    from config import (
        CAPTURE_SAMPLE_RATE, CAPTURE_CHANNELS,
        CAPTURE_CHUNK_SIZE, CAPTURE_LOOPBACK, CAPTURE_NOISE_REDUCE,
        INPUT_WAV,
    )
except ImportError:
    CAPTURE_SAMPLE_RATE  = 44100
    CAPTURE_CHANNELS     = 1
    CAPTURE_CHUNK_SIZE   = 1024
    CAPTURE_LOOPBACK     = True
    CAPTURE_NOISE_REDUCE = True
    INPUT_WAV            = "output/outputs/voz_capturada.wav"


# ─── Utilitários ──────────────────────────────────────────────────────────────

def _find_loopback_device(pa: "pyaudio.PyAudio") -> int | None:
    """Retorna índice do primeiro dispositivo WASAPI loopback disponível."""
    wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    dev_count   = wasapi_info["deviceCount"]

    for i in range(dev_count):
        dev = pa.get_device_info_by_host_api_device_index(
            wasapi_info["index"], i
        )
        # Dispositivos loopback têm maxInputChannels > 0 e nome contém "Loopback"
        if dev.get("maxInputChannels", 0) > 0 and "loopback" in dev["name"].lower():
            logger.info(f"Dispositivo loopback encontrado: {dev['name']} (idx={i})")
            return dev["index"]

    # Fallback: qualquer saída padrão com loopback implícito
    default_out = wasapi_info.get("defaultOutputDevice", -1)
    if default_out >= 0:
        logger.warning("Loopback explícito não encontrado. Tentando saída padrão como loopback.")
        return default_out

    return None


def _find_microphone(pa: "pyaudio.PyAudio") -> int:
    """Retorna índice do microfone padrão."""
    default = pa.get_default_input_device_info()
    logger.info(f"Microfone padrão: {default['name']}")
    return default["index"]


def _apply_noise_reduction(audio_np: np.ndarray, rate: int) -> np.ndarray:
    """Reduz ruído de fundo usando noisereduce (se disponível)."""
    if not _NR_OK or not CAPTURE_NOISE_REDUCE:
        return audio_np
    # Usa os primeiros 0.5s como amostra de ruído
    noise_sample = audio_np[: int(rate * 0.5)]
    return nr.reduce_noise(y=audio_np, sr=rate, y_noise=noise_sample, stationary=True)


def _save_wav(frames: list[bytes], rate: int, channels: int, path: str):
    """Salva frames PCM em arquivo WAV."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # Converter para numpy para eventual pós-processamento
    audio_np = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
    audio_np = _apply_noise_reduction(audio_np, rate)

    # Normalização leve para evitar clipping
    peak = np.max(np.abs(audio_np))
    if peak > 0:
        audio_np = audio_np * (0.95 / peak)

    pcm = (audio_np * 32768).astype(np.int16).tobytes()

    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(rate)
        wf.writeframes(pcm)

    logger.info(f"Áudio salvo em: {path} ({len(pcm) // 2 // rate:.1f}s)")


# ─── Captura Principal ────────────────────────────────────────────────────────

class AudioCapture:
    """
    Captura áudio do sistema (loopback WASAPI) com fallback para microfone.

    Uso:
        cap = AudioCapture()
        cap.start()
        time.sleep(10)
        cap.stop()
    """

    def __init__(self, output_path: str = INPUT_WAV, duration: float | None = None):
        self.output_path  = output_path
        self.duration     = duration         # None = manual (chamar .stop())
        self._frames: list[bytes] = []
        self._stream      = None
        self._pa          = None
        self._thread      = None
        self._stop_event  = threading.Event()
        self._mode        = "loopback"       # ou "microphone"

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    def start(self):
        if not _PYAUDIO_OK:
            raise RuntimeError("pyaudio não está instalado.")

        self._pa = pyaudio.PyAudio()
        device_idx, loopback = self._resolve_device()
        self._mode = "loopback" if loopback else "microphone"

        self._stream = self._pa.open(
            format              = pyaudio.paInt16,
            channels            = CAPTURE_CHANNELS,
            rate                = CAPTURE_SAMPLE_RATE,
            input               = True,
            input_device_index  = device_idx,
            frames_per_buffer   = CAPTURE_CHUNK_SIZE,
            as_loopback         = loopback,   # parâmetro WASAPI
        )

        logger.info(f"Iniciando captura [{self._mode}] @ {CAPTURE_SAMPLE_RATE} Hz")
        self._stop_event.clear()
        self._frames.clear()

        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

        if self.duration:
            # Para automaticamente após `duration` segundos
            threading.Timer(self.duration, self.stop).start()

    def stop(self) -> str:
        """Para captura e salva WAV. Retorna caminho do arquivo."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()

        _save_wav(self._frames, CAPTURE_SAMPLE_RATE, CAPTURE_CHANNELS, self.output_path)
        return self.output_path

    # ─── Internos ─────────────────────────────────────────────────────────────

    def _resolve_device(self) -> tuple[int, bool]:
        """Retorna (device_index, is_loopback)."""
        if CAPTURE_LOOPBACK:
            try:
                idx = _find_loopback_device(self._pa)
                if idx is not None:
                    return idx, True
            except Exception as e:
                logger.warning(f"Loopback falhou ({e}). Usando microfone.")

        return _find_microphone(self._pa), False

    def _record_loop(self):
        while not self._stop_event.is_set():
            try:
                data = self._stream.read(CAPTURE_CHUNK_SIZE, exception_on_overflow=False)
                self._frames.append(data)
            except IOError as e:
                logger.error(f"Erro de leitura de áudio: {e}")
                break


# ─── API de Conveniência ──────────────────────────────────────────────────────

def capture_audio(duration: float, output_path: str = INPUT_WAV) -> str:
    """Captura `duration` segundos de áudio e retorna o caminho do WAV."""
    cap = AudioCapture(output_path=output_path, duration=duration)
    cap.start()
    # Aguarda conclusão (+0.5s de margem)
    time.sleep(duration + 0.5)
    return cap.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Capturando 5 segundos de áudio...")
    path = capture_audio(5)
    print(f"Salvo em: {path}")
