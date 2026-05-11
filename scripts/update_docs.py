"""
Script de automacao para manutencao de documentacao, changelog e erros.

Uso:
  python scripts/update_docs.py check           # Verifica documentacao
  python scripts/update_docs.py init-errors     # Inicializa ERRORS.md
  python scripts/update_docs.py changelog       # Adiciona entry no changelog
  python scripts/update_docs.py health          # Relatorio de saude
  python scripts/update_docs.py bump            # Bump version + changelog
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DOCS = {
    "README.md": "Visao geral do projeto",
    "DOCUMENTATION.md": "Documentacao tecnica detalhada",
    "RUNBOOK.md": "Instrucoes de execucao",
    "MAINTENANCE.md": "Guia de manutencao",
    "CONTRIBUTING.md": "Guia de contribuicao",
    "CHANGELOG.md": "Historico de versoes",
    "ERRORS.md": "Historico de erros",
    "LICENSE": "Licenca do projeto",
    ".env.example": "Template de variaveis de ambiente",
}

ERRORS_TEMPLATE = """# Historico de Erros

Este arquivo registra bugs encontrados, suas causas raiz, solucoes e prevencoes.
Mantenha atualizado seguindo o guia em [MAINTENANCE.md](MAINTENANCE.md).

---

## Formato

Cada entrada deve seguir este modelo:

```markdown
## [YYYY-MM-DD] Titulo Resumido

### Descricao
Breve descricao do erro e seus sintomas.

### Causa Raiz
O que originou o problema.

### Solucao
Como foi corrigido (com links para commits/PRs quando possivel).

### Prevencao
Como evitar que o erro ocorra novamente.

### Arquivos Afetados
- `caminho/para/arquivo.py:linha`

### Testes
- `testes/relacionados.py`
```

<!--
  ================================================================
  NOVOS ERROS: adicione no TOPO desta secao (mais recente primeiro)
  ================================================================
