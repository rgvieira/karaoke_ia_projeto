"""
downloaders/youtube.py
Download de audio do YouTube usando yt-dlp.
Converte automaticamente para WAV 22050Hz mono.
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_YT_DLP_OK = False
try:
    import yt_dlp
    _YT_DLP_OK = True
except ImportError:
    pass


def _is_youtube_url(url: str) -> bool:
    patterns = [
        r"^https?://(www\.)?youtube\.com/watch\?v=.+",
        r"^https?://youtu\.be/.+",
        r"^https?://(www\.)?youtube\.com/shorts/.+",
        r"^https?://music\.youtube\.com/watch\?v=.+",
        r"^https?://(www\.)?youtube\.com/playlist\?list=.+",
    ]
    return any(re.match(p, url) for p in patterns)


def _sanitize_filename(title: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|]', "", title)
    return safe.strip().replace(" ", "_") or "youtube_audio"


def download_youtube_audio(
    url: str,
    output_dir: str | None = None,
) -> str:
    """
    Baixa audio do YouTube e converte para WAV.

    Args:
        url: URL do video do YouTube
        output_dir: Diretorio de saida (padrao: output/outputs)

    Returns:
        Caminho do arquivo WAV baixado

    Raises:
        ValueError: Se a URL nao for valida
        RuntimeError: Se yt-dlp nao estiver instalado
    """
    if not _YT_DLP_OK:
        raise RuntimeError(
            "yt-dlp nao instalado. Execute: pip install yt-dlp"
        )

    if not _is_youtube_url(url):
        raise ValueError(
            f"URL do YouTube invalida: {url}\n"
            "Use o formato: https://www.youtube.com/watch?v=..."
        )

    output_dir = output_dir or str(Path(__file__).resolve().parent.parent / "output" / "outputs")
    os.makedirs(output_dir, exist_ok=True)

    output_template = str(Path(output_dir) / "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
        "prefer_ffmpeg": True,
        "quiet": True,
        "no_warnings": True,
    }

    logger.info(f"Baixando audio do YouTube: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "audio")
            duration = info.get("duration", 0)
            logger.info(
                f"Video: '{title}' ({duration // 60}:{duration % 60:02d})"
            )
    except Exception as e:
        raise RuntimeError(f"Falha ao baixar audio do YouTube: {e}") from e

    # Find the downloaded WAV
    wav_path = None
    for f in os.listdir(output_dir):
        if f.endswith(".wav") and _sanitize_filename(title) in f:
            wav_path = str(Path(output_dir) / f)
            break

    if not wav_path:
        wav_path = str(Path(output_dir) / f"{_sanitize_filename(title)}.wav")

    if not Path(wav_path).exists():
        raise RuntimeError(f"Arquivo WAV nao encontrado apos download: {wav_path}")

    logger.info(f"Audio salvo: {wav_path}")
    return wav_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Uso: python youtube.py <URL>")
        sys.exit(1)
    path = download_youtube_audio(sys.argv[1])
    print(f"Audio baixado: {path}")
