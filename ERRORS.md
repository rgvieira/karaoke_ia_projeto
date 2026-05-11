# Histórico de Erros

Este arquivo registra bugs encontrados, suas causas raiz, soluções e prevenções.
Mantenha atualizado seguindo o guia em [MAINTENANCE.md](MAINTENANCE.md).

---

## Formato

Cada entrada deve seguir este modelo:

```markdown
## [YYYY-MM-DD] Título Resumido

### Descrição
Breve descrição do erro e seus sintomas.

### Causa Raiz
O que originou o problema.

### Solução
Como foi corrigido (com links para commits/PRs quando possível).

### Prevenção
Como evitar que o erro ocorra novamente.

### Arquivos Afetados
- `caminho/para/arquivo.py:linha`
- `caminho/para/outro.py:linha`

### Testes
- `testes/relacionados.py`
```

---

<!--
  ═════════════════════════════════════════════════════════════════════
  NOVOS ERROS: adicione no TOPO desta seção (mais recente primeiro)
  ═════════════════════════════════════════════════════════════════════
-->

## [2025-05-10] UnicodeEncodeError em terminais Windows

### Descrição
Comandos como `python main.py diagnose` lançavam `UnicodeEncodeError` em terminais
Windows com codificação cp1252 ao tentar imprimir caracteres Unicode
(`║`, `→`, `…`, `✓`, `✗`).

### Causa Raiz
O terminal Windows (cmd/PowerShell) usa cp1252 como codificação padrão, que não
suporta box-drawing characters (U+2550+) nem setas (U+2192).

### Solução
Substituídos todos os caracteres Unicode não-ASCII em strings de saída por
alternativas ASCII:
- `═══` → `===`
- `✓` → `[OK]`
- `✗` → `[--]`
- `→` → `->`
- `…` → `` (removido)

### Prevenção
Em qualquer nova string de saída (print/log), use apenas ASCII básico.
Para logs use inglês ou português sem acentos nem caracteres especiais.

### Arquivos Afetados
- `main.py:29,47,50,83,106,112,122`

### Testes
- N/A (erro de encoding de terminal)

---

## [2025-05-10] ModuleNotFoundError no config.py ao importar torch

### Descrição
`config.py` importava `torch` no módulo nível. Sem PyTorch instalado, qualquer
import de `config` falhava com `ModuleNotFoundError`, quebrando todo o pipeline.

### Causa Raiz
`import torch` sem try/except no topo do módulo.

### Solução
Envolvido o import em try/except com flag `_TORCH_OK`. Toda detecção de GPU
passou a verificar `_TORCH_OK` antes de acessar torch.

### Prevenção
Nunca importe bibliotecas opcionais no nível do módulo sem try/except.
Use flags booleanas para indicar disponibilidade.

### Arquivos Afetados
- `config.py:7-12`

### Testes
- N/A (testes não rodam com torch ausente)

---

## [2025-05-10] ImportError no output_generator.py sem faster-whisper

### Descrição
`output_generator.py` importava `transcribe` do `whisper_client` no nível do
módulo, causando `ImportError` se faster-whisper não estivesse instalado, mesmo
que o módulo só fosse usado na função `assemble_project`.

### Causa Raiz
Import no topo do arquivo de um módulo com dependências pesadas.

### Solução
Movido o import de `from lyrics_sync.whisper_client import transcribe` para
dentro das funções `assemble_project` e `_assemble_parallel` (lazy import).

### Prevenção
Use lazy imports para módulos com dependências pesadas ou opcionais.

### Arquivos Afetados
- `output/output_generator.py:31`

### Testes
- `tests/test_pipeline.py:255-275`
