"""Evaluate the classifier against the labeled set.

Usage: python evaluate.py [--data data/seed.csv] [--workers 4] [--limit N]
"""
import argparse
import csv
import json
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from classify import LABELS, classify

# Below this, the product routes the message to a human instead of acting.
AUTO_THRESHOLD = 0.80


def load(path, limit=None, shuffle=False):
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("text")]
    if shuffle:
        # The file is grouped by label, so any partial run must shuffle or it
        # only ever tests one class.
        random.seed(0)
        random.shuffle(rows)
    return rows[:limit] if limit else rows


def run(rows, workers):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        preds = list(pool.map(lambda r: classify(r["text"]), rows))
    return preds


def metrics(rows, preds):
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    confusion = defaultdict(lambda: defaultdict(int))

    for row, pred in zip(rows, preds):
        gold, got = row["label"], pred["intent"]
        confusion[gold][got] += 1
        if gold == got:
            tp[gold] += 1
        else:
            fn[gold] += 1
            fp[got] += 1
    return tp, fp, fn, confusion


def f1(p, r):
    return 2 * p * r / (p + r) if (p + r) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/seed.csv")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--shuffle", action="store_true")
    args = ap.parse_args()

    rows = load(args.data, args.limit, args.shuffle)
    print(f"Evaluating {len(rows)} examples...\n")
    preds = run(rows, args.workers)

    correct = sum(r["label"] == p["intent"] for r, p in zip(rows, preds))
    tp, fp, fn, confusion = metrics(rows, preds)

    print(f"Overall accuracy: {correct}/{len(rows)} = {correct / len(rows):.1%}\n")

    print(f"{'label':<16}{'prec':>7}{'rec':>7}{'f1':>7}{'n':>5}")
    for label in LABELS:
        support = tp[label] + fn[label]
        if not support:
            continue
        prec = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) else 0.0
        rec = tp[label] / support
        print(f"{label:<16}{prec:>7.2f}{rec:>7.2f}{f1(prec, rec):>7.2f}{support:>5}")

    # The metric the product actually lives on: of the messages we act on
    # automatically, how many do we get wrong?
    auto = [(r, p) for r, p in zip(rows, preds) if p["confidence"] >= AUTO_THRESHOLD]
    auto_correct = sum(r["label"] == p["intent"] for r, p in auto)
    print(f"\nAt confidence >= {AUTO_THRESHOLD}:")
    print(f"  auto-handled:  {len(auto)}/{len(rows)} = {len(auto) / len(rows):.1%}")
    if auto:
        print(f"  accuracy when auto-handled: {auto_correct}/{len(auto)} = {auto_correct / len(auto):.1%}")
    print(f"  escalated to human: {len(rows) - len(auto)}")

    # The expensive mistake: we dispatch an order the customer did not want.
    costly = [
        (r, p) for r, p in zip(rows, preds)
        if p["intent"] == "CONFIRM" and r["label"] in {"CANCEL", "RESCHEDULE", "ADDRESS_CHANGE"}
    ]
    print(f"\nFalse CONFIRMs (would dispatch a dead order): {len(costly)}")
    for r, p in costly:
        print(f"  {r['text']!r}  gold={r['label']}  conf={p['confidence']:.2f}")

    errors = [
        {"text": r["text"], "gold": r["label"], "pred": p["intent"],
         "confidence": p["confidence"], "reason": p.get("reason", "")}
        for r, p in zip(rows, preds) if r["label"] != p["intent"]
    ]
    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    print(f"\n{len(errors)} errors written to errors.json - read every one.")


if __name__ == "__main__":
    main()
