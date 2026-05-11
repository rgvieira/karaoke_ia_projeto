"""
api/server.py
API REST local (FastAPI) para integração com front-end de karaokê.
Expõe os módulos do pipeline como endpoints com validação e status em tempo real.

Iniciar: uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
"""

import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Karaokê IA API",
    description="Pipeline completo: captura → MIDI → letra → JSON de karaokê",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # em produção restringir a localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Importações lazy (não aborta se módulos ausentes) ───────────────────────
try:
    from config import OUTPUT_DIR, OUTPUT_JSON, WHISPER_LANGUAGE
except ImportError:
    OUTPUT_DIR     = "output/outputs"
    OUTPUT_JSON    = "output/outputs/projeto_karaoke.json"
    WHISPER_LANGUAGE = "pt"

UPLOAD_DIR = Path(OUTPUT_DIR) / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ─── Modelos de request/response ─────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    audio_path: str
    language: str = WHISPER_LANGUAGE

class CorrectMidiRequest(BaseModel):
    midi_in:    str
    midi_out:   str
    audio_path: Optional[str] = None
    tempo:      float = 120.0

class AssembleRequest(BaseModel):
    midi_path:   str
    audio_path:  str
    output_json: str = OUTPUT_JSON
    tempo:       float = 120.0
    language:    str = WHISPER_LANGUAGE
    parallel:    bool = True


# ─── Endpoints de status ──────────────────────────────────────────────────────

@app.get("/", tags=["Status"])
async def root():
    return {"status": "ok", "service": "Karaokê IA API", "version": "1.1.0"}


@app.get("/health", tags=["Status"])
async def health():
    """Verifica disponibilidade de cada módulo."""
    modules = {}

    try:
        from faster_whisper import WhisperModel  # noqa: F401
        modules["whisper"] = "ok"
    except ImportError:
        modules["whisper"] = "not_installed"

    try:
        import basic_pitch  # noqa: F401
        modules["basic_pitch"] = "ok"
    except ImportError:
        modules["basic_pitch"] = "not_installed"

    try:
        import pretty_midi  # noqa: F401
        modules["pretty_midi"] = "ok"
    except ImportError:
        modules["pretty_midi"] = "not_installed"

    try:
        import torch
        modules["gpu"] = f"cuda:{torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else "cpu_only"
    except ImportError:
        modules["gpu"] = "torch_not_installed"

    return {"modules": modules}


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.post("/upload", tags=["Arquivos"])
async def upload_audio(file: UploadFile = File(...)):
    """Recebe arquivo de áudio (WAV) e retorna o caminho no servidor."""
    ext = Path(file.filename or "audio.wav").suffix.lower()
    if ext not in {".wav", ".mp3", ".ogg", ".flac"}:
        raise HTTPException(400, "Formato não suportado. Use WAV, MP3, OGG ou FLAC.")

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"path": str(dest), "size_kb": dest.stat().st_size // 1024}


# ─── Transcrição Whisper ──────────────────────────────────────────────────────

@app.post("/transcribe", tags=["Pipeline"])
async def transcribe_endpoint(req: TranscribeRequest):
    """Transcreve áudio → letras com timestamps por palavra."""
    try:
        from lyrics_sync.whisper_client import transcribe
        t0     = time.perf_counter()
        result = transcribe(req.audio_path, language=req.language)
        result["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Erro na transcrição")
        raise HTTPException(500, str(e))


# ─── BasicPitch ───────────────────────────────────────────────────────────────

@app.post("/audio-to-midi", tags=["Pipeline"])
async def audio_to_midi_endpoint(
    audio_path: str = Query(..., description="Caminho do WAV de entrada"),
    midi_out:   str = Query(OUTPUT_DIR + "/partitura_etapa1.mid"),
):
    """Converte áudio WAV → MIDI via BasicPitch."""
    try:
        from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
        t0     = time.perf_counter()
        events = transcribe_with_basicpitch(audio_path, midi_out)
        return {
            "midi_path": midi_out,
            "n_notes":   len(events),
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "preview":   events[:5],
        }
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Erro na conversão áudio→MIDI")
        raise HTTPException(500, str(e))


# ─── Correção MIDI ────────────────────────────────────────────────────────────

