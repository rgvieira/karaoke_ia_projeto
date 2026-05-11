"""
midi_tools/note_corrector.py
Pós-processamento do MIDI gerado pelo BasicPitch:
  1. Quantização de notas para grade rítmica
  2. Detecção de tonalidade (librosa)
  3. Correção de notas fora da escala
  4. Remoção de polifonia improváveis (voz solo)
  5. Filtragem de notas muito curtas (ruído)
  6. Exportação para MIDI corrigido (pretty_midi)
"""

import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import pretty_midi
    _PM_OK = True
except ImportError:
    _PM_OK = False
    logger.warning("pretty_midi não instalado. Use: pip install pretty_midi")

try:
    import librosa
    _LIBROSA_OK = True
except ImportError:
    _LIBROSA_OK = False
    logger.warning("librosa não instalado.")

try:
    from config import (
        MIDI_QUANTIZATION_GRID,
        MIDI_MIN_NOTE_DURATION,
        MIDI_KEY_DETECTION,
        MIDI_MAX_POLYPHONY,
        BASICPITCH_MIDI_TEMPO,
    )
except ImportError:
    MIDI_QUANTIZATION_GRID  = 0.125
    MIDI_MIN_NOTE_DURATION  = 0.05
    MIDI_KEY_DETECTION      = True
    MIDI_MAX_POLYPHONY      = 1
    BASICPITCH_MIDI_TEMPO   = 120


# ─── Mapeamento de escalas ───────────────────────────────────────────────────

# Graus (semitons) das escalas maior e menor natural, a partir de C=0
_SCALE_MAJOR  = {0, 2, 4, 5, 7, 9, 11}
_SCALE_MINOR  = {0, 2, 3, 5, 7, 8, 10}

# Notas MIDI: nomes para log
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F",
               "F#", "G", "G#", "A", "A#", "B"]


def _midi_to_name(midi_note: int) -> str:
    return f"{_NOTE_NAMES[midi_note % 12]}{midi_note // 12 - 1}"


# ─── Detecção de tonalidade ──────────────────────────────────────────────────

def detect_key(audio_path: Optional[str] = None, midi_path: Optional[str] = None) -> tuple[int, str]:
    """
    Detecta tonalidade a partir de áudio (preferido) ou MIDI.

    Retorna (root_note, mode) onde:
      - root_note: 0–11 (C=0, C#=1, … B=11)
      - mode: "major" ou "minor"
    """
    if audio_path and _LIBROSA_OK:
        return _detect_key_from_audio(audio_path)
    if midi_path and _PM_OK:
        return _detect_key_from_midi(midi_path)
    logger.warning("Sem dados suficientes para detectar tonalidade. Usando C maior.")
    return 0, "major"


def _detect_key_from_audio(audio_path: str) -> tuple[int, str]:
    """Usa librosa.key_to_degrees via chroma para estimar a tonalidade."""
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    # Correlação com perfis de Krumhansl (simplificado)
    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    best_score = -np.inf
    best_root, best_mode = 0, "major"

    for root in range(12):
        rotated_chroma = np.roll(chroma_mean, -root)

        score_maj = np.corrcoef(rotated_chroma, major_profile)[0, 1]
        score_min = np.corrcoef(rotated_chroma, minor_profile)[0, 1]

        if score_maj > best_score:
            best_score = score_maj
            best_root, best_mode = root, "major"
        if score_min > best_score:
            best_score = score_min
            best_root, best_mode = root, "minor"

    logger.info(f"Tonalidade detectada: {_NOTE_NAMES[best_root]} {best_mode} (score={best_score:.3f})")
    return best_root, best_mode


def _detect_key_from_midi(midi_path: str) -> tuple[int, str]:
    """Fallback: usa frequência de pitch classes do MIDI."""
    pm = pretty_midi.PrettyMIDI(midi_path)
    counts = np.zeros(12)
    for inst in pm.instruments:
        for note in inst.notes:
            counts[note.pitch % 12] += note.end - note.start  # peso pela duração

    # Correlação simples com perfis
    root = int(np.argmax(counts))
    mode = "major"  # heurística: usa maior por padrão sem áudio
    logger.info(f"Tonalidade estimada do MIDI: {_NOTE_NAMES[root]} {mode}")
    return root, mode


def get_scale_pitches(root: int, mode: str) -> set[int]:
    """Retorna conjunto de todos os MIDI pitches pertencentes à escala."""
    template = _SCALE_MAJOR if mode == "major" else _SCALE_MINOR
    return {(root + degree) % 12 for degree in template}


# ─── Correção de escala ───────────────────────────────────────────────────────

def _nearest_in_scale(pitch: int, scale_pcs: set[int]) -> int:
    """Move o pitch para a nota mais próxima da escala (±1 semitom)."""
    if pitch % 12 in scale_pcs:
        return pitch

    for delta in [1, -1, 2, -2]:
        candidate = pitch + delta
        if candidate % 12 in scale_pcs:
            return candidate

    return pitch  # sem solução, mantém original


# ─── Quantização ─────────────────────────────────────────────────────────────

def _quantize_time(t: float, grid: float, tempo: float) -> float:
    """Quantiza tempo (segundos) para a grade rítmica mais próxima."""
    beat_duration = 60.0 / tempo          # segundos por batida
    grid_duration = grid * beat_duration  # segundos por subdivisão
    return round(t / grid_duration) * grid_duration


# ─── Remoção de polifonia ─────────────────────────────────────────────────────

