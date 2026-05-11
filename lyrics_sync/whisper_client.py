"""
lyrics_sync/whisper_client.py
Transcrição de áudio com faster-whisper.
Cache singleton do modelo para evitar overhead de re-carregamento.
Suporte a timestamps por palavra para sincronização de karaokê.
"""

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except ImportError:
    _WHISPER_OK = False
    logger.warning("faster-whisper não instalado. Use: pip install faster-whisper")

try:
    from config import (
        WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
        WHISPER_VAD_FILTER, WHISPER_WORD_TIMESTAMPS,
        WHISPER_BEAM_SIZE, WHISPER_LANGUAGE,
    )
except ImportError:
    WHISPER_MODEL_SIZE      = "small"
    WHISPER_DEVICE          = "cpu"
    WHISPER_COMPUTE_TYPE    = "int8"
    WHISPER_VAD_FILTER      = True
    WHISPER_WORD_TIMESTAMPS = True
    WHISPER_BEAM_SIZE       = 1
    WHISPER_LANGUAGE        = "pt"


# ─── Cache Singleton ──────────────────────────────────────────────────────────

_model_cache: dict[str, "WhisperModel"] = {}


def get_model(
    model_size: str = WHISPER_MODEL_SIZE,
    device: str = WHISPER_DEVICE,
    compute_type: str = WHISPER_COMPUTE_TYPE,
) -> "WhisperModel":
    """
    Carrega o modelo Whisper uma única vez e mantém em cache.
    Chamadas subsequentes retornam a instância existente.
    """
    if not _WHISPER_OK:
        raise RuntimeError("faster-whisper não está disponível.")

    cache_key = f"{model_size}:{device}:{compute_type}"
    if cache_key not in _model_cache:
        logger.info(f"Carregando Whisper '{model_size}' [{device}/{compute_type}]")
        t0 = time.perf_counter()
        _model_cache[cache_key] = WhisperModel(
            model_size, device=device, compute_type=compute_type
        )
        logger.info(f"Whisper carregado em {time.perf_counter() - t0:.1f}s")

    return _model_cache[cache_key]


def unload_model():
    """Libera todos os modelos do cache (útil em ambientes com pouca RAM)."""
    _model_cache.clear()
    logger.info("Cache Whisper limpo.")


# ─── Transcrição ─────────────────────────────────────────────────────────────

def transcribe(
    audio_path: str,
    language: Optional[str] = WHISPER_LANGUAGE,
    word_timestamps: bool = WHISPER_WORD_TIMESTAMPS,
    vad_filter: bool = WHISPER_VAD_FILTER,
    beam_size: int = WHISPER_BEAM_SIZE,
) -> dict:
    """
    Transcreve áudio e retorna dicionário com segmentos e palavras.

    Retorno:
    {
      "language": "pt",
      "duration_s": 45.2,
      "segments": [
        {
          "text": "linha da letra",
          "start": 1.2,
          "end": 3.4,
          "words": [
            {"w": "linha", "s": 1200, "e": 1600},
            {"w": "da",    "s": 1620, "e": 1700},
            {"w": "letra", "s": 1720, "e": 2100},
          ]
        }
      ]
    }
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

    model = get_model()
    logger.info(f"Transcrevendo: {path.name} (language={language}, beam={beam_size})")
    t0 = time.perf_counter()

    segments_gen, info = model.transcribe(
        str(path),
        language=language,
        vad_filter=vad_filter,
        word_timestamps=word_timestamps,
        beam_size=beam_size,
        condition_on_previous_text=True,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
    )

    result_segments = []
    for seg in segments_gen:
        words_list = []
        if word_timestamps and seg.words:
            words_list = [
                {
                    "w": w.word.strip(),
                    "s": int(w.start * 1000),
                    "e": int(w.end * 1000),
                    "p": round(w.probability, 2),   # confiança da palavra
                }
                for w in seg.words
                if w.word.strip()  # ignora tokens em branco
            ]

        result_segments.append({
            "text": seg.text.strip(),
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "words": words_list,
        })

    elapsed = time.perf_counter() - t0
    audio_dur = info.duration if hasattr(info, "duration") else 0
    rtf = elapsed / audio_dur if audio_dur > 0 else 0

    logger.info(
        f"Transcrição concluída em {elapsed:.1f}s "
        f"(RTF={rtf:.2f}x, {len(result_segments)} segmentos)"
    )

    return {
        "language": info.language,
        "duration_s": round(audio_dur, 2),
        "segments": result_segments,
    }


# Alias para compatibilidade com código legado
def transcribe_with_whisper_local(audio_path: str, language: str = WHISPER_LANGUAGE) -> dict:
    return transcribe(audio_path, language=language)


# ─── CLI rápido ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json, logging
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Uso: python whisper_client.py <arquivo.wav>")
        sys.exit(1)
    result = transcribe(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
