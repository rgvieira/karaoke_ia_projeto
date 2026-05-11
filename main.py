"""
main.py — Orquestrador do Pipeline Karaokê IA
Uso: python main.py [modo] [opções]

Modos:
  capture   Captura áudio do sistema (loopback WASAPI)
  process   Processa WAV existente → JSON de karaokê
  full      Captura + processa em sequência
  serve     Inicia API REST local (FastAPI)
  diagnose  Verifica módulos e hardware disponíveis
"""

import argparse
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
    """Verifica disponibilidade de todos os módulos e hardware."""
    print("\n=== Diagnóstico do Sistema ===\n")

    checks = {
        "faster_whisper":  "Whisper (transcrição)",
        "basic_pitch":     "BasicPitch (audio->MIDI)",
        "pretty_midi":     "pretty_midi (correção MIDI)",
        "librosa":         "librosa (análise de áudio)",
        "pyaudio":         "pyaudio (captura loopback)",
        "noisereduce":     "noisereduce (redução de ruído)",
        "fastapi":         "FastAPI (API REST)",
        "torch":           "PyTorch (aceleração GPU)",
        "tensorflow":      "TensorFlow (BasicPitch backend)",
    }

    ok = failed = 0
    for module, label in checks.items():
        try:
            __import__(module)
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
            print("\n  GPU: não disponível — usando CPU")
    except ImportError:
        pass

    try:
        import config
        print(f"\n  Config: Whisper={config.WHISPER_MODEL_SIZE} | "
              f"SR={config.BASICPITCH_SAMPLE_RATE} Hz")
    except ImportError:
        print("\n  config.py: não encontrado")

    print(f"\n=== {ok} módulos OK | {failed} ausentes ===\n")
    return failed == 0


def cmd_capture(duration: float, output: str):
    """Captura áudio do sistema."""
    try:
        from audio_capture.loopback import capture_audio
    except ImportError as e:
        logger.error(f"Módulo de captura indisponível: {e}")
        sys.exit(1)

    logger.info(f"Capturando {duration}s de audio -> {output}")
    path = capture_audio(duration, output_path=output)
    logger.info(f"Áudio salvo: {path}")
    return path


def cmd_process(
    wav_path: str,
    midi_raw:  str,
    midi_fix:  str,
    json_out:  str,
    language:  str = "pt",
    tempo:     float = 120.0,
    parallel:  bool = True,
):
    """Processa WAV existente → JSON de karaokê completo."""
    from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
    from midi_tools.note_corrector import correct_midi
    from output.output_generator import assemble_project

    t_total = time.perf_counter()

    # ── Etapa 1: BasicPitch ──────────────────────────────────────────────────
    logger.info("[ 1/3 ] BasicPitch: audio -> MIDI bruto")
    t0    = time.perf_counter()
    notes = transcribe_with_basicpitch(wav_path, midi_raw)
    logger.info(f"        {len(notes)} notas detectadas em {time.perf_counter()-t0:.1f}s")

    # ── Etapa 2: Correção MIDI ───────────────────────────────────────────────
    logger.info("[ 2/3 ] Correcao MIDI: quantizacao + tonalidade")
    t0    = time.perf_counter()
    stats = correct_midi(midi_raw, midi_fix, audio_path=wav_path, tempo=tempo)
    logger.info(
        f"        {stats['notes_out']} notas ({stats['filtered']} filtradas) "
        f"| {stats['key'].get('root','?')} {stats['key'].get('mode','?')} "
        f"em {time.perf_counter()-t0:.1f}s"
    )

    # ── Etapa 3: Montagem JSON ───────────────────────────────────────────────
    logger.info("[ 3/3 ] Montando JSON (Whisper + MIDI)")
    t0   = time.perf_counter()
    proj = assemble_project(
        midi_fix, wav_path,
        output_json=json_out,
        tempo=tempo,
        key_info=stats.get("key"),
        language=language,
        parallel=parallel,
    )
    logger.info(f"        JSON salvo em {time.perf_counter()-t0:.1f}s")

    elapsed = time.perf_counter() - t_total
    logger.info(
        f"\n=== Pipeline concluído em {elapsed:.1f}s ===\n"
        f"  Notas   : {proj['meta']['n_notes']}\n"
        f"  Segmentos: {proj['meta']['n_segs']}\n"
        f"  Duração : {proj['meta']['dur_ms']/1000:.1f}s\n"
        f"  Saída   : {json_out}\n"
    )
    return proj


def cmd_serve(host: str = "127.0.0.1", port: int = 8000):
    """Inicia o servidor FastAPI."""
    try:
        import uvicorn
        from api.server import app
    except ImportError as e:
        logger.error(f"FastAPI/uvicorn não instalado: {e}")
        sys.exit(1)

    logger.info(f"Iniciando API em http://{host}:{port}")
    logger.info(f"Docs: http://{host}:{port}/docs")
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
        description="Karaokê IA — Pipeline completo de transcrição",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # diagnose
    sub.add_parser("diagnose", help="Verifica módulos e hardware")

    # capture
    cap = sub.add_parser("capture", help="Captura áudio do sistema")
    cap.add_argument("--duration", "-d", type=float, default=30.0, help="Segundos a capturar")
    cap.add_argument("--output",   "-o", default=INPUT_WAV)

    # process
    proc = sub.add_parser("process", help="Processa WAV existente")
    proc.add_argument("wav",               help="Arquivo WAV de entrada")
    proc.add_argument("--midi-raw",  default=OUTPUT_MIDI_1)
    proc.add_argument("--midi-fix",  default=OUTPUT_MIDI_2)
    proc.add_argument("--json-out",  default=OUTPUT_JSON)
    proc.add_argument("--language",  "-l", default=WHISPER_LANGUAGE)
    proc.add_argument("--tempo",     "-t", type=float, default=120.0)
    proc.add_argument("--no-parallel", action="store_true")

    # full
    full = sub.add_parser("full", help="Captura e processa em sequência")
    full.add_argument("--duration", "-d", type=float, default=30.0)
    full.add_argument("--language", "-l", default=WHISPER_LANGUAGE)
    full.add_argument("--tempo",    "-t", type=float, default=120.0)

    # serve
    srv = sub.add_parser("serve", help="Inicia API REST")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", "-p", type=int, default=8000)

    args = parser.parse_args()

    if args.cmd == "diagnose":
        ok = cmd_diagnose()
        sys.exit(0 if ok else 1)

    elif args.cmd == "capture":
        cmd_capture(args.duration, args.output)

    elif args.cmd == "process":
        cmd_process(
            args.wav, args.midi_raw, args.midi_fix, args.json_out,
            language=args.language, tempo=args.tempo,
            parallel=not args.no_parallel,
        )

    elif args.cmd == "full":
        wav = cmd_capture(args.duration, INPUT_WAV)
        cmd_process(
            wav, OUTPUT_MIDI_1, OUTPUT_MIDI_2, OUTPUT_JSON,
            language=args.language, tempo=args.tempo,
        )

    elif args.cmd == "serve":
        cmd_serve(args.host, args.port)


if __name__ == "__main__":
    main()