@app.post("/correct-midi", tags=["Pipeline"])
async def correct_midi_endpoint(req: CorrectMidiRequest):
    """Aplica quantização, detecção de tonalidade e correção de escala ao MIDI."""
    try:
        from midi_tools.note_corrector import correct_midi
        t0    = time.perf_counter()
        stats = correct_midi(req.midi_in, req.midi_out, audio_path=req.audio_path, tempo=req.tempo)
        stats["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return stats
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Erro na correção MIDI")
        raise HTTPException(500, str(e))


# ─── Montagem do projeto ──────────────────────────────────────────────────────

@app.post("/assemble", tags=["Pipeline"])
async def assemble_endpoint(req: AssembleRequest):
    """
    Roda pipeline completo (paralelo por padrão):
    MIDI + Whisper → JSON de karaokê.
    """
    try:
        from output.output_generator import assemble_project
        t0      = time.perf_counter()
        project = assemble_project(
            req.midi_path,
            req.audio_path,
            output_json=req.output_json,
            tempo=req.tempo,
            language=req.language,
            parallel=req.parallel,
        )
        return {
            "json_path": req.output_json,
            "n_notes":   project["meta"]["n_notes"],
            "n_segments": project["meta"]["n_segs"],
            "duration_s": project["meta"]["dur_ms"] / 1000,
            "elapsed_s":  round(time.perf_counter() - t0, 2),
        }
    except Exception as e:
        logger.exception("Erro na montagem do projeto")
        raise HTTPException(500, str(e))


# ─── Download do JSON ─────────────────────────────────────────────────────────

@app.get("/download/json", tags=["Arquivos"])
async def download_json(path: str = Query(OUTPUT_JSON)):
    """Baixa o JSON final do projeto."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"Arquivo não encontrado: {path}")
    return FileResponse(str(p), media_type="application/json", filename=p.name)


@app.get("/download/midi", tags=["Arquivos"])
async def download_midi(path: str = Query(...)):
    """Baixa um arquivo MIDI."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"Arquivo não encontrado: {path}")
    return FileResponse(str(p), media_type="audio/midi", filename=p.name)


# ─── Pipeline Completo em Uma Chamada ─────────────────────────────────────────

@app.post("/pipeline/full", tags=["Pipeline"])
async def full_pipeline(
    file:     UploadFile = File(...),
    language: str = Query(WHISPER_LANGUAGE),
    tempo:    float = Query(120.0),
):
    """
    Pipeline completo em uma única chamada:
    Upload WAV → BasicPitch → Correção MIDI → Whisper → JSON

    Retorna o JSON final do projeto.
    """
    # 1. Salvar upload
    ext  = Path(file.filename or "audio.wav").suffix.lower()
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    audio_path = str(dest)

    midi_raw = str(UPLOAD_DIR / f"{dest.stem}_raw.mid")
    midi_fix = str(UPLOAD_DIR / f"{dest.stem}_fixed.mid")
    json_out = str(UPLOAD_DIR / f"{dest.stem}_karaoke.json")

    try:
        t_total = time.perf_counter()

        # 2. BasicPitch
        from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
        transcribe_with_basicpitch(audio_path, midi_raw)

        # 3. Correção MIDI
        from midi_tools.note_corrector import correct_midi
        key_stats = correct_midi(midi_raw, midi_fix, audio_path=audio_path, tempo=tempo)

        # 4. Assemblar JSON (paralelo: MIDI + Whisper)
        from output.output_generator import assemble_project
        project = assemble_project(
            midi_fix, audio_path,
            output_json=json_out,
            tempo=tempo,
            key_info=key_stats.get("key"),
            language=language,
            parallel=True,
        )

        return {
            "status":      "ok",
            "json_path":   json_out,
            "n_notes":     project["meta"]["n_notes"],
            "n_segments":  project["meta"]["n_segs"],
            "duration_s":  project["meta"]["dur_ms"] / 1000,
            "key":         key_stats.get("key", {}),
            "elapsed_s":   round(time.perf_counter() - t_total, 2),
            "download_url": f"/download/json?path={json_out}",
        }

    except Exception as e:
        logger.exception("Erro no pipeline completo")
        raise HTTPException(500, str(e))
