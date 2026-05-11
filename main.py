"""
main.py — Orquestrador do Pipeline Karaoke IA
Uso: python main.py [modo] [opcoes]

Modos:
  capture   Captura audio do sistema (loopback WASAPI)
  process   Processa audio (WAV/MP3/OGG/FLAC) -> JSON de karaoke
  youtube   Baixa audio do YouTube e processa
  export    Exporta projeto JSON para LRC/TXT
  full      Captura + processa em sequencia
  serve     Inicia API REST local (FastAPI) + interface web
  diagnose  Verifica modulos e hardware disponiveis
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def cmd_diagnose():
    """Verifica disponibilidade de todos os modulos e hardware."""
    checks = {
        "faster_whisper": "Whisper (transcricao)",
        "basic_pitch":    "BasicPitch (audio->MIDI)",
        "pretty_midi":    "pretty_midi (correcao MIDI)",
        "librosa":        "librosa (analise de audio)",
        "yt_dlp":         "yt-dlp (YouTube download)",
        "pyaudio":        "pyaudio (captura loopback)",
        "noisereduce":    "noisereduce (reducao de ruido)",
        "fastapi":        "FastAPI (API REST)",
        "torch":          "PyTorch (aceleracao GPU)",
    }

    print("\n=== Diagnostico do Sistema ===\n")

    ok = failed = 0
    for module, label in checks.items():
        try:
            __import__(module.replace("-", "_"))
            print(f"  [OK] {label}")
            ok += 1
        except ImportError:
            print(f"  [--] {label}  (pip install {module})")
            failed += 1

    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"\n  GPU: {name} ({vram:.1f} GB VRAM)")
        else:
            print("\n  GPU: nao disponivel - usando CPU")
    except ImportError:
        pass

    try:
        import config
        print(f"\n  Config: Whisper={config.WHISPER_MODEL_SIZE} | SR={config.BASICPITCH_SAMPLE_RATE} Hz")
    except ImportError:
        print("\n  config.py: nao encontrado")

    print(f"\n=== {ok} modulos OK | {failed} ausentes ===\n")
    return failed == 0


def cmd_capture(duration: float, output: str):
    """Captura audio do sistema."""
    try:
        from audio_capture.loopback import capture_audio
    except ImportError as e:
        logger.error(f"Modulo de captura indisponivel: {e}")
        sys.exit(1)

    logger.info(f"Capturando {duration}s de audio -> {output}")
    path = capture_audio(duration, output_path=output)
    logger.info(f"Audio salvo: {path}")
    return path


def cmd_process(audio_path, midi_raw, midi_fix, json_out, language="pt", tempo=120.0, parallel=True):
    """Processa audio (WAV/MP3/OGG/FLAC) -> JSON de karaoke completo."""
    from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
    from audio_utils import ensure_wav
    from midi_tools.note_corrector import correct_midi
    from output.output_generator import assemble_project

    wav_path = ensure_wav(audio_path)
    if wav_path != audio_path:
        logger.info(f"Audio convertido: {audio_path} -> {wav_path}")

    t_total = time.perf_counter()

    logger.info("[ 1/3 ] BasicPitch: audio -> MIDI bruto")
    t0 = time.perf_counter()
    notes = transcribe_with_basicpitch(wav_path, midi_raw)
    logger.info(f"        {len(notes)} notas em {time.perf_counter()-t0:.1f}s")

    logger.info("[ 2/3 ] Correcao MIDI: quantizacao + tonalidade")
    t0 = time.perf_counter()
    stats = correct_midi(midi_raw, midi_fix, audio_path=wav_path, tempo=tempo)
    logger.info(f"        {stats['notes_out']} notas ({stats['filtered']} filtradas) | {stats['key'].get('root','?')} {stats['key'].get('mode','?')} em {time.perf_counter()-t0:.1f}s")

    logger.info("[ 3/3 ] Montando JSON (Whisper + MIDI)")
    t0 = time.perf_counter()
    proj = assemble_project(midi_fix, wav_path, output_json=json_out, tempo=tempo, key_info=stats.get("key"), language=language, parallel=parallel)
    logger.info(f"        JSON salvo em {time.perf_counter()-t0:.1f}s")

    elapsed = time.perf_counter() - t_total
    logger.info(f"\n=== Pipeline concluido em {elapsed:.1f}s ===\n  Notas: {proj['meta']['n_notes']}\n  Segmentos: {proj['meta']['n_segs']}\n  Duracao: {proj['meta']['dur_ms']/1000:.1f}s\n  Saida: {json_out}\n")
    return proj


def cmd_youtube(url: str, language: str = "pt", tempo: float = 120.0):
    """Baixa audio do YouTube e processa o pipeline completo."""
    logger.info(f"Baixando audio do YouTube: {url}")

    try:
        from downloaders import download_youtube_audio
        from config import OUTPUT_DIR
        wav_path = download_youtube_audio(url, str(OUTPUT_DIR))
    except ImportError:
        logger.error("yt-dlp nao instalado. Execute: pip install yt-dlp")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Falha no YouTube: {e}")
        sys.exit(1)

    logger.info(f"Audio baixado: {wav_path}")

    from config import OUTPUT_MIDI_1, OUTPUT_MIDI_2, OUTPUT_JSON
    return cmd_process(wav_path, OUTPUT_MIDI_1, OUTPUT_MIDI_2, OUTPUT_JSON, language=language, tempo=tempo)


def cmd_export(project_path: str, output_format: str, output_path: str | None = None):
    """Exporta projeto JSON para LRC ou TXT."""
    path = Path(project_path)
    if not path.exists():
        logger.error(f"Projeto nao encontrado: {project_path}")
        sys.exit(1)

    project = json.loads(path.read_text(encoding="utf-8"))

    if output_format == "lrc":
        from exporters import to_lrc
        out = output_path or str(path.with_suffix(".lrc"))
        result = to_lrc(project, out)
        logger.info(f"LRC exportado: {out}")
    elif output_format == "txt":
        from exporters.krc_exporter import to_txt
        out = output_path or str(path.with_suffix(".txt"))
        result = to_txt(project, out)
        logger.info(f"TXT exportado: {out}")
    else:
        logger.error(f"Formato desconhecido: {output_format}. Use lrc ou txt.")
        sys.exit(1)

    return result


def cmd_serve(host: str = "127.0.0.1", port: int = 8000):
    """Inicia o servidor FastAPI + interface web."""
    try:
        import uvicorn
        from api.server import app
    except ImportError as e:
        logger.error(f"FastAPI/uvicorn nao instalado: {e}")
        sys.exit(1)

    logger.info(f"Iniciando API em http://{host}:{port}")
    logger.info(f" Docs: http://{host}:{port}/docs")
    logger.info(f" Web:  http://{host}:{port}/api/web")
    uvicorn.run(app, host=host, port=port)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    try:
        from config import INPUT_WAV, OUTPUT_MIDI_1, OUTPUT_MIDI_2, OUTPUT_JSON, WHISPER_LANGUAGE
    except ImportError:
        INPUT_WAV        = "output/outputs/voz_capturada.wav"
        OUTPUT_MIDI_1    = "output/outputs/partitura_etapa1.mid"
        OUTPUT_MIDI_2    = "output/outputs/partitura_etapa2.mid"
        OUTPUT_JSON      = "output/outputs/projeto_karaoke.json"
        WHISPER_LANGUAGE = "pt"

    parser = argparse.ArgumentParser(
        description="Karaoke IA - Pipeline completo de transcricao",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("diagnose", help="Verifica modulos e hardware")

    cap = sub.add_parser("capture", help="Captura audio do sistema")
    cap.add_argument("--duration", "-d", type=float, default=30.0, help="Segundos a capturar")
    cap.add_argument("--output",   "-o", default=INPUT_WAV)

    proc = sub.add_parser("process", help="Processa audio (WAV/MP3/OGG/FLAC)")
    proc.add_argument("audio", help="Arquivo de audio (WAV/MP3/OGG/FLAC)")
    proc.add_argument("--midi-raw",  default=OUTPUT_MIDI_1)
    proc.add_argument("--midi-fix",  default=OUTPUT_MIDI_2)
    proc.add_argument("--json-out",  default=OUTPUT_JSON)
    proc.add_argument("--language",  "-l", default=WHISPER_LANGUAGE)
    proc.add_argument("--tempo",     "-t", type=float, default=120.0)
    proc.add_argument("--no-parallel", action="store_true")

    yt = sub.add_parser("youtube", help="Baixa audio do YouTube e processa")
    yt.add_argument("url", help="URL do video do YouTube")
    yt.add_argument("--language", "-l", default=WHISPER_LANGUAGE)
    yt.add_argument("--tempo",    "-t", type=float, default=120.0)

    exp = sub.add_parser("export", help="Exporta projeto para LRC/TXT")
    exp.add_argument("project", help="Arquivo JSON do projeto")
    exp.add_argument("--format", "-f", choices=["lrc", "txt"], default="lrc")
    exp.add_argument("--output", "-o", default=None, help="Arquivo de saida")

    full = sub.add_parser("full", help="Captura e processa em sequencia")
    full.add_argument("--duration", "-d", type=float, default=30.0)
    full.add_argument("--language", "-l", default=WHISPER_LANGUAGE)
    full.add_argument("--tempo",    "-t", type=float, default=120.0)

    srv = sub.add_parser("serve", help="Inicia API REST + interface web")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", "-p", type=int, default=8000)

    args = parser.parse_args()

    if args.cmd == "diagnose":
        ok = cmd_diagnose()
        sys.exit(0 if ok else 1)

    elif args.cmd == "capture":
        cmd_capture(args.duration, args.output)

    elif args.cmd == "process":
        cmd_process(args.audio, args.midi_raw, args.midi_fix, args.json_out,
                    language=args.language, tempo=args.tempo, parallel=not args.no_parallel)

    elif args.cmd == "youtube":
        cmd_youtube(args.url, language=args.language, tempo=args.tempo)

    elif args.cmd == "export":
        cmd_export(args.project, args.format, args.output)

    elif args.cmd == "full":
        wav = cmd_capture(args.duration, INPUT_WAV)
        cmd_process(wav, OUTPUT_MIDI_1, OUTPUT_MIDI_2, OUTPUT_JSON,
                    language=args.language, tempo=args.tempo)

    elif args.cmd == "serve":
        cmd_serve(args.host, args.port)


if __name__ == "__main__":
    main()
