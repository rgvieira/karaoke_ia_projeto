# Changelog

## [1.1.0] - 2025-05-10

### Adicionado
- Pipeline paralelo (Whisper + MIDI simultâneos) — economia de 30-50% no tempo
- API REST completa com FastAPI (upload, transcrição, correção, assemble, download)
- Endpoint `/pipeline/full` — pipeline completo em uma chamada
- Cache singleton do modelo Whisper (evita recarregamento)
- Detecção de tonalidade via chroma CQT (librosa)
- Correção de escala com perfis Krumhansl
- Redução de ruído com noisereduce (fallback microfone)
- Suporte a WASAPI loopback no Windows
- Testes automatizados com pytest (isolados + integração)
- Formato JSON compacto (chaves curtas, sem indentação)
- Detecção automática de GPU/VRAM para ajuste do modelo Whisper

### Corrigido
- Liberação de VRAM após inferência BasicPitch
- Fallback para scipy quando librosa não disponível
- Tratamento de dispositivos loopback WASAPI
- Polifonia removida para vozes solo

## [1.0.0] - 2025-03-15

### Adicionado
- Pipeline básico: captura de áudio → BasicPitch → MIDI → Whisper → JSON
- CLI com modos capture, process, full, serve, diagnose
- Configuração centralizada via config.py
- Suporte a GPU (CUDA)
