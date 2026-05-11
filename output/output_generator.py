"""
output/output_generator.py
Monta o JSON final do projeto de karaokê combinando:
  - Notas MIDI corrigidas (pretty_midi)
  - Letras com timestamps por palavra (Whisper)
  - Metadados de BPM, tonalidade e duração
JSON exportado com chaves compactas (~40% menor que formato expandido).
"""

import json
import logging
import math
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pretty_midi
    _PM_OK = True
except ImportError:
    _PM_OK = False

try:
    from config import OUTPUT_JSON, BASICPITCH_MIDI_TEMPO
except ImportError:
    OUTPUT_JSON          = "output/outputs/projeto_karaoke.json"
    BASICPITCH_MIDI_TEMPO = 120

# ─── Extração de notas ────────────────────────────────────────────────────────

def midi_to_note_list(midi_path: str, tempo: float = BASICPITCH_MIDI_TEMPO) -> list[dict]:
    """
    Extrai notas do MIDI em formato compacto.

    Chaves:
      n    = MIDI pitch (0–127)
      s_ms = início em milissegundos
      d_ms = duração em milissegundos
      v    = velocity (0–127)
    """
    if _PM_OK:
        return _extract_via_pretty_midi(midi_path)
    return _extract_via_mido(midi_path, tempo)


def _extract_via_pretty_midi(midi_path: str) -> list[dict]:
    """Usa pretty_midi para duração precisa."""
    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = []
    for inst in pm.instruments:
        for note in inst.notes:
            notes.append({
                "n":    note.pitch,
                "s_ms": int(note.start * 1000),
                "d_ms": max(1, int((note.end - note.start) * 1000)),
                "v":    note.velocity,
            })
    notes.sort(key=lambda n: n["s_ms"])
    logger.info(f"Extraídas {len(notes)} notas via pretty_midi")
    return notes


def _extract_via_mido(midi_path: str, tempo: float) -> list[dict]:
    """Fallback: usa mido se pretty_midi não estiver disponível."""
    try:
        import mido
    except ImportError:
        logger.error("Nem pretty_midi nem mido instalados. Não é possível extrair notas.")
        return []

    mid           = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat
    us_per_beat    = int(60_000_000 / tempo)  # microssegundos
    notes          = []
    open_notes: dict[int, dict] = {}  # pitch → nota em aberto

    for track in mid.tracks:
        abs_ticks = 0
        for msg in track:
            abs_ticks += msg.time

            if msg.type == "set_tempo":
                us_per_beat = msg.tempo

            elif msg.type == "note_on" and msg.velocity > 0:
                time_ms = int(mido.tick2second(abs_ticks, ticks_per_beat, us_per_beat) * 1000)
                open_notes[msg.note] = {"n": msg.note, "s_ms": time_ms, "v": msg.velocity}

            elif msg.type in ("note_off", "note_on") and msg.note in open_notes:
                if msg.type == "note_off" or msg.velocity == 0:
                    end_ms  = int(mido.tick2second(abs_ticks, ticks_per_beat, us_per_beat) * 1000)
                    on_note = open_notes.pop(msg.note)
                    on_note["d_ms"] = max(1, end_ms - on_note["s_ms"])
                    notes.append(on_note)

    notes.sort(key=lambda n: n["s_ms"])
    logger.info(f"Extraídas {len(notes)} notas via mido")
    return notes


# ─── Formatação de letras ─────────────────────────────────────────────────────

def _format_lyrics(segments: list[dict]) -> list[dict]:
    """
    Converte segmentos do Whisper em formato compacto.

    Chaves:
      t    = texto do segmento
      s    = início em ms
      e    = fim em ms
      w    = lista de palavras (opcional, se disponível)
        w.w = palavra
        w.s = início ms
        w.e = fim ms
    """
    out = []
    for seg in segments:
        entry: dict = {
            "t": seg["text"],
            "s": int(seg["start"] * 1000),
            "e": int(seg["end"]   * 1000),
        }
        if seg.get("words"):
            entry["w"] = [
                {"w": w["w"], "s": w["s"], "e": w["e"]}
                for w in seg["words"]
            ]
        out.append(entry)
    return out


