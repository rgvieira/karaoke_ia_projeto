# Guia de Manutenção

Este documento descreve como manter os arquivos de documentação, histórico de erros e changelog atualizados.

## Índice

- [Fluxo de Manutenção](#fluxo-de-manutenção)
- [Documentação](#documentação)
- [Histórico de Erros](#histórico-de-erros)
- [Changelog](#changelog)
- [Script de Automação](#script-de-automação)

---

## Fluxo de Manutenção

### Ao implementar uma nova funcionalidade:

1. Atualize `README.md` (seção de funcionalidades)
2. Atualize `DOCUMENTATION.md` (arquitetura, novos módulos)
3. Adicione entry em `CHANGELOG.md` sob `## [Não publicado]`
4. Se houver novos endpoints, documente em `DOCUMENTATION.md` (tabela de rotas)
5. Se houver novas dependências, atualize `requirements.txt` e `pyproject.toml`
6. Atualize `RUNBOOK.md` se novos comandos foram adicionados

### Ao corrigir um bug:

1. Registre o erro em `ERRORS.md` (veja modelo abaixo)
2. Adicione entry em `CHANGELOG.md` sob `### Corrigido`
3. Se o bug afetou a API, atualize `api/server.py` e `DOCUMENTATION.md`

### Ao alterar configurações:

1. Atualize `config.py` (novas variáveis)
2. Atualize `.env.example` se aplicável
3. Atualize `DOCUMENTATION.md` (seção de configuração)
4. Atualize `README.md` se a configuração for de alto nível

---

## Documentação

### Arquivos e Responsabilidades

#### Documentação do Projeto

| # | Arquivo | Conteúdo | Público-alvo | Quando atualizar |
|---|---------|----------|--------------|------------------|
| 1 | `README.md` | Visão geral, instalação rápida, exemplos de uso, tecnologias | Usuários finais | Nova funcionalidade, mudança de CLI |
| 2 | `DOCUMENTATION.md` | Arquitetura detalhada, módulos, endpoints API, troubleshooting | Desenvolvedores | Mudança estrutural, novos endpoints |
| 3 | `RUNBOOK.md` | Instruções passo a passo de execução, exemplos com saída esperada | Operadores / DevOps | Novos comandos, mudança de fluxo |
| 4 | `MAINTENANCE.md` | Guia de manutenção de documentação, erros e changelog | Mantenedores | Quando o fluxo de manutenção mudar |
| 5 | `CONTRIBUTING.md` | Guia para contribuidores, padrões de código, testes | Contribuidores externos | Mudança no estilo de código, testes |
| 6 | `CHANGELOG.md` | Histórico de versões (SemVer), registro de mudanças | Todos | Cada alteração relevante |
| 7 | `ERRORS.md` | Histórico de erros conhecidos, causas, soluções e prevenções | Desenvolvedores / Suporte | Cada bug corrigido |
| 8 | `.env.example` | Template de variáveis de ambiente com valores padrão | Desenvolvedores | Nova variável de ambiente |

#### Configuração e Empacotamento

| # | Arquivo | Conteúdo | Quando atualizar |
|---|---------|----------|------------------|
| 9 | `config.py` | Configurações centralizadas do pipeline (hardware, modelos, paths) | Nova configuração, mudança de hardware |
| 10 | `pyproject.toml` | Metadados do projeto, dependências, scripts, ferramentas | Bump de versão, nova dependência |
| 11 | `requirements.txt` | Dependências Python com versões mínimas | Nova dependência, atualização de versão |
| 12 | `.gitignore` | Padrões de arquivos ignorados pelo git | Nova ferramenta que gera artefatos |

#### Automação

| # | Arquivo | Conteúdo | Quando atualizar |
|---|---------|----------|------------------|
| 13 | `scripts/update_docs.py` | Script de automação para docs, changelog e versionamento | Nova funcionalidade no script |
| 14 | `main.py` | CLI / orquestrador do pipeline | Novo modo de execução |

### Convenções de Documentação

- Use **português** para documentação do projeto
- Markdown com formatação limpa (sem HTML)
- Exemplos de código executáveis sempre que possível
- Mantenha exemplos de CLI atualizados com a saída real

---

## Histórico de Erros

O arquivo `ERRORS.md` registra bugs, soluções e prevenções. Use o modelo abaixo:

```markdown
## [YYYY-MM-DD] Título do Erro

### Descrição
Descreva o erro de forma clara e objetiva.

### Causa Raiz
O que causou o erro.

### Solução
Como foi corrigido.

### Prevenção
Como evitar que ocorra novamente.

### Arquivos Afetados
- `caminho/para/arquivo.py:linha`
```

### Erros Registrados

<!-- Novos erros devem ser adicionados no TOPO desta lista -->
```

---

## Changelog

### Formato

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Adicionado
- Nova funcionalidade A
- Nova funcionalidade B

### Corrigido
- Bug X corrigido
- Bug Y corrigido

### Alterado
- Mudança na API
- Dependência atualizada

### Removido
- Funcionalidade obsoleta
```

### Versionamento

Seguimos [SemVer](https://semver.org/):
- **MAJOR (X):** mudança incompatível na API
- **MINOR (Y):** nova funcionalidade compatível
- **PATCH (Z):** correção de bug compatível

---

## Script de Automação

O projeto inclui um script `scripts/update_docs.py` que auxilia na manutenção:

```bash
# Verificar documentação faltante
python scripts/update_docs.py check

# Inicializar ERRORS.md se não existir
python scripts/update_docs.py init-errors

# Adicionar entrada no changelog (interativo)
python scripts/update_docs.py changelog

# Gerar relatório de saúde da documentação
python scripts/update_docs.py health
```

Execute `python scripts/update_docs.py --help` para ver todas as opções.
