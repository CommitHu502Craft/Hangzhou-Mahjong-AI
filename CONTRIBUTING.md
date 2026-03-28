# Contributing

Thanks for contributing to Hangzhou Mahjong AI.

## Ground Rules

- Keep changes focused and small.
- Do not commit generated artifacts (`models/`, `reports/`, `logs/`, `datasets/artifacts/`).
- Do not commit secrets (`.env`, tokens, credentials).
- Use clear commit messages.

## Local Setup

```powershell
uv venv .venv --python 3.11 --managed-python
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

Frontend (optional):

```powershell
cd frontend
npm install
```

## Validation Before PR

Run tests:

```powershell
uv run pytest tests -q
```

If frontend changed:

```powershell
cd frontend
npm run build
```

## Branch and PR Flow

- Branch from `main`.
- Naming suggestion:
  - `feat/<short-topic>`
  - `fix/<short-topic>`
  - `docs/<short-topic>`
- Open a PR to `main` with:
  - problem statement
  - what changed
  - test evidence
  - risks / rollback notes

## Coding Notes

- Follow existing project style and structure.
- Prefer deterministic behavior for experiments (explicit seeds when relevant).
- Keep interfaces stable unless change is intentional and documented.
- Update docs when behavior, commands, or outputs change.

