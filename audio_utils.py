"""
audio_utils.py
Utilitarios de conversao e formatos de audio.
Converte MP3/OGG/FLAC para WAV automaticamente.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma"}


def ensure_wav(path: str, target_dir: str | None = None) -> str:
    """
    Garante que o arquivo de audio esteja em formato WAV.
    Converte MP3/OGG/FLAC para WAV se necessario.

    Args:
        path: Caminho do arquivo de audio original
        target_dir: Diretorio de destino (padrao: mesmo diretorio do original)

    Returns:
        Caminho do arquivo WAV (original ou convertido)
    """
    path = str(Path(path).resolve())
    ext = Path(path).suffix.lower()

    if ext == ".wav":
        return path

    if ext not in AUDIO_EXTENSIONS:
        raise ValueError(
            f"Formato '{ext}' nao suportado. Use: {', '.join(sorted(AUDIO_EXTENSIONS))}"
        )

    target = target_dir or str(Path(path).parent)
    wav_path = str(Path(target) / f"{Path(path).stem}.wav")

    if Path(wav_path).exists():
        logger.info(f"WAV ja existe: {wav_path}")
        return wav_path

    logger.info(f"Convertendo {ext} -> WAV: {Path(path).name}")
    _convert_to_wav(path, wav_path)
    return wav_path


def _convert_to_wav(src: str, dst: str):
    """Converte arquivo de audio para WAV 16-bit mono 22050Hz."""
    try:
        import librosa
    except ImportError:
        raise RuntimeError("librosa necessario para conversao. Instale com: pip install librosa")

    audio, sr = librosa.load(src, sr=22050, mono=True)
    _write_wav(audio, sr, dst)
    logger.info(f"Convertido: {Path(src).name} -> {Path(dst).name}")


def _write_wav(audio, sr: int, path: str):
    """Escreve array numpy como WAV 16-bit."""
    try:
        from scipy.io import wavfile
        import numpy as np
        pcm = (audio * 32767).astype(np.int16)
        os.makedirs(Path(path).parent, exist_ok=True)
        wavfile.write(path, sr, pcm)
    except ImportError:
        import soundfile as sf
        sf.write(path, audio, sr, subtype="PCM_16")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Uso: python audio_utils.py <arquivo.mp3>")
        sys.exit(1)
    result = ensure_wav(sys.argv[1])
    print(f"Resultado: {result}")
