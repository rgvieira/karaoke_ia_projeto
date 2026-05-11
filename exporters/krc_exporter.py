"""
exporters/krc_exporter.py
Exporta letras sincronizadas no formato KRC (Kugou).
Com timestamps por palavra para karaoke word-level.
"""

import logging
import struct
import zlib
from base64 import b64encode
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENCRYPT_KEY = b"kugou1325"


def _encrypt_krc(data: bytes) -> bytes:
    """Criptografa no formato Kugou (XOR + compressao)."""
    compressed = zlib.compress(data)
    key_len = len(_ENCRYPT_KEY)
    encrypted = bytearray(len(compressed))
    for i, b in enumerate(compressed):
        encrypted[i] = b ^ _ENCRYPT_KEY[i % key_len]
    return bytes(encrypted)


def to_krc(project: dict, output_path: str | None = None) -> bytes:
    """
    Converte projeto karaoke para formato KRC (Kugou).

    Args:
        project: Dicionario do projeto (formato JSON do karaoke)
        output_path: Caminho opcional para salvar o arquivo .krc

    Returns:
        Conteudo KRC como bytes
    """
    lyrics = project.get("lyrics", [])
    meta = project.get("meta", {})
    bpm = meta.get("bpm", 120)

    lines = []
    lines.append(f"[offset:0]")

    for seg in lyrics:
        start_ms = seg.get("s", 0)
        text = seg.get("t", "")
        words = seg.get("w", [])

        if not text or not start_ms:
            continue

        if words:
            word_parts = []
            for w in words:
                ws = w.get("s", 0) - start_ms
                we = w.get("e", 0) - start_ms
                wt = w.get("w", "")
                word_parts.append(f"<{ws},{we}>{wt}")

            if word_parts:
                line = f"[{start_ms},0]{''.join(word_parts)}"
                lines.append(line)
            else:
                mm = start_ms // 60000
                ss = (start_ms % 60000) // 1000
                ms = start_ms % 1000
                lines.append(f"[{start_ms},{0}]{text}")
        else:
            lines.append(f"[{start_ms},{0}]{text}")

    raw = "\n".join(lines).encode("utf-8-sig")
    encrypted = _encrypt_krc(raw)

    header = struct.pack("<I", len(encrypted))
    result = b"krc" + header + encrypted

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(result)
        logger.info(f"KRC salvo: {output_path}")

    return result


def to_txt(project: dict, output_path: str | None = None) -> str:
    """Exporta letras como texto simples com timestamps."""
    lyrics = project.get("lyrics", [])
    lines = []
    for seg in lyrics:
        start_ms = seg.get("s", 0)
        text = seg.get("t", "")
        mm = start_ms // 60000
        ss = (start_ms % 60000) // 1000
        ms = start_ms % 1000
        lines.append(f"[{mm:02d}:{ss:02d}.{ms:03d}] {text}")

    result = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")
        logger.info(f"TXT salvo: {output_path}")
    return result
