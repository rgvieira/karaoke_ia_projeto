"""
api/server.py
API REST local (FastAPI) para integracao com front-end de karaoke.
Expoe os modulos do pipeline como endpoints com validacao e status em tempo real.

Iniciar: uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
"""

import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Karaoke IA API",
    description="Pipeline completo: captura -> MIDI -> letra -> JSON de karaoke",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Importacoes lazy (nao aborta se modulos ausentes) ───────────────────────
try:
    from config import OUTPUT_DIR, OUTPUT_JSON, WHISPER_LANGUAGE
except ImportError:
    OUTPUT_DIR       = "output/outputs"
    OUTPUT_JSON      = "output/outputs/projeto_karaoke.json"
    WHISPER_LANGUAGE = "pt"

BASE_DIR    = Path(__file__).resolve().parent.parent
UPLOAD_DIR  = Path(OUTPUT_DIR) / "uploads"
OUTPUT_PATH = Path(OUTPUT_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

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

class PipelineRequest(BaseModel):
    audio_path: str
    language:   str = WHISPER_LANGUAGE
    tempo:      float = 120.0

class YoutubeRequest(BaseModel):
    url: str

class ExportLrcRequest(BaseModel):
    project: dict


# ─── Endpoints de status ──────────────────────────────────────────────────────

@app.get("/", tags=["Status"])
async def root():
    return {
        "status": "ok",
        "service": "Karaoke IA API",
        "version": "1.2.0",
    }

@app.get("/api/health", tags=["Status"])
async def health():
    """Verifica disponibilidade de cada modulo."""
    modules = {}

    try:
        from faster_whisper import WhisperModel
        modules["whisper"] = "ok"
    except ImportError:
        modules["whisper"] = "not_installed"

    try:
        import basic_pitch
        modules["basic_pitch"] = "ok"
    except ImportError:
        modules["basic_pitch"] = "not_installed"

    try:
        import pretty_midi
        modules["pretty_midi"] = "ok"
    except ImportError:
        modules["pretty_midi"] = "not_installed"

    try:
        import yt_dlp
        modules["youtube"] = "ok"
    except ImportError:
        modules["youtube"] = "not_installed"

    try:
        import torch
        modules["gpu"] = f"cuda:{torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else "cpu_only"
    except ImportError:
        modules["gpu"] = "torch_not_installed"

    return {"modules": modules}


# ─── Web Interface ────────────────────────────────────────────────────────────

@app.get("/api/web", tags=["Web"])
async def web_interface():
    """Serve a interface web do player de karaoke."""
    web_path = BASE_DIR / "web" / "index.html"
    if not web_path.exists():
        raise HTTPException(404, "Interface web nao encontrada. Execute o projeto da raiz.")
    return HTMLResponse(web_path.read_text(encoding="utf-8"))


# ─── Audio Server ─────────────────────────────────────────────────────────────

@app.get("/api/audio/{filename:path}", tags=["Arquivos"])
async def serve_audio(filename: str):
    """Serve arquivos de audio para o player web."""
    for base in [UPLOAD_DIR, OUTPUT_PATH, BASE_DIR]:
        path = Path(base) / filename
        if path.exists():
            return FileResponse(str(path), media_type="audio/wav")
    raise HTTPException(404, f"Audio nao encontrado: {filename}")


# ─── YouTube ──────────────────────────────────────────────────────────────────

@app.post("/api/youtube", tags=["YouTube"])
async def youtube_download(req: YoutubeRequest):
    """Baixa audio do YouTube e retorna o caminho."""
    t0 = time.perf_counter()
    try:
        from downloaders import download_youtube_audio
        path = download_youtube_audio(req.url, str(UPLOAD_DIR))
        return {
            "path": path,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.exception("Erro no YouTube")
        raise HTTPException(500, str(e))


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.post("/api/upload", tags=["Arquivos"])
async def upload_audio(file: UploadFile = File(...)):
    """Recebe arquivo de audio e retorna o caminho no servidor."""
    ext = Path(file.filename or "audio.wav").suffix.lower()
    if ext not in {".wav", ".mp3", ".ogg", ".flac", ".m4a"}:
        raise HTTPException(400, "Formato nao suportado. Use WAV, MP3, OGG ou FLAC.")

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"path": str(dest), "size_kb": dest.stat().st_size // 1024}


# ─── Pipeline Completo (por path) ──────────────────────────────────────────────

@app.post("/api/pipeline", tags=["Pipeline"])
async def run_pipeline(req: PipelineRequest):
    """
    Pipeline completo a partir de um path de audio:
    WAV -> BasicPitch -> Correcao MIDI -> Whisper -> JSON
    Retorna o JSON final do projeto.
    """
    from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
    from midi_tools.note_corrector import correct_midi
    from output.output_generator import assemble_project
    from audio_utils import ensure_wav

    t_total = time.perf_counter()

    audio_path = ensure_wav(req.audio_path, str(UPLOAD_DIR))
    stem = Path(audio_path).stem

    midi_raw = str(UPLOAD_DIR / f"{stem}_raw.mid")
    midi_fix = str(UPLOAD_DIR / f"{stem}_fixed.mid")
    json_out = str(UPLOAD_DIR / f"{stem}_karaoke.json")

    try:
        notes = transcribe_with_basicpitch(audio_path, midi_raw)
        key_stats = correct_midi(midi_raw, midi_fix, audio_path=audio_path, tempo=req.tempo)
        project = assemble_project(
            midi_fix, audio_path,
            output_json=json_out,
            tempo=req.tempo,
            key_info=key_stats.get("key"),
            language=req.language,
            parallel=True,
        )
        project["status"] = "ok"
        project["elapsed_s"] = round(time.perf_counter() - t_total, 2)
        return project
    except Exception as e:
        logger.exception("Erro no pipeline")
        raise HTTPException(500, str(e))


# ─── Pipeline Completo (upload direto) ────────────────────────────────────────

@app.post("/pipeline/full", tags=["Pipeline"])
async def full_pipeline(
    file:     UploadFile = File(...),
    language: str = Query(WHISPER_LANGUAGE),
    tempo:    float = Query(120.0),
):
    """Pipeline completo: Upload WAV -> JSON."""
    ext  = Path(file.filename or "audio.wav").suffix.lower()
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    from audio_utils import ensure_wav
    audio_path = ensure_wav(str(dest))

    from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
    from midi_tools.note_corrector import correct_midi
    from output.output_generator import assemble_project

    try:
        t_total = time.perf_counter()
        midi_raw = str(UPLOAD_DIR / f"{dest.stem}_raw.mid")
        midi_fix = str(UPLOAD_DIR / f"{dest.stem}_fixed.mid")
        json_out = str(UPLOAD_DIR / f"{dest.stem}_karaoke.json")

        transcribe_with_basicpitch(audio_path, midi_raw)
        key_stats = correct_midi(midi_raw, midi_fix, audio_path=audio_path, tempo=tempo)
        project = assemble_project(
            midi_fix, audio_path,
            output_json=json_out,
            tempo=tempo,
            key_info=key_stats.get("key"),
            language=language,
            parallel=True,
        )

        return project | {
            "status":    "ok",
            "json_path": json_out,
            "elapsed_s": round(time.perf_counter() - t_total, 2),
        }
    except Exception as e:
        logger.exception("Erro no pipeline completo")
        raise HTTPException(500, str(e))


# ─── Transcricao Whisper ──────────────────────────────────────────────────────

@app.post("/transcribe", tags=["Pipeline"])
async def transcribe_endpoint(req: TranscribeRequest):
    """Transcreve audio -> letras com timestamps por palavra."""
    try:
        from lyrics_sync.whisper_client import transcribe
        t0     = time.perf_counter()
        result = transcribe(req.audio_path, language=req.language)
        result["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Erro na transcricao")
        raise HTTPException(500, str(e))


# ─── BasicPitch ───────────────────────────────────────────────────────────────

@app.post("/audio-to-midi", tags=["Pipeline"])
async def audio_to_midi_endpoint(
    audio_path: str = Query(..., description="Caminho do WAV de entrada"),
    midi_out:   str = Query(OUTPUT_DIR + "/partitura_etapa1.mid"),
):
    """Converte audio WAV -> MIDI via BasicPitch."""
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
        logger.exception("Erro na conversao audio->MIDI")
        raise HTTPException(500, str(e))


# ─── Correcao MIDI ────────────────────────────────────────────────────────────

@app.post("/correct-midi", tags=["Pipeline"])
async def correct_midi_endpoint(req: CorrectMidiRequest):
    """Aplica quantizacao, deteccao de tonalidade e correcao de escala ao MIDI."""
    try:
        from midi_tools.note_corrector import correct_midi
        t0    = time.perf_counter()
        stats = correct_midi(req.midi_in, req.midi_out, audio_path=req.audio_path, tempo=req.tempo)
        stats["elapsed_s"] = round(time.perf_counter() - t0, 2)
        return stats
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Erro na correcao MIDI")
        raise HTTPException(500, str(e))


# ─── Montagem do projeto ──────────────────────────────────────────────────────

@app.post("/assemble", tags=["Pipeline"])
async def assemble_endpoint(req: AssembleRequest):
    """MIDI + Whisper -> JSON de karaoke."""
    try:
        from output.output_generator import assemble_project
        t0      = time.perf_counter()
        project = assemble_project(
            req.midi_path, req.audio_path,
            output_json=req.output_json,
            tempo=req.tempo,
            language=req.language,
            parallel=req.parallel,
        )
        return {
            "json_path":  req.output_json,
            "n_notes":    project["meta"]["n_notes"],
            "n_segments": project["meta"]["n_segs"],
            "duration_s": project["meta"]["dur_ms"] / 1000,
            "elapsed_s":  round(time.perf_counter() - t0, 2),
        }
    except Exception as e:
        logger.exception("Erro na montagem do projeto")
        raise HTTPException(500, str(e))


# ─── Export LRC ────────────────────────────────────────────────────────────────

@app.post("/api/export/lrc", tags=["Export"])
async def export_lrc(req: ExportLrcRequest):
    """Exporta projeto para formato LRC (letra sincronizada)."""
    try:
        from exporters import to_lrc
        lrc = to_lrc(req.project)
        return PlainTextResponse(lrc, media_type="text/plain")
    except Exception as e:
        logger.exception("Erro na exportacao LRC")
        raise HTTPException(500, str(e))


# ─── Download ─────────────────────────────────────────────────────────────────

@app.get("/download/json", tags=["Arquivos"])
async def download_json(path: str = Query(OUTPUT_JSON)):
    """Baixa o JSON final do projeto."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"Arquivo nao encontrado: {path}")
    return FileResponse(str(p), media_type="application/json", filename=p.name)


@app.get("/download/midi", tags=["Arquivos"])
async def download_midi(path: str = Query(...)):
    """Baixa um arquivo MIDI."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"Arquivo nao encontrado: {path}")
    return FileResponse(str(p), media_type="audio/midi", filename=p.name)
