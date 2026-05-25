# End-to-end demo runners

Two layers of e2e validation for the 6-step business scenario described in
`docs/02-business-scenario.md` and `docs/15-demo-script.md`.

## 1. `backend/tests/e2e/test_scenario_6_steps.py` — in-process (CI)

Runs against the FastAPI app with `TestClient` + fake Foundry connections.
No network, no real Azure dependency. Verifies:

- step 1: customer audio → `translate.text.delta` **and**
  `whisper.transcript.completed` arrive in parallel on `/ws/customer`.
- step 3: `escalate.request` → `escalate.acked` with `assist_ws_url`.
- step 4-5: `/ws/assist` streams `rt2.reasoning.delta`, three
  `rt2.tool_call` (`get_order`, `check_tariff`, `check_insurance`),
  matching `rt2.tool_result`, final `rt2.text.delta`, then `rt2.done`.
- step 6: audit sink captures all envelopes for the call.
- stability: three back-to-back runs do not bleed state.

Latency budget asserted: first `translate.text.delta` arrives within
200 ms of the first `audio.frame` (in-process; production target is
1.5 s with the real `gpt-realtime-mini` deployment over the network).

Run locally:

```bash
cd backend
pytest tests/e2e/test_scenario_6_steps.py -v
```

## 2. `backend/e2e/run_scenario.py` — wire-level (pre-demo smoke check)

Drives the three websocket endpoints against a **live** backend — either a
local `uvicorn` or a deployed Azure App Service / Container Apps host.
Prints per-step pass/fail and round-trip latency so you can verify the
demo path is healthy 60 seconds before going on stage.

```bash
# local backend
python -m backend.e2e.run_scenario --base ws://localhost:8000 --runs 3

# Azure deployment
python -m backend.e2e.run_scenario \
    --base wss://contact-center-on-gpt-realtime.azurewebsites.net --runs 5
```

Exit code `0` if every step in every run sees the expected envelopes,
`1` otherwise. Wire this into the post-deploy job in
`.github/workflows/deploy.yml` (issue #21) as the smoke gate.