def _remove_polyphony(notes: list, max_voices: int = 1) -> list:
    """
    Para voz solo: mantém apenas a nota mais alta em qualquer instante de sobreposição.
    """
    if max_voices < 1:
        return notes

    notes_sorted = sorted(notes, key=lambda n: n.start)
    kept = []
    active_end = -np.inf

    for note in notes_sorted:
        if note.start >= active_end:
            kept.append(note)
            active_end = note.end
        else:
            # Sobreposição: mantém a nota mais alta
            if kept and note.pitch > kept[-1].pitch:
                kept[-1] = note
                active_end = note.end

    removed = len(notes) - len(kept)
    if removed:
        logger.info(f"Polifonia removida: {removed} notas descartadas")
    return kept


# ─── Pipeline completo ────────────────────────────────────────────────────────

def correct_midi(
    midi_in_path: str,
    midi_out_path: str,
    audio_path: Optional[str] = None,
    tempo: float = BASICPITCH_MIDI_TEMPO,
    quantization_grid: float = MIDI_QUANTIZATION_GRID,
    min_duration: float = MIDI_MIN_NOTE_DURATION,
    detect_key_flag: bool = MIDI_KEY_DETECTION,
    max_polyphony: int = MIDI_MAX_POLYPHONY,
) -> dict:
    """
    Pipeline completo de correção MIDI.

    Parâmetros
    ----------
    midi_in_path       : MIDI original (BasicPitch)
    midi_out_path      : MIDI corrigido (saída)
    audio_path         : WAV original para detecção de tonalidade (opcional)
    tempo              : BPM para quantização
    quantization_grid  : grade rítmica (0.125 = 1/8 de batida)
    min_duration       : duração mínima em segundos (notas menores são removidas)
    detect_key_flag    : ativa correção de escala
    max_polyphony      : vozes simultâneas máximas (1 = solo)

    Retorno
    -------
    dict com estatísticas: notas_in, notas_out, tonalidade, etc.
    """
    if not _PM_OK:
        raise RuntimeError("pretty_midi não disponível. Instale com: pip install pretty_midi")

    midi_in_path = str(Path(midi_in_path).resolve())
    Path(midi_out_path).parent.mkdir(parents=True, exist_ok=True)

    pm = pretty_midi.PrettyMIDI(midi_in_path)

    # ── 1. Coletar todas as notas ────────────────────────────────────────────
    all_notes = []
    for inst in pm.instruments:
        all_notes.extend(inst.notes)

    total_in = len(all_notes)
    logger.info(f"MIDI carregado: {total_in} notas | {len(pm.instruments)} instrumento(s)")

    # ── 2. Filtrar notas muito curtas ────────────────────────────────────────
    all_notes = [n for n in all_notes if (n.end - n.start) >= min_duration]
    logger.info(f"Após filtro de duração mínima: {len(all_notes)} notas")

    # ── 3. Quantizar tempo ───────────────────────────────────────────────────
    for note in all_notes:
        q_start = _quantize_time(note.start, quantization_grid, tempo)
        q_end   = _quantize_time(note.end,   quantization_grid, tempo)
        # Garante duração mínima após quantização
        if q_end - q_start < min_duration:
            q_end = q_start + min_duration
        note.start = q_start
        note.end   = q_end

    logger.info(f"Quantização aplicada (grid={quantization_grid}, BPM={tempo})")

    # ── 4. Detecção e correção de tonalidade ─────────────────────────────────
    key_info = {"root": 0, "mode": "major", "applied": False}
    if detect_key_flag:
        root, mode = detect_key(audio_path=audio_path, midi_path=midi_in_path)
        scale_pcs  = get_scale_pitches(root, mode)
        key_info   = {"root": _NOTE_NAMES[root], "mode": mode, "applied": True}

        corrected = 0
        for note in all_notes:
            new_pitch = _nearest_in_scale(note.pitch, scale_pcs)
            if new_pitch != note.pitch:
                note.pitch = new_pitch
                corrected += 1

        logger.info(
            f"Correção de escala ({_NOTE_NAMES[root]} {mode}): "
            f"{corrected}/{len(all_notes)} notas ajustadas"
        )

    # ── 5. Remover polifonia excessiva ───────────────────────────────────────
    all_notes = _remove_polyphony(all_notes, max_voices=max_polyphony)

    # ── 6. Ordenar por tempo de início ───────────────────────────────────────
    all_notes.sort(key=lambda n: n.start)

    # ── 7. Reconstruir MIDI corrigido ────────────────────────────────────────
    pm_out = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    voice  = pretty_midi.Instrument(program=0, name="Voz Corrigida")
    voice.notes = all_notes
    pm_out.instruments.append(voice)
    pm_out.write(midi_out_path)

    total_out = len(all_notes)
    logger.info(
        f"MIDI corrigido salvo: {midi_out_path} | "
        f"{total_in} → {total_out} notas"
    )

    return {
        "notes_in":  total_in,
        "notes_out": total_out,
        "filtered":  total_in - total_out,
        "key":       key_info,
        "midi_out":  midi_out_path,
    }


# ─── CLI rápido ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json, logging
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 3:
        print("Uso: python note_corrector.py input.mid output.mid [audio.wav]")
        sys.exit(1)

    audio = sys.argv[3] if len(sys.argv) > 3 else None
    stats = correct_midi(sys.argv[1], sys.argv[2], audio_path=audio)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
