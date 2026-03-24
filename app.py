#!/usr/bin/env python3
"""
FastAPI entrypoint for the Twilio SMS webhook.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from agent_service import DEFAULT_MODEL, DEFAULT_STORE_CODE, run_recipe_agent

app = FastAPI(title="Agent Joes SMS Webhook")
ROOT_DIR = Path(__file__).resolve().parent
WEB_DIST_CANDIDATES = [
    ROOT_DIR / "api" / "web_dist",
    ROOT_DIR / "web" / "dist",
]
WEB_DIST_DIR = next((path for path in WEB_DIST_CANDIDATES if path.exists()), WEB_DIST_CANDIDATES[0])
WEB_ASSETS_DIR = WEB_DIST_DIR / "assets"

if WEB_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_ASSETS_DIR), name="assets")


def _twiml_response(message_text: str) -> Response:
    twiml = MessagingResponse()
    twiml.message(message_text)
    return Response(content=str(twiml), media_type="application/xml")


def _signature_target_url(request: Request) -> str:
    override = os.getenv("TWILIO_WEBHOOK_URL")
    if override:
        return override
    return str(request.url)


def _validate_twilio_request(request: Request, params: dict[str, str], signature: str) -> None:
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured")

    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-Twilio-Signature header")

    validator = RequestValidator(auth_token)
    if not validator.validate(_signature_target_url(request), params, signature):
        raise HTTPException(status_code=403, detail="Twilio request signature validation failed")


def _frontend_available() -> bool:
    return WEB_DIST_DIR.exists() and (WEB_DIST_DIR / "index.html").exists()


def _frontend_file(path: str) -> Path | None:
    candidate = (WEB_DIST_DIR / path).resolve()
    try:
        candidate.relative_to(WEB_DIST_DIR.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def _index_payload() -> dict[str, str]:
    return {
        "service": "agent-joes",
        "webhook_path": "/api/twilio/sms",
        "default_store_code": os.getenv("DEFAULT_STORE_CODE", DEFAULT_STORE_CODE),
    }


@app.get("/")
async def index() -> Response:
    if _frontend_available():
        return FileResponse(WEB_DIST_DIR / "index.html")
    return JSONResponse(_index_payload())


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    store_code: str | None = None
    model: str | None = None


@app.post("/api/twilio/sms")
async def twilio_sms(request: Request) -> Response:
    form = await request.form()
    params = {key: value for key, value in form.items()}
    signature = request.headers.get("X-Twilio-Signature", "")

    _validate_twilio_request(request, params, signature)

    body = str(form.get("Body", "")).strip()
    if not body:
        return _twiml_response("Send a recipe question and I'll text back a Trader Joe's-grounded answer.")

    store_code = os.getenv("DEFAULT_STORE_CODE", DEFAULT_STORE_CODE)

    try:
        reply_text = run_recipe_agent(user_text=body, store_code=store_code)
    except Exception:
        reply_text = (
            "I hit a problem while building that Trader Joe's answer. "
            "Please try again in a moment."
        )

    return _twiml_response(reply_text)


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> JSONResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        reply_text = run_recipe_agent(
            user_text=message,
            store_code=(payload.store_code or os.getenv("DEFAULT_STORE_CODE", DEFAULT_STORE_CODE)).strip(),
            model=(payload.model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)).strip(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The agent failed to generate a reply.") from exc

    return JSONResponse({"reply": reply_text})


@app.get("/{path:path}", include_in_schema=False)
async def frontend_fallback(path: str) -> Response:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if _frontend_available():
        frontend_file = _frontend_file(path)
        if frontend_file is not None:
            return FileResponse(frontend_file)
        return FileResponse(WEB_DIST_DIR / "index.html")
    raise HTTPException(status_code=404, detail="Not found")