# ─── Pipeline Principal ───────────────────────────────────────────────────────

def assemble_project(
    midi_path: str,
    audio_path: str,
    output_json: str = OUTPUT_JSON,
    tempo: float = BASICPITCH_MIDI_TEMPO,
    key_info: Optional[dict] = None,
    language: str = "pt",
    parallel: bool = True,
) -> dict:
    """
    Gera o JSON final do projeto de karaokê.

    Parâmetros
    ----------
    midi_path   : MIDI corrigido
    audio_path  : WAV original (para transcrição Whisper)
    output_json : caminho de saída do JSON
    tempo       : BPM
    key_info    : resultado de note_corrector.correct_midi()["key"]
    language    : idioma para Whisper
    parallel    : roda Whisper e extração MIDI em paralelo

    Retorno
    -------
    Dicionário completo do projeto (mesmo conteúdo do JSON)
    """
    logger.info("Iniciando montagem do projeto de karaoke")
    t0 = time.perf_counter()

    if parallel:
        return _assemble_parallel(midi_path, audio_path, output_json, tempo, key_info, language)

    # ── Sequencial ───────────────────────────────────────────────────────────
    from lyrics_sync.whisper_client import transcribe
    notes       = midi_to_note_list(midi_path, tempo)
    lyrics_data = transcribe(audio_path, language=language)
    return _build_and_save(notes, lyrics_data, output_json, tempo, key_info, audio_path)


def _assemble_parallel(midi_path, audio_path, output_json, tempo, key_info, language):
    """
    Roda extração de notas e transcrição Whisper em threads paralelas.
    Economiza ~30–50% do tempo total.
    """
    import threading

    notes_result      = {}
    lyrics_result     = {}
    errors            = []

    def extract_notes():
        try:
            notes_result["notes"] = midi_to_note_list(midi_path, tempo)
        except Exception as e:
            errors.append(f"MIDI: {e}")

    def transcribe_audio():
        try:
            from lyrics_sync.whisper_client import transcribe
            lyrics_result["data"] = transcribe(audio_path, language=language)
        except Exception as e:
            errors.append(f"Whisper: {e}")

    t_notes   = threading.Thread(target=extract_notes,   name="midi-extract")
    t_whisper = threading.Thread(target=transcribe_audio, name="whisper-transcribe")

    t_notes.start()
    t_whisper.start()
    t_notes.join()
    t_whisper.join()

    if errors:
        raise RuntimeError(f"Erros no pipeline paralelo: {'; '.join(errors)}")

    return _build_and_save(
        notes_result["notes"],
        lyrics_result["data"],
        output_json, tempo, key_info, audio_path,
    )


def _build_and_save(notes, lyrics_data, output_json, tempo, key_info, audio_path):
    segments    = lyrics_data.get("segments", [])
    lyrics_out  = _format_lyrics(segments)
    duration_ms = segments[-1]["end"] * 1000 if segments else (
        max(n["s_ms"] + n["d_ms"] for n in notes) if notes else 0
    )

    project = {
        "pv":     "1.1",                             # versão do formato
        "src":    Path(audio_path).name,
        "lang":   lyrics_data.get("language", "pt"),
        "notes":  notes,
        "lyrics": lyrics_out,
        "meta": {
            "bpm":     tempo,
            "dur_ms":  int(duration_ms),
            "key":     key_info or {},
            "n_notes": len(notes),
            "n_segs":  len(lyrics_out),
        },
    }

    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = Path(output_json).stat().st_size / 1024
    logger.info(
        f"JSON salvo: {output_json} "
        f"({size_kb:.1f} KB | {len(notes)} notas | {len(lyrics_out)} segmentos)"
    )

    return project


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 3:
        print("Uso: python output_generator.py midi.mid audio.wav [output.json]")
        sys.exit(1)

    out = sys.argv[3] if len(sys.argv) > 3 else OUTPUT_JSON
    proj = assemble_project(sys.argv[1], sys.argv[2], out)
    print(f"Projeto montado: {proj['meta']['n_notes']} notas, "
          f"{proj['meta']['n_segs']} segmentos, "
          f"{proj['meta']['dur_ms'] / 1000:.1f}s")
