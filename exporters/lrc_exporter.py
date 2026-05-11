"""
exporters/lrc_exporter.py
Exporta letras sincronizadas no formato LRC (LyRiCs).
Formato padrao: [mm:ss.xx]linha da letra
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def to_lrc(project: dict, output_path: str | None = None) -> str:
    """
    Converte um projeto karaoke para formato LRC.

    Args:
        project: Dicionario do projeto (formato JSON do karaoke)
        output_path: Caminho opcional para salvar o arquivo .lrc

    Returns:
        Conteudo LRC como string
    """
    lyrics = project.get("lyrics", [])
    meta = project.get("meta", {})

    lines = []

    if meta.get("key"):
        key = meta["key"]
        if isinstance(key, dict) and "root" in key:
            lines.append(f"[ti:{project.get('src', 'unknown')}]")
            lines.append(f"[re:Karaoke IA]")
            lines.append(f"[key:{key.get('root', '')} {key.get('mode', '')}]")

    for seg in lyrics:
        start_ms = seg.get("s", 0)
        text = seg.get("t", "")

        if not text or not start_ms:
            continue

        mm = start_ms // 60000
        ss = (start_ms % 60000) // 1000
        xx = (start_ms % 1000) // 10
        lines.append(f"[{mm:02d}:{ss:02d}.{xx:02d}]{text}")

    if seg.get("w"):
        words = seg["w"]
        word_text = " ".join(w["w"] for w in words)
        first_ms = words[0]["s"]
        mm = first_ms // 60000
        ss = (first_ms % 60000) // 1000
        xx = (first_ms % 1000) // 10
        lines.append(f"[{mm:02d}:{ss:02d}.{xx:02d}]{word_text}")

    result = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(result, encoding="utf-8")
        logger.info(f"LRC salvo: {output_path}")

    return result
