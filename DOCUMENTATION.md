# Documentação Técnica — Karaokê IA

## Arquitetura

O sistema é organizado em módulos independentes que se comunicam através de interfaces bem definidas. Cada módulo pode ser usado isoladamente ou como parte do pipeline completo.

```
Audio Source (WAV/Mic)
       │
       ▼
┌──────────────────────────────────┐
│  audio_capture/loopback.py       │
│  WASAPI loopback ou microfone    │
│  + redução de ruído (noisereduce)│
└────────────┬─────────────────────┘
             │ WAV
             ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  audio_to_midi/           │    │  lyrics_sync/             │
│  basicpitch_gateway.py    │    │  whisper_client.py        │
│  BasicPitch → MIDI bruto  │    │  faster-whisper → letras  │
└──────────┬────────────────┘    └───────────┬────────────────┘
           │ MIDI                            │ JSON segments
           ▼                                 ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  midi_tools/              │    │  output/                  │
│  note_corrector.py        │    │  output_generator.py      │
│  Quantização + tonalidade │    │  Montagem JSON final      │
│  Correção de escala       │    │  (MIDI + letras + meta)   │
└──────────┬────────────────┘    └───────────┬────────────────┘
           │ MIDI corrigido                  │
           └──────────────┬──────────────────┘
                          ▼
              ┌──────────────────────┐
              │  projeto_karaoke.json │
              │  Formato compacto     │
              └──────────────────────┘
```

## Módulos

### 1. Captura de Áudio (`audio_capture/loopback.py`)

Captura áudio do sistema usando WASAPI loopback (Windows). Se loopback não estiver disponível, faz fallback para microfone com redução de ruído.

**Classe principal:** `AudioCapture`

- `start()` — inicia a captura em thread separada
- `stop()` — finaliza e salva WAV
- `capture_audio(duration, output_path)` — função de conveniência

**Detalhes técnicos:**
- Sample rate: 44100 Hz
- Formato: 16-bit PCM, mono
- Redução de ruído via `noisereduce` (amostra dos primeiros 500ms)
- Normalização automática (pico 95%)
- Suporte a gravação temporizada ou manual

### 2. Áudio → MIDI (`audio_to_midi/basicpitch_gateway.py`)

Converte áudio para MIDI usando o modelo BasicPitch do Spotify.

**Função principal:** `transcribe_with_basicpitch(wav_path, midi_out_path)`

**Detalhes técnicos:**
- Reamostragem para 22050 Hz (reduz carga de memória)
- Cache do modelo em singleton (carregado uma vez)
- Liberação automática de VRAM após inferência (`tf.keras.backend.clear_session()` + `torch.cuda.empty_cache()`)
- Fallback para scipy se librosa não estiver disponível

### 3. Correção MIDI (`midi_tools/note_corrector.py`)

Pós-processamento do MIDI bruto para melhorar qualidade musical.

**Pipeline de correção:**

1. **Filtro de duração mínima** — remove notas < 50ms (ruído)
2. **Quantização rítmica** — alinha notas à grade (1/8 de batida por padrão)
3. **Detecção de tonalidade** — via chroma CQT com perfis Krumhansl
4. **Correção de escala** — move notas cromáticas para o grau mais próximo da escala
5. **Remoção de polifonia** — mantém apenas a nota mais alta em sobreposições (voz solo)
6. **Ordenação** — notas classificadas por tempo de início

### 4. Transcrição de Letras (`lyrics_sync/whisper_client.py`)

Transcrição de áudio com timestamps por palavra usando faster-whisper.

**Função principal:** `transcribe(audio_path, language, word_timestamps, ...)`

**Detalhes técnicos:**
- Cache singleton do modelo Whisper
- Suporte a VAD (Voice Activity Detection) para filtrar silêncio
- Timestamps por palavra para sincronização precisa
- Retorno de confiança por palavra (`probability`)
- RTF (Real-Time Factor) reportado no log

### 5. Gerador de Saída (`output/output_generator.py`)

Monta o JSON final combinando MIDI e letras.

**Formato do JSON:**

```json
{
  "pv": "1.1",
  "src": "musica.wav",
  "lang": "pt",
  "notes": [
    {"n": 60, "s_ms": 0, "d_ms": 500, "v": 80}
  ],
  "lyrics": [
    {
      "t": "Olá mundo",
      "s": 0,
      "e": 1500,
      "w": [
        {"w": "Olá", "s": 0, "e": 500},
        {"w": "mundo", "s": 600, "e": 1500}
      ]
    }
  ],
  "meta": {
    "bpm": 120,
    "dur_ms": 15000,
    "key": {"root": "C", "mode": "major"},
    "n_notes": 42,
    "n_segs": 8
  }
}
```

**Modo paralelo:** executa extração MIDI e transcrição Whisper em threads simultâneas.

### 6. API REST (`api/server.py`)

Servidor FastAPI com CORS habilitado.

**Endpoints:**

| Método | Rota                  | Descrição                                      |
|--------|-----------------------|------------------------------------------------|
| GET    | `/`                   | Status da API                                  |
| GET    | `/health`             | Health check com status de cada módulo         |
| POST   | `/upload`             | Upload de arquivo de áudio (WAV/MP3/OGG/FLAC) |
| POST   | `/transcribe`         | Transcrição Whisper com timestamps por palavra |
| POST   | `/audio-to-midi`      | Conversão áudio WAV → MIDI via BasicPitch      |
| POST   | `/correct-midi`       | Correção MIDI (quantização + tonalidade)       |
| POST   | `/assemble`           | Montagem do JSON final (MIDI + letras)         |
| GET    | `/download/json`      | Download do JSON do projeto                    |
| GET    | `/download/midi`      | Download de arquivo MIDI                       |
| POST   | `/pipeline/full`      | Pipeline completo: upload → JSON em uma chamada|

## Configuração

Todas as configurações estão centralizadas em `config.py` com detecção automática de hardware:

- **Whisper:** modelo `large` se VRAM ≥ 6GB, `medium` se ≥ 4GB, `small` caso contrário
- **Device:** `cuda` se disponível, `cpu` caso contrário
- **Compute type:** `float16` (GPU) ou `int8` (CPU)

## Dependências

Agrupadas por função no `requirements.txt`:

- **Core:** faster-whisper, basic-pitch, pretty_midi, librosa, mido
- **Áudio:** pyaudio, sounddevice, noisereduce
- **API:** fastapi, uvicorn, python-multipart
- **ML:** torch, tensorflow, numpy, scipy
- **Testes:** pytest, pytest-asyncio, httpx

## Testes

```bash
pytest tests/ -v              # Testes rápidos (sem modelos)
pytest tests/ -v -m slow      # Testes completos (requer modelos)
pytest tests/ --coverage       # Cobertura de código
```

## Solução de Problemas

### PyAudio não encontra dispositivos loopback
Instale o PyAudio via wheel: `pip install pipwin && pipwin install pyaudio`

### BasicPitch falha sem GPU
Forçar CPU: defina a variável `CUDA_VISIBLE_DEVICES=-1` antes de executar.

### Whisper com pouca memória
Reduza o modelo em `config.py`: `WHISPER_MODEL_SIZE = "tiny"` ou `"base"`.

### Erro "No module named 'torch'"
O PyTorch é opcional (apenas para detecção de GPU). Instale com `pip install torch` ou ignore.
