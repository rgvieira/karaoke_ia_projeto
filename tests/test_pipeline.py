"""
tests/test_pipeline.py
Suite de testes automatizados com pytest.
Testa cada módulo de forma isolada, usando fixtures de áudio/MIDI sintéticos.
"""

import json
import math
import os
import struct
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _generate_sine_wav(path: str, freq: float = 440.0, duration: float = 2.0,
                        sr: int = 22050, amplitude: float = 0.5):
    """Gera WAV sintético com tom puro."""
    t      = np.linspace(0, duration, int(sr * duration), endpoint=False)
    signal = (amplitude * np.sin(2 * math.pi * freq * t) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(signal.tobytes())


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sine_wav(tmp_dir):
    path = str(tmp_dir / "sine_440.wav")
    _generate_sine_wav(path, freq=440.0, duration=2.0)
    return path


@pytest.fixture
def multi_tone_wav(tmp_dir):
    """WAV com sequência de notas para BasicPitch."""
    sr       = 22050
    duration = 0.5   # segundos por nota
    freqs    = [261.63, 293.66, 329.63, 349.23]  # C4 D4 E4 F4
    segments = []
    for f in freqs:
        t   = np.linspace(0, duration, int(sr * duration), endpoint=False)
        seg = (0.5 * np.sin(2 * math.pi * f * t) * 32767).astype(np.int16)
        segments.append(seg)
    signal = np.concatenate(segments)

    path = str(tmp_dir / "melody.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(signal.tobytes())
    return path


@pytest.fixture
def simple_midi(tmp_dir):
    """Cria MIDI sintético com pretty_midi."""
    pytest.importorskip("pretty_midi")
    import pretty_midi
    pm   = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=0)
    for i, pitch in enumerate([60, 62, 64, 65]):
        note = pretty_midi.Note(velocity=80, pitch=pitch,
                                start=i * 0.5, end=i * 0.5 + 0.4)
        inst.notes.append(note)
    pm.instruments.append(inst)
    path = str(tmp_dir / "test.mid")
    pm.write(path)
    return path


# ─── config.py ───────────────────────────────────────────────────────────────

class TestConfig:
    def test_imports(self):
        import config
        assert hasattr(config, "WHISPER_MODEL_SIZE")
        assert hasattr(config, "BASICPITCH_SAMPLE_RATE")
        assert config.BASICPITCH_SAMPLE_RATE == 22050

    def test_output_dir_created(self):
        import config
        assert Path(config.OUTPUT_DIR).exists()


# ─── whisper_client.py ───────────────────────────────────────────────────────

class TestWhisperClient:
    def test_import(self):
        from lyrics_sync import whisper_client  # noqa: F401

    def test_get_model_returns_same_instance(self):
        pytest.importorskip("faster_whisper")
        from lyrics_sync.whisper_client import get_model
        m1 = get_model()
        m2 = get_model()
        assert m1 is m2, "Modelo deve ser singleton (mesmo objeto)"

    def test_transcribe_returns_dict(self, sine_wav):
        pytest.importorskip("faster_whisper")
        from lyrics_sync.whisper_client import transcribe
        result = transcribe(sine_wav)
        assert isinstance(result, dict)
        assert "segments" in result
        assert "language" in result
        assert "duration_s" in result

    def test_transcribe_file_not_found(self):
        pytest.importorskip("faster_whisper")
        from lyrics_sync.whisper_client import transcribe
        with pytest.raises(FileNotFoundError):
            transcribe("/tmp/nao_existe.wav")

    def test_word_timestamps_format(self, sine_wav):
        pytest.importorskip("faster_whisper")
        from lyrics_sync.whisper_client import transcribe
        result = transcribe(sine_wav, word_timestamps=True)
        for seg in result["segments"]:
            assert "words" in seg
            for w in seg["words"]:
                assert "w" in w
                assert "s" in w
                assert "e" in w
                assert w["s"] <= w["e"]


# ─── basicpitch_gateway.py ───────────────────────────────────────────────────

class TestBasicpitchGateway:
    def test_import(self):
        from audio_to_midi import basicpitch_gateway  # noqa: F401

    def test_load_audio(self, sine_wav):
        pytest.importorskip("librosa")
        from audio_to_midi.basicpitch_gateway import _load_audio
        audio, sr = _load_audio(sine_wav)
        assert sr == 22050
        assert len(audio) > 0

    def test_transcribe_returns_notes(self, multi_tone_wav, tmp_dir):
        pytest.importorskip("basic_pitch")
        from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
        midi_out = str(tmp_dir / "out.mid")
        notes = transcribe_with_basicpitch(multi_tone_wav, midi_out)
        assert isinstance(notes, list)
        assert Path(midi_out).exists()

    def test_transcribe_file_not_found(self, tmp_dir):
        pytest.importorskip("basic_pitch")
        from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
        with pytest.raises(FileNotFoundError):
            transcribe_with_basicpitch("/tmp/nao_existe.wav", str(tmp_dir / "x.mid"))


# ─── note_corrector.py ───────────────────────────────────────────────────────

class TestNoteCorrector:
    def test_import(self):
        from midi_tools import note_corrector  # noqa: F401

    def test_get_scale_pitches_c_major(self):
        from midi_tools.note_corrector import get_scale_pitches
        pcs = get_scale_pitches(0, "major")   # C maior
        assert 0 in pcs   # C
        assert 2 in pcs   # D
        assert 4 in pcs   # E
        assert 1 not in pcs  # C# fora da escala

    def test_nearest_in_scale(self):
        from midi_tools.note_corrector import _nearest_in_scale, get_scale_pitches
        scale = get_scale_pitches(0, "major")  # C maior
        # C# (61) → deve ir para C (60) ou D (62)
        result = _nearest_in_scale(61, scale)
        assert result % 12 in scale

    def test_quantize_time(self):
        from midi_tools.note_corrector import _quantize_time
        # Em 120 BPM, 1 batida = 0.5s; grid 1/8 = 0.0625s
        q = _quantize_time(0.07, 0.125, 120)
        # Deve ser múltiplo de 0.0625
        assert abs(q % 0.0625) < 1e-6

    def test_correct_midi_pipeline(self, simple_midi, tmp_dir, sine_wav):
        pytest.importorskip("pretty_midi")
        from midi_tools.note_corrector import correct_midi
        out = str(tmp_dir / "corrected.mid")
        stats = correct_midi(simple_midi, out, audio_path=sine_wav)
        assert Path(out).exists()
        assert "notes_in" in stats
        assert "notes_out" in stats
        assert stats["notes_out"] <= stats["notes_in"]

    def test_detect_key_from_audio(self, sine_wav):
        pytest.importorskip("librosa")
        from midi_tools.note_corrector import detect_key
        root, mode = detect_key(audio_path=sine_wav)
        assert 0 <= root <= 11
        assert mode in ("major", "minor")

    def test_remove_polyphony(self):
        from midi_tools.note_corrector import _remove_polyphony
        pytest.importorskip("pretty_midi")
        import pretty_midi

        # Duas notas sobrepostas
        n1 = pretty_midi.Note(80, 60, 0.0, 1.0)
        n2 = pretty_midi.Note(80, 64, 0.3, 1.2)  # sobreposição
        result = _remove_polyphony([n1, n2], max_voices=1)
        assert len(result) == 1


# ─── output_generator.py ─────────────────────────────────────────────────────

class TestOutputGenerator:
    def test_import(self):
        from output import output_generator  # noqa: F401

    def test_midi_to_note_list(self, simple_midi):
        pytest.importorskip("pretty_midi")
        from output.output_generator import midi_to_note_list
        notes = midi_to_note_list(simple_midi)
        assert len(notes) == 4
        for note in notes:
            assert "n" in note
            assert "s_ms" in note
            assert "d_ms" in note
            assert note["d_ms"] > 0

    def test_format_lyrics(self):
        from output.output_generator import _format_lyrics
        segments = [
            {"text": "Olá mundo", "start": 0.0, "end": 1.5,
             "words": [{"w": "Olá", "s": 0, "e": 500}, {"w": "mundo", "s": 600, "e": 1500}]},
        ]
        out = _format_lyrics(segments)
        assert len(out) == 1
        assert out[0]["t"] == "Olá mundo"
        assert out[0]["s"] == 0
        assert out[0]["e"] == 1500
        assert len(out[0]["w"]) == 2

    def test_assemble_project_creates_json(self, simple_midi, sine_wav, tmp_dir):
        pytest.importorskip("faster_whisper")
        pytest.importorskip("pretty_midi")
        from output.output_generator import assemble_project
        json_out = str(tmp_dir / "karaoke.json")
        proj = assemble_project(simple_midi, sine_wav, output_json=json_out)
        assert Path(json_out).exists()
        assert proj["pv"] == "1.1"
        assert "notes" in proj
        assert "lyrics" in proj
        assert "meta" in proj

    def test_json_is_compact(self, simple_midi, sine_wav, tmp_dir):
        """Verifica que o JSON não tem indentação (modo compacto)."""
        pytest.importorskip("faster_whisper")
        pytest.importorskip("pretty_midi")
        from output.output_generator import assemble_project
        json_out = str(tmp_dir / "compact.json")
        assemble_project(simple_midi, sine_wav, output_json=json_out)
        raw = Path(json_out).read_text(encoding="utf-8")
        assert "\n  " not in raw, "JSON não deve ter indentação"


# ─── Testes de integração ─────────────────────────────────────────────────────

class TestIntegration:
    @pytest.mark.slow
    def test_full_pipeline(self, multi_tone_wav, tmp_dir):
        """Pipeline completo: WAV → MIDI → correção → JSON."""
        pytest.importorskip("basic_pitch")
        pytest.importorskip("faster_whisper")
        pytest.importorskip("pretty_midi")

        from audio_to_midi.basicpitch_gateway import transcribe_with_basicpitch
        from midi_tools.note_corrector import correct_midi
        from output.output_generator import assemble_project

        midi_raw = str(tmp_dir / "raw.mid")
        midi_fix = str(tmp_dir / "fixed.mid")
        json_out = str(tmp_dir / "karaoke.json")

        # Etapa 1: BasicPitch
        notes = transcribe_with_basicpitch(multi_tone_wav, midi_raw)
        assert len(notes) > 0

        # Etapa 2: Correção
        stats = correct_midi(midi_raw, midi_fix, audio_path=multi_tone_wav)
        assert stats["notes_out"] > 0

        # Etapa 3: JSON
        proj = assemble_project(
            midi_fix, multi_tone_wav, output_json=json_out,
            key_info=stats.get("key"), parallel=False
        )
        assert Path(json_out).exists()
        data = json.loads(Path(json_out).read_text())
        assert data["meta"]["n_notes"] > 0