-->
"""


def cmd_check():
    """Verifica se todos os documentos obrigatorios existem."""
    missing = []
    for doc, desc in REQUIRED_DOCS.items():
        path = ROOT / doc
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        status = "OK" if (exists and size > 0) else "AUSENTE" if not exists else "VAZIO"
        if status != "OK":
            missing.append(doc)
        print(f"  [{status:>7}] {doc:30s} {desc}")

    print()
    if missing:
        print(f"Faltam {len(missing)} documento(s):")
        for m in missing:
            print(f"  - {m}")
        return 1
    print("Todos os documentos estao presentes e nao vazios.")
    return 0


def cmd_init_errors():
    """Inicializa ERRORS.md se nao existir."""
    path = ROOT / "ERRORS.md"
    if path.exists():
        print("ERRORS.md ja existe.")
        return 1
    path.write_text(ERRORS_TEMPLATE, encoding="utf-8")
    print("ERRORS.md criado com template padrao.")
    return 0


def cmd_changelog():
    """Adiciona entrada interativa no changelog."""
    changelog_path = ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        print("CHANGELOG.md nao encontrado.")
        return 1

    print("=== Adicionar entrada no CHANGELOG.md ===")
    try:
        import inquirer
        questions = [
            inquirer.List("type",
                          message="Tipo de mudanca",
                          choices=["Adicionado", "Corrigido", "Alterado",
                                   "Removido", "Seguranca"]),
            inquirer.Text("message", message="Descricao"),
        ]
        answers = inquirer.prompt(questions)
        if not answers:
            return 1
        entry_type = answers["type"]
        message = answers["message"]
    except ImportError:
        inquirer_selection = input("Tipo (Adicionado/Corrigido/Alterado/Removido/Seguranca): ").strip()
        while inquirer_selection not in ("Adicionado", "Corrigido", "Alterado", "Removido", "Seguranca"):
            inquirer_selection = input("Tipo invalido. Escolha um valido: ").strip()
        entry_type = inquirer_selection
        message = input("Descricao: ").strip()
        if not message:
            print("Descricao vazia. Cancelando.")
            return 1

    today = date.today().isoformat()
    header = "## [Nao publicado] - {today}\n".format(today=today)
    entry = "### {type}\n- {message}\n".format(type=entry_type, message=message)

    content = changelog_path.read_text(encoding="utf-8")
    # Insert after the first heading (title line)
    lines = content.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("# ") and i == 0:
            continue
        if line.startswith("#"):
            insert_idx = i
            break

    lines.insert(insert_idx, "")
    lines.insert(insert_idx, header)
    lines.insert(insert_idx, entry)
    changelog_path.write_text("\n".join(lines), encoding="utf-8")

    print("Entrada adicionada em CHANGELOG.md:")
    print(f"  {header.strip()}")
    print(f"    {entry_type}: {message}")
    return 0


def cmd_health():
    """Relatorio de saude da documentacao."""
    print("=== Relatorio de Saude da Documentacao ===")
    print()

    total = len(REQUIRED_DOCS)
    ok_count = 0
    size_total = 0

    for doc, desc in REQUIRED_DOCS.items():
        path = ROOT / doc
        if path.exists():
            size = path.stat().st_size
            size_total += size
            ok_count += 1
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"  [OK] {doc:30s} {size_str:>10s}")
        else:
            print(f"  [--] {doc:30s} {'AUSENTE':>10s}")

    print()
    print(f"Resumo: {ok_count}/{total} documentos presentes ({size_total / 1024:.1f} KB total)")
    print()

    if ok_count < total:
        print("Documentos faltantes:")
        for doc in REQUIRED_DOCS:
            if not (ROOT / doc).exists():
                print(f"  - {doc}")
        return 1
    return 0


def cmd_bump():
    """Bump version e atualiza changelog."""
    version_file = ROOT / "pyproject.toml"
    if not version_file.exists():
        print("pyproject.toml nao encontrado.")
        return 1

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            print("tomllib/tomli necessario. Instale com: pip install tomli")
            return 1

    data = tomllib.loads(version_file.read_text(encoding="utf-8"))
    current_version = data.get("project", {}).get("version", "0.0.0")
    print(f"Versao atual: {current_version}")

    parts = [int(p) for p in current_version.split(".")]
    print("Qual parte incrementar?")
    print("  1) MAJOR (x.0.0) - mudanca incompativel")
    print("  2) MINOR (0.x.0) - nova funcionalidade")
    print("  3) PATCH (0.0.x) - correcao de bug")

    while True:
        choice = input("Escolha (1/2/3): ").strip()
        if choice == "1":
            parts[0] += 1
            parts[1] = 0
            parts[2] = 0
            break
        elif choice == "2":
            parts[1] += 1
            parts[2] = 0
            break
        elif choice == "3":
            parts[2] += 1
            break
        print("Escolha invalida.")

    new_version = ".".join(str(p) for p in parts)
    print(f"Nova versao: {new_version}")

    # Update pyproject.toml
    content = version_file.read_text(encoding="utf-8")
    content = content.replace(f'version = "{current_version}"',
                              f'version = "{new_version}"')
    version_file.write_text(content, encoding="utf-8")

    # Update changelog
    changelog_path = ROOT / "CHANGELOG.md"
    if changelog_path.exists():
        changelog = changelog_path.read_text(encoding="utf-8")
        today = date.today().isoformat()
        old_header = "## [Nao publicado]"
        new_header = f"## [{new_version}] - {today}"
        # Try to replace latest unreleased
        if old_header in changelog:
            changelog = changelog.replace(old_header, new_header, 1)
        else:
            new_entry = f"\n\n## [{new_version}] - {today}\n"
            changelog += new_entry
        changelog_path.write_text(changelog, encoding="utf-8")

    print(f"Versao bumpada para {new_version}.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Automacao de documentacao do projeto",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Verifica documentos obrigatorios")
    sub.add_parser("init-errors", help="Inicializa ERRORS.md")
    sub.add_parser("changelog", help="Adiciona entry interativa no CHANGELOG.md")
    sub.add_parser("health", help="Relatorio de saude da documentacao")
    sub.add_parser("bump", help="Bump version + changelog")

    args = parser.parse_args()

    commands = {
        "check": cmd_check,
        "init-errors": cmd_init_errors,
        "changelog": cmd_changelog,
        "health": cmd_health,
        "bump": cmd_bump,
    }

    sys.exit(commands[args.cmd]())


if __name__ == "__main__":
    main()
