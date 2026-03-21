#!/usr/bin/env python3
"""
FastAPI entrypoint for the Twilio SMS webhook.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from agent_service import DEFAULT_STORE_CODE, run_recipe_agent

app = FastAPI(title="Agent Joes SMS Webhook")


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


@app.get("/")
async def index() -> JSONResponse:
    return JSONResponse(
        {
            "service": "agent-joes",
            "webhook_path": "/api/twilio/sms",
            "default_store_code": os.getenv("DEFAULT_STORE_CODE", DEFAULT_STORE_CODE),
        }
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})


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
