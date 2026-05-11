# Contribuindo

Obrigado por considerar contribuir com o Karaokê IA!

## Como Contribuir

1. **Fork** o repositório
2. Crie um **branch** para sua feature (`git checkout -b feat/nova-funcionalidade`)
3. Faça **commit** das alterações (`git commit -m 'feat: adiciona nova funcionalidade'`)
4. Faça **push** para o branch (`git push origin feat/nova-funcionalidade`)
5. Abra um **Pull Request**

## Padrões de Código

- Siga o estilo existente do código
- Mantenha compatibilidade com Python 3.10+
- Escreva testes para novas funcionalidades
- Use type hints em funções públicas
- Documente funções com docstrings

## Estrutura de Commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — nova funcionalidade
- `fix:` — correção de bug
- `docs:` — documentação
- `refactor:` — refatoração
- `test:` — testes
- `chore:` — tarefas de manutenção

## Testes

```bash
pytest tests/ -v
```

Certifique-se de que todos os testes passam antes de abrir um PR.
