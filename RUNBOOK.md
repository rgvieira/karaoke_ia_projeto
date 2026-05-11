# Runbook — Instruções de Execução

Guia passo a passo para executar o Karaokê IA em diferentes cenários.

## Índice

- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [Diagnóstico do Sistema](#diagnóstico-do-sistema)
- [Pipeline Completo](#pipeline-completo)
- [YouTube](#youtube)
- [Captura de Áudio](#captura-de-áudio)
- [Processamento Offline](#processamento-offline)
- [Exportação LRC/TXT](#exportação-lrctxt)
- [Interface Web](#interface-web)
- [Servidor API](#servidor-api)
- [Testes](#testes)
- [Solução de Problemas](#solução-de-problemas)
- [Modo Desenvolvimento](#modo-desenvolvimento)

---

## Pré-requisitos

| Requisito | Versão Mínima | Verificar |
|-----------|--------------|-----------|
| Python | 3.10+ | `python --version` |
| pip | 21+ | `pip --version` |
| GPU (opcional) | NVIDIA CUDA | `nvidia-smi` |
| Windows | 10+ | `winver` |

## Instalação

### 1. Ambiente Virtual

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

Para instalação otimizada (sem GPU):

```bash
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

### 3. Verificar Instalação

```bash
python main.py diagnose
```

Saída esperada (todos os módulos OK):

```
=== Diagnóstico do Sistema ===

  [OK] Whisper (transcrição)
  [OK] BasicPitch (audio->MIDI)
  [OK] pretty_midi (correção MIDI)
  [OK] librosa (análise de áudio)
  [OK] pyaudio (captura loopback)
  [OK] noisereduce (redução de ruído)
  [OK] FastAPI (API REST)
  [OK] PyTorch (aceleração GPU)
  [OK] TensorFlow (BasicPitch backend)

  GPU: NVIDIA GeForce RTX 3060 (12.0 GB VRAM)

  Config: Whisper=medium | SR=22050 Hz

=== 9 módulos OK | 0 ausentes ===
```

---

## Pipeline Completo

### Gravar e processar em um comando

```bash
python main.py full --duration 30
```

Captura 30 segundos de áudio do sistema, processa e gera `projeto_karaoke.json`.

### Parâmetros

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `--duration, -d` | 30.0 | Segundos de áudio a capturar |
| `--language, -l` | pt | Idioma para transcrição Whisper |
| `--tempo, -t` | 120 | BPM para quantização MIDI |

### Exemplo com parâmetros

```bash
python main.py full --duration 60 --language en --tempo 140
```

---

## YouTube

### Baixar e processar audio do YouTube

```bash
python main.py youtube "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Isso baixa o audio, converte para WAV e executa o pipeline completo.

### Parametros

| Parametro | Default | Descricao |
|-----------|---------|-----------|
| `url` | (obrigatorio) | URL do video do YouTube |
| `--language, -l` | pt | Idioma para transcricao Whisper |
| `--tempo, -t` | 120 | BPM para quantizacao MIDI |

### Exemplo com parametros

```bash
python main.py youtube "https://youtu.be/abc123" --language en --tempo 140
```

### Requisitos

```bash
pip install yt-dlp
```

---

## Captura de Áudio

### Gravar áudio do sistema

```bash
python main.py capture --duration 120 --output minha_musica.wav
```

### Fallback para microfone

Se o loopback WASAPI falhar, o sistema automaticamente usa o microfone com redução de ruído.

---

## Processamento Offline

### Processar arquivo de audio (WAV/MP3/OGG/FLAC)

```bash
python main.py process caminho/para/audio.wav --language pt --tempo 120
```

MP3, OGG e FLAC sao convertidos automaticamente para WAV:

```bash
python main.py process caminho/para/musica.mp3 --language pt --tempo 120
python main.py process caminho/para/audio.ogg --language en --tempo 140
```

### Arquivos gerados

| Arquivo | Descrição |
|---------|-----------|
| `output/outputs/partitura_etapa1.mid` | MIDI bruto do BasicPitch |
| `output/outputs/partitura_etapa2.mid` | MIDI corrigido (quantizado, escala) |
| `output/outputs/projeto_karaoke.json` | JSON final do karaokê |

### Saída esperada

```
14:30:22 [INFO] main: [ 1/3 ] BasicPitch: audio -> MIDI bruto
14:30:45 [INFO] main:         42 notas detectadas em 23.1s
14:30:45 [INFO] main: [ 2/3 ] Correção MIDI: quantizacao + tonalidade
14:30:46 [INFO] main:         40 notas (2 filtradas) | C major em 0.8s
14:30:46 [INFO] main: [ 3/3 ] Montando JSON (Whisper + MIDI)
14:31:10 [INFO] main:         JSON salvo em 24.0s

=== Pipeline concluído em 48.0s ===
  Notas   : 40
  Segmentos: 8
  Duração : 30.0s
  Saída   : output/outputs/projeto_karaoke.json
```

---

## Exportacao LRC/TXT

### Exportar projeto para formato LRC (letra sincronizada)

```bash
python main.py export output/outputs/projeto_karaoke.json --format lrc
```

Isso gera `projeto_karaoke.lrc` no mesmo diretorio.

### Opcoes

| Parametro | Default | Descricao |
|-----------|---------|-----------|
| `project` | (obrigatorio) | Caminho do JSON do projeto |
| `--format, -f` | lrc | Formato de saida: `lrc` ou `txt` |
| `--output, -o` | (auto) | Caminho do arquivo de saida |

### Exemplos

```bash
python main.py export projeto.json -f lrc -o musica.lrc
python main.py export projeto.json -f txt
```

---

## Interface Web

### Iniciar servidor com player de karaoke

```bash
python main.py serve
```

Acesse: http://127.0.0.1:8000/api/web

### Funcionalidades do player

- Upload de arquivo de audio (WAV/MP3/OGG)
- Download de audio do YouTube por URL
- Letra sincronizada com destaque palavra-a-palavra
- Barra de meta (BPM, tom, duracao)
- Piano roll simplificado
- Exportacao LRC e JSON diretamente da界面

---

## Servidor API

### Iniciar servidor

```bash
python main.py serve
```

Acesse:
- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

### Endpoints principais

| Método | Rota | Exemplo |
|--------|------|---------|
| POST | `/pipeline/full` | Upload WAV + processamento completo |
| POST | `/upload` | Upload de arquivo de áudio |
| POST | `/transcribe` | Transcrição Whisper |
| POST | `/audio-to-midi` | Conversão áudio → MIDI |
| POST | `/correct-midi` | Correção MIDI |
| POST | `/assemble` | Montagem do JSON |

### Exemplo com curl

```bash
# Pipeline completo em uma chamada
curl -X POST http://127.0.0.1:8000/pipeline/full \
  -F "file=@musica.wav" \
  -F "language=pt" \
  -F "tempo=120"
```

---

## Testes

### Executar todos os testes

```bash
python -m pytest tests/ -v
```

### Testes rápidos (sem modelos de ML)

```bash
python -m pytest tests/ -v -k "not slow"
```

### Testes de integração (requer modelos)

```bash
python -m pytest tests/ -v -m slow
```

### Com cobertura

```bash
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## Solução de Problemas

### Erro: `ModuleNotFoundError: No module named 'torch'`

O PyTorch é opcional (apenas para detecção de GPU). Instale:

```bash
pip install torch
```

Ou ignore — o sistema funciona em CPU sem PyTorch.

### Erro: `paWASAPI not found`

PyAudio WASAPI requer o Microsoft Visual C++ Redistributable.
Instale via wheel:

```bash
pip install pipwin
pipwin install pyaudio
```

### Erro: BasicPitch sem GPU (lento)

Force CPU:

```powershell
# Windows PowerShell
$env:CUDA_VISIBLE_DEVICES="-1"
python main.py process entrada.wav
```

```bash
# Linux/macOS
CUDA_VISIBLE_DEVICES=-1 python main.py process entrada.wav
```

### Erro: Whisper sem memória

Reduza o modelo em `config.py`:

```python
WHISPER_MODEL_SIZE = "tiny"  # ou "base"
```

### Erro: Encoding Unicode no terminal

```powershell
# Windows PowerShell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

---

## Modo Desenvolvimento

### Instalar em modo editável

```bash
pip install -e .
```

### Rodar com reload automático (API)

```bash
uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
```

### Verificar qualidade do código

```bash
pip install ruff mypy
ruff check .
mypy .
```

### Perfil de performance

```bash
python -m cProfile -o profile.prof main.py process entrada.wav
python -m pstats profile.prof
```
