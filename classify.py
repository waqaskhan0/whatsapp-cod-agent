"""Roman Urdu intent classifier for COD order confirmation replies.

Works with either Gemini or Groq, depending on which key is in .env.
"""
import json
import logging
import os
import random
import re
import threading
import time

from dotenv import load_dotenv

load_dotenv()
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

LABELS = [
    "CONFIRM",
    "CANCEL",
    "RESCHEDULE",
    "ADDRESS_CHANGE",
    "ORDER_CHANGE",
    "QUESTION",
    "UNCLEAR",
]

SYSTEM = """You classify customer replies to a COD (cash on delivery) order \
confirmation message sent by a Pakistani online seller over WhatsApp.

Replies arrive in Roman Urdu, Urdu script, English, or a mix. They are short, \
informal, often misspelled, and may be a single word.

Labels:
- CONFIRM: customer wants the order dispatched as-is.
- CANCEL: customer does not want the order at all, or never placed it.
- RESCHEDULE: customer wants it, but later. Any deferral to a future time.
- ADDRESS_CHANGE: customer wants it delivered to a different or corrected address.
- ORDER_CHANGE: customer wants a different size, colour, design, or quantity.
- QUESTION: customer is asking something and has not decided yet.
- UNCLEAR: cannot be determined. Filler, greetings, acknowledgements, or ambiguous.

Rules that matter:
- "acha" / "achha" alone is an acknowledgement, NOT a confirmation. Use UNCLEAR.
- "ji" alone is ambiguous (UNCLEAR). "ji han" / "ji bilkul" is CONFIRM.
- "k" alone is ambiguous in Pakistani usage. Use UNCLEAR.
- "abhi nahi" means later, not never: RESCHEDULE, not CANCEL.
- CRITICAL: "ab" is ambiguous. In "abhi nahi" it means "not now" (RESCHEDULE). But in "mujhe nahi chahiye ab" / "ab nahi lena" / "ab nahi chahiye" it means "not anymore", and the customer is cancelling (CANCEL). Read "ab" at the END of a negative sentence as "anymore", not "now".
- A question about who is messaging ("kon", "aap kon ho") is QUESTION.
- "maine order nahi kiya" is a fake or mistaken order: CANCEL.
- If the customer wants it but changes something, prefer the change label \
(ADDRESS_CHANGE / ORDER_CHANGE / RESCHEDULE) over CONFIRM.
- If more than one applies, pick the one that must be acted on before dispatch.
- When genuinely torn, use UNCLEAR with low confidence. A human reviewing a \
message is cheap; dispatching a dead order is not.

confidence is your probability that the label is correct, 0.0 to 1.0. Be honest: \
low confidence routes the message to a human, which is the desired outcome for \
anything ambiguous.

Reply with JSON only: {"intent": "<label>", "confidence": <float>, "reason": "<short English note>"}"""


# --- rate limiting -----------------------------------------------------------
# Free tiers are strict (Gemini flash free tier is 5 req/min). Exceeding the
# limit raises 429, so we pace requests and back off when told to.

RPM = int(os.getenv("RPM", "0"))  # 0 = derive from provider below
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "6"))

_lock = threading.Lock()
_next_slot = 0.0


def _pace():
    """Block until this thread is allowed to make the next request."""
    global _next_slot
    if RPM <= 0:
        return
    interval = 60.0 / RPM
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next_slot - now)
        _next_slot = max(now, _next_slot) + interval
    if wait:
        time.sleep(wait)


def _retry_delay(err, attempt):
    """Honour the server's requested delay when it gives one."""
    m = re.search(r"retry in ([0-9.]+)s", str(err), re.I)
    if m:
        return float(m.group(1)) + 1.0
    return min(60.0, (2 ** attempt) + random.uniform(0, 1))


def _is_rate_limit(err):
    text = str(err)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _with_retry(fn, text):
    for attempt in range(MAX_RETRIES):
        _pace()
        try:
            return fn(text)
        except Exception as err:
            if not _is_rate_limit(err) or attempt == MAX_RETRIES - 1:
                raise
            delay = _retry_delay(err, attempt)
            print(f"  rate limited, waiting {delay:.0f}s...", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def _make_backend():
    """Pick a provider based on which key is present in .env."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    if groq_key and groq_key != "your_key_here":
        from groq import Groq

        client = Groq(api_key=groq_key)
        model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

        def call(text):
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Customer reply:\n{text}"},
                ],
            )
            return resp.choices[0].message.content

        globals()["RPM"] = RPM or 25
        return call, f"groq:{model}"

    if gemini_key and gemini_key != "your_key_here":
        from google import genai

        client = genai.Client(api_key=gemini_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        def call(text):
            resp = client.models.generate_content(
                model=model,
                contents=f"Customer reply:\n{text}",
                config={
                    "system_instruction": SYSTEM,
                    "temperature": 0,
                    "response_mime_type": "application/json",
                },
            )
            return resp.text

        globals()["RPM"] = RPM or 5
        return call, f"gemini:{model}"

    raise SystemExit(
        "No usable API key found in .env.\n"
        "Set GROQ_API_KEY (starts with 'gsk_', from console.groq.com/keys)\n"
        "or GEMINI_API_KEY (starts with 'AIza', from aistudio.google.com/apikey)."
    )


_call, BACKEND = _make_backend()


def classify(text: str) -> dict:
    """Classify one customer reply. Returns {intent, confidence, reason}."""
    try:
        raw = _with_retry(_call, text)
        out = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"intent": "UNCLEAR", "confidence": 0.0, "reason": "unparseable model output"}

    if out.get("intent") not in LABELS:
        return {"intent": "UNCLEAR", "confidence": 0.0, "reason": f"invalid label: {out.get('intent')}"}

    out["confidence"] = float(out.get("confidence", 0.0))
    return out


if __name__ == "__main__":
    import sys

    reply = " ".join(sys.argv[1:]) or "han bhai confirm hai"
    print(f"[{BACKEND}]")
    print(json.dumps(classify(reply), ensure_ascii=False, indent=2))
