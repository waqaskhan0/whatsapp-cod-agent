# Roman Urdu Intent Classifier — COD Order Confirmation

Classifies how a Pakistani customer replied to a cash-on-delivery confirmation
message on WhatsApp, so only genuinely confirmed orders get booked with a courier.

## Why

25-40% of COD orders in Pakistan fail on delivery. Each failure costs the seller
shipping both ways (~Rs 200-400) plus handling. Sellers currently phone every
customer to confirm; it does not scale and most calls go unanswered.

This is the component that decides whether an order is dispatched. If it reads
`nahi bhai rehne dein` as a confirmation, the seller pays for a dead delivery —
so it is evaluated on that specific failure, not just on average accuracy.

## Labels

| Label | Meaning |
|---|---|
| `CONFIRM` | Dispatch as-is |
| `CANCEL` | Does not want it, or never ordered |
| `RESCHEDULE` | Wants it, but later |
| `ADDRESS_CHANGE` | Different or corrected address |
| `ORDER_CHANGE` | Different size, colour, design, quantity |
| `QUESTION` | Still asking, has not decided |
| `UNCLEAR` | Ambiguous — route to a human |

## The hard cases

Off-the-shelf sentiment and intent models fail on this because the input is
Roman Urdu, code-switched, and heavily context-dependent:

- `acha` is an acknowledgement, not agreement
- `ji` alone is ambiguous; `ji han` is not
- `abhi nahi` means later (RESCHEDULE), not never (CANCEL)
- `k` is ambiguous in Pakistani usage
- `maine order nahi kiya` is a fake order, which is a large share of COD failures

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env    # add a free Gemini key from aistudio.google.com/apikey
```

## Use

```bash
python classify.py "nahi bhai rehne dein"
python evaluate.py
```

`evaluate.py` reports per-class precision/recall/F1, how much traffic is
auto-handled at the confidence threshold, accuracy within that auto-handled
slice, and every false CONFIRM. Errors are dumped to `errors.json`.

## Results

`openai/gpt-oss-120b` via Groq, 93 seed examples, zero-shot with a task-specific prompt.

| Metric | Value |
|---|---|
| Overall accuracy | **97.8%** (91/93) |
| Auto-handled at conf >= 0.80 | 94.6% (88/93) |
| Accuracy when auto-handled | **98.9%** (87/88) |
| Escalated to human | 5 |
| False CONFIRMs (would dispatch a dead order) | **0** |

Per class: CANCEL, ADDRESS_CHANGE, ORDER_CHANGE and QUESTION at F1 1.00;
CONFIRM 0.98; RESCHEDULE 0.96; UNCLEAR 0.90.

### What the eval caught

The first run scored 91.4%, with CANCEL recall at 0.83. Every miss traced to one
ambiguity: **"ab"**. In `abhi nahi` it means "not now" (RESCHEDULE), but in
`mujhe nahi chahiye ab` and `ab nahi lena` it means "not anymore" (CANCEL). The
model read the second sense as the first, so real cancellations were being queued
for a retry. Adding an explicit rule for terminal-position `ab` fixed the class
outright, without regressing `abhi nahi`.

This is the kind of failure no general-purpose sentiment model catches, and it is
the reason the eval set exists.

### Cost asymmetry

Errors are not symmetric and the metrics reflect that. Misreading CANCEL as
RESCHEDULE costs one extra WhatsApp message. Misreading CANCEL as CONFIRM costs a
Rs 200-400 failed delivery. The prompt is biased toward escalating rather than
confirming, and false CONFIRMs are reported separately from accuracy.

## Running it

One command, from the project root:

```
.\start.ps1
```

That opens three windows (classifier, n8n, tunnel), waits for each to come up,
prints the dashboard and editor links, and tells you the public callback URL.

`.\stop.ps1` shuts everything down.

Secrets live in `.env.local` (gitignored) - copy `.env.local.example` and fill
in your Meta token. The token expires every 24 hours during testing, so that
file is usually the only thing you touch.

**The script warns you when the tunnel URL changes.** ngrok's free plan issues a
new hostname on every restart, and Meta keeps calling the old one until you
update it in the app dashboard, which looks exactly like the integration being
broken.


## Dashboard

```
uvicorn service:app --host 0.0.0.0 --port 8000
```

- `http://localhost:8000/` - seller dashboard
- `POST /classify` - the decision endpoint n8n calls
- `GET /stats` - the numbers behind the dashboard
- `POST /resolve/{id}` - mark an escalated reply as dealt with

Decisions are stored in SQLite (`cod.db`), so the numbers survive a restart.

The headline is money, not accuracy: **Rs saved = cancellations caught x
`RTO_COST_PKR`** (default 300, set it to the seller's real two-way courier
charge). It is labelled an estimate on the page, because it is one.

`store.AUTOMATED` lists the only three actions the workflow handles without a
person, and must stay identical to the n8n switch - the dashboard's
"needs a person" count is derived from it, so if the two drift the dashboard
starts lying.

## Deploying for a client

The local setup above is for building and demoing. A client's system runs on a
VPS instead - Docker, a real domain with automatic HTTPS, a non-expiring token,
and automatic restart on reboot. Nobody logs in to start it.

See `deploy/DEPLOY.md`. Infrastructure runs about $6/month.


## n8n

See `n8n/README.md`. Two workflows, import both.


## Data

`data/seed.csv` is a hand-written seed set used to get the harness running.
**It is not real data.** Replace it with logged customer replies as soon as you
have them — real messages have typos, voice-note transcripts, and phrasings no
one invents at a desk. Seed accuracy is a smoke test, not a result.

## Next

- Replace seed data with real logged replies
- Calibrate the confidence threshold against the real cost ratio (a human review
  costs minutes; a failed delivery costs Rs 200-400, so the threshold should be
  set high)
- Fine-tune a small open model once there are a few thousand labeled replies, to
  cut per-message cost and remove the API dependency
