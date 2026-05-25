# Backend (FastAPI WebSocket Gateway)

See `docs/04-tech-stack.md` for the full directory layout and `docs/11-api-contract.md` for the WS protocol.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env  # fill in AZURE_OPENAI_* values
uvicorn app.main:app --reload
```

## Tests

```bash
pytest -v
```

## Smoke tests (vs real Foundry)

```bash
python scripts/smoke-translate.py
python scripts/smoke-whisper.py
python scripts/smoke-rt2.py
```
