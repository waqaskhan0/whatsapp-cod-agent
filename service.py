"""HTTP wrapper so n8n can call the classifier, plus the seller dashboard.

Run:  uvicorn service:app --host 0.0.0.0 --port 8000
"""
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import store
from classify import BACKEND, classify

# Below this confidence the workflow must not act automatically.
AUTO_THRESHOLD = float(os.getenv("AUTO_THRESHOLD", "0.80"))
# Shared secret so a stray request cannot drive your order pipeline.
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "")

HERE = Path(__file__).parent
app = FastAPI(title="Roman Urdu COD Intent")


class Reply(BaseModel):
    text: str
    order_id: str | None = None
    customer_phone: str | None = None
    # WhatsApp's wamid. Supplying it makes this endpoint idempotent.
    message_id: str | None = None


def _check(token: str):
    if SERVICE_TOKEN and token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="bad service token")


@app.get("/health")
def health():
    return {"ok": True, "backend": BACKEND, "auto_threshold": AUTO_THRESHOLD}


@app.post("/classify")
def classify_reply(reply: Reply, x_service_token: str = Header(default="")):
    _check(x_service_token)

    seen = store.find_by_message_id(reply.message_id)
    if seen:
        # A retry of a message already decided. Return the original decision
        # unchanged rather than classifying (and charging) again.
        return {
            "decision_id": seen["id"], "order_id": seen["order_id"],
            "customer_phone": seen["customer_phone"], "text": seen["text"],
            "intent": seen["intent"], "confidence": seen["confidence"],
            "reason": "duplicate delivery; returning original decision",
            "auto": seen["confidence"] >= AUTO_THRESHOLD,
            "action": seen["action"], "duplicate": True,
        }

    result = classify(reply.text)
    auto = result["confidence"] >= AUTO_THRESHOLD

    # The workflow branches on this, never on intent alone. Two things send a
    # message to a human: low confidence, and a confident UNCLEAR (the model is
    # sure the customer was ambiguous, which still needs a person).
    action = result["intent"] if (auto and result["intent"] != "UNCLEAR") else "ESCALATE"

    decision_id = store.record(
        reply.order_id, reply.customer_phone, reply.text,
        result["intent"], result["confidence"], action,
        message_id=reply.message_id,
    )

    return {
        "decision_id": decision_id,
        "order_id": reply.order_id,
        "customer_phone": reply.customer_phone,
        "text": reply.text,
        "intent": result["intent"],
        "confidence": result["confidence"],
        "reason": result.get("reason", ""),
        "auto": auto,
        "action": action,
        "duplicate": False,
    }


@app.post("/resolve/{decision_id}")
def resolve(decision_id: int, x_service_token: str = Header(default="")):
    _check(x_service_token)
    store.resolve(decision_id)
    return {"ok": True, "decision_id": decision_id}


@app.get("/stats")
def stats():
    return {
        **store.stats(),
        "inbox": store.inbox(),
        "recent": store.recent(25),
        "auto_threshold": AUTO_THRESHOLD,
    }


@app.get("/")
def dashboard():
    return FileResponse(HERE / "static" / "dashboard.html")
