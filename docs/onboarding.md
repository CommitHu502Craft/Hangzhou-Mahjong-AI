# Onboarding

This document is the shortest path from clone to a working local setup.

## Goal

By the end of this guide, you should be able to:

- install dependencies
- run the Python test suite
- build the frontend
- know where to look when setup fails

## Canonical Setup Path

### 1) Clone the repository

```powershell
git clone https://github.com/CommitHu502Craft/Hangzhou-Mahjong-AI.git
cd Hangzhou-Mahjong-AI
```

### 2) Set up Python dependencies

```powershell
uv venv .venv --python 3.11 --managed-python
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

Linux/macOS equivalent:

```bash
uv venv .venv --python 3.11 --managed-python
uv pip install --python .venv/bin/python -r requirements.txt
```

### 3) Run the Python test suite

```powershell
uv run pytest tests -q
```

Expected result:

- the command finishes without `FAILED` or `ERROR`
- the output ends with passed test counts

### 4) Set up and build the frontend

```powershell
cd frontend
npm install
npm run build
cd ..
```

### 5) Optional local API run

```powershell
uv run uvicorn api.server:app --host 127.0.0.1 --port 8000
```

## Recommended First Reads

- `README.md`
- `CONTRIBUTING.md`
- `docs/architecture.md`
- `docs/runbook.md`

## Troubleshooting

### Python 3.11 is missing

Symptoms:

- `uv venv` fails
- Python version mismatch errors appear during install

Fix:

- install Python 3.11
- rerun `uv venv .venv --python 3.11 --managed-python`

### `pytest` or project dependencies cannot import

Symptoms:

- `ModuleNotFoundError`
- import failures during test startup

Fix:

- recreate the virtual environment
- reinstall dependencies from `requirements.txt`

Commands:

```powershell
Remove-Item -Recurse -Force .venv
uv venv .venv --python 3.11 --managed-python
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

### Frontend install or build fails

Symptoms:

- `npm install` fails
- `npm run build` exits with dependency or lockfile errors

Fix:

- use a current Node.js release
- retry with a clean install in `frontend/`

Commands:

```powershell
cd frontend
Remove-Item -Recurse -Force node_modules
npm install
npm run build
cd ..
```

## Done Criteria

You are ready to contribute if:

- Python dependencies install successfully
- `uv run pytest tests -q` passes
- `frontend` builds with `npm run build`

