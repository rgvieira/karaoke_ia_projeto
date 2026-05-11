"""
config.py — Configurações centralizadas do projeto Karaokê IA
Detecta automaticamente GPU/CPU e ajusta parâmetros.
"""

import os

try:
    import torch
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False

# ─── Caminhos ─────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR   = os.path.join(BASE_DIR, "output", "outputs")

INPUT_WAV       = os.path.join(OUTPUT_DIR, "voz_capturada.wav")
OUTPUT_MIDI_1   = os.path.join(OUTPUT_DIR, "partitura_etapa1.mid")
OUTPUT_MIDI_2   = os.path.join(OUTPUT_DIR, "partitura_etapa2.mid")
OUTPUT_JSON     = os.path.join(OUTPUT_DIR, "projeto_karaoke.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Detecção de Hardware ─────────────────────────────────────────────────────
_CUDA_AVAILABLE   = _TORCH_OK and torch.cuda.is_available()
_VRAM_GB          = (
    torch.cuda.get_device_properties(0).total_memory / 1e9
    if _CUDA_AVAILABLE else 0
)

# ─── Whisper ──────────────────────────────────────────────────────────────────
# Ajuste automático: large só se VRAM >= 6 GB, medium se >= 4 GB
if _VRAM_GB >= 6:
    WHISPER_MODEL_SIZE = "medium"
elif _VRAM_GB >= 4:
    WHISPER_MODEL_SIZE = "small"
else:
    WHISPER_MODEL_SIZE = "small"          # seguro para CPU

WHISPER_DEVICE          = "cuda" if _CUDA_AVAILABLE else "cpu"
WHISPER_COMPUTE_TYPE    = "float16" if _CUDA_AVAILABLE else "int8"
WHISPER_VAD_FILTER      = True
WHISPER_WORD_TIMESTAMPS = True           # timestamps por palavra (karaokê)
WHISPER_BEAM_SIZE       = 1              # rápido — aumentar para 5 se precisar de mais precisão
WHISPER_LANGUAGE        = "pt"           # idioma padrão

# ─── BasicPitch ───────────────────────────────────────────────────────────────
BASICPITCH_SAMPLE_RATE      = 22050      # reduz carga; original é 44100
BASICPITCH_ONSET_THRESHOLD  = 0.5
BASICPITCH_FRAME_THRESHOLD  = 0.3
BASICPITCH_MIN_NOTE_LEN     = 58         # ms — filtra ruído
BASICPITCH_MIDI_TEMPO       = 120        # BPM padrão

# ─── Correção MIDI ────────────────────────────────────────────────────────────
MIDI_QUANTIZATION_GRID  = 0.125          # 1/8 de batida
MIDI_MIN_NOTE_DURATION  = 0.05          # segundos
MIDI_KEY_DETECTION      = True           # usa librosa para detectar tonalidade
MIDI_MAX_POLYPHONY      = 1             # voz solo — remove acordes improváveis

# ─── Captura de Áudio ─────────────────────────────────────────────────────────
CAPTURE_SAMPLE_RATE     = 44100
CAPTURE_CHANNELS        = 1
CAPTURE_CHUNK_SIZE      = 1024
CAPTURE_FORMAT          = "wav"
CAPTURE_LOOPBACK        = True           # tenta loopback; fallback = microfone
CAPTURE_NOISE_REDUCE    = True           # aplica noisereduce se loopback falhar

# ─── API ──────────────────────────────────────────────────────────────────────
API_HOST    = "127.0.0.1"
API_PORT    = 8000
API_RELOAD  = False

# ─── Diagnóstico ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Torch instalado: {_TORCH_OK}")
    print(f"GPU disponível : {_CUDA_AVAILABLE}")
    print(f"VRAM           : {_VRAM_GB:.1f} GB")
    print(f"Whisper device : {WHISPER_DEVICE} / {WHISPER_COMPUTE_TYPE}")
    print(f"Whisper model  : {WHISPER_MODEL_SIZE}")
    print(f"Output dir     : {OUTPUT_DIR}")
