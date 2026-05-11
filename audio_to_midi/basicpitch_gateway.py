"""
audio_to_midi/basicpitch_gateway.py
Converte áudio WAV em MIDI usando Basic Pitch (Spotify).
Pré-processa em 22050 Hz para reduzir carga de memória.
Libera VRAM após inferência.
"""

import logging
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import librosa
    _LIBROSA_OK = True
except ImportError:
    _LIBROSA_OK = False
    logger.warning("librosa não instalado. Use: pip install librosa")

try:
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict, Model
    _BASICPITCH_OK = True
except ImportError:
    _BASICPITCH_OK = False
    logger.warning("basic-pitch não instalado. Use: pip install basic-pitch")

try:
    import tensorflow as tf
    _TF_OK = True
except ImportError:
    _TF_OK = False

try:
    from config import (
        BASICPITCH_SAMPLE_RATE,
        BASICPITCH_ONSET_THRESHOLD,
        BASICPITCH_FRAME_THRESHOLD,
        BASICPITCH_MIN_NOTE_LEN,
    )
except ImportError:
    BASICPITCH_SAMPLE_RATE     = 22050
    BASICPITCH_ONSET_THRESHOLD = 0.5
    BASICPITCH_FRAME_THRESHOLD = 0.3
    BASICPITCH_MIN_NOTE_LEN    = 58


# ─── Cache do modelo ─────────────────────────────────────────────────────────
_bp_model = None


def _get_bp_model():
    global _bp_model
    if _bp_model is None:
        logger.info("Carregando modelo BasicPitch")
        t0 = time.perf_counter()
        _bp_model = Model(ICASSP_2022_MODEL_PATH)
        logger.info(f"BasicPitch carregado em {time.perf_counter() - t0:.1f}s")
    return _bp_model


def _free_gpu():
    """Libera memória de GPU após inferência."""
    if _TF_OK:
        try:
            tf.keras.backend.clear_session()
        except Exception:
            pass
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# ─── Pré-processamento ────────────────────────────────────────────────────────

def _load_audio(wav_path: str) -> tuple[np.ndarray, int]:
    """
    Carrega áudio em mono e reamostrado para BASICPITCH_SAMPLE_RATE.
    Fallback para scipy se librosa não estiver disponível.
    """
    if _LIBROSA_OK:
        audio, sr = librosa.load(wav_path, sr=BASICPITCH_SAMPLE_RATE, mono=True)
        return audio, sr

    # Fallback mínimo: scipy
    try:
        from scipy.io import wavfile
        import scipy.signal as spsig
        sr_orig, data = wavfile.read(wav_path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype(np.float32) / 32768.0
        target_len = int(len(data) * BASICPITCH_SAMPLE_RATE / sr_orig)
        audio = spsig.resample(data, target_len)
        return audio, BASICPITCH_SAMPLE_RATE
    except Exception as e:
        raise RuntimeError(f"Falha ao carregar áudio (sem librosa nem scipy): {e}") from e


# ─── Transcrição ─────────────────────────────────────────────────────────────

def transcribe_with_basicpitch(
    wav_path: str,
    midi_out_path: str,
    onset_threshold: float = BASICPITCH_ONSET_THRESHOLD,
    frame_threshold: float = BASICPITCH_FRAME_THRESHOLD,
    min_note_len_ms: int = BASICPITCH_MIN_NOTE_LEN,
) -> list[dict]:
    """
    Transcreve WAV → MIDI.

    Retorna lista de note_events:
    [{"pitch": 60, "start_s": 1.0, "end_s": 1.5, "velocity": 80}, ...]
    """
    if not _BASICPITCH_OK:
        raise RuntimeError("basic-pitch não disponível.")

    wav_path = str(Path(wav_path).resolve())
    if not Path(wav_path).exists():
        raise FileNotFoundError(f"WAV não encontrado: {wav_path}")

    Path(midi_out_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Pré-processando áudio: {wav_path}")
    audio, sr = _load_audio(wav_path)
    logger.info(f"Áudio: {len(audio)/sr:.1f}s @ {sr} Hz | shape={audio.shape}")

    logger.info("Iniciando inferencia BasicPitch")
    t0 = time.perf_counter()

    try:
        model = _get_bp_model()
        model_output, midi_data, note_events = predict(
            audio,
            sr,
            model,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_len_ms,
            sonify_midi=False,
            save_midi=False,   # vamos salvar manualmente abaixo
        )
    finally:
        _free_gpu()

    elapsed = time.perf_counter() - t0
    logger.info(f"Inferência concluída em {elapsed:.1f}s | {len(note_events)} notas detectadas")

    # Salvar MIDI
    midi_data.write(midi_out_path)
    logger.info(f"MIDI salvo em: {midi_out_path}")

    # Converter note_events para dicionários serializáveis
    notes_out = []
    for ev in note_events:
        # note_events: (start_time_s, end_time_s, pitch, amplitude, …)
        if len(ev) >= 4:
            notes_out.append({
                "pitch":    int(ev[2]),
                "start_s":  round(float(ev[0]), 3),
                "end_s":    round(float(ev[1]), 3),
                "velocity": int(min(127, float(ev[3]) * 127)),
            })

    return notes_out


# ─── CLI rápido ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json, logging
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print("Uso: python basicpitch_gateway.py input.wav output.mid")
        sys.exit(1)
    events = transcribe_with_basicpitch(sys.argv[1], sys.argv[2])
    print(f"{len(events)} notas transcritas.")
    print(json.dumps(events[:5], indent=2))
