"""FastAPI app entrypoint.

TODO (issue #06 ws-gateway):
- mount /ws/customer, /ws/agent, /ws/assist
- mount /health for Container Apps probes
"""
from fastapi import FastAPI

app = FastAPI(title="contact-center-on-gpt-realtime")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# TODO: app.include_router(... ws routers)
