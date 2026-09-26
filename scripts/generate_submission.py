#!/usr/bin/env python3
"""
Generates the canonical submission.jsonl artifact (30 lines, one per canonical test pair).
Reads expanded/test_pairs.json and invokes bot.compose().
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure repository root is on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from bot import compose

EXPANDED_DIR = ROOT_DIR / "expanded"
OUTPUT_FILE = ROOT_DIR / "submission.jsonl"


def load_all_contexts():
    categories = {}
    for p in (EXPANDED_DIR / "categories").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            categories[d["slug"]] = d

    merchants = {}
    for p in (EXPANDED_DIR / "merchants").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            merchants[d["merchant_id"]] = d

    customers = {}
    for p in (EXPANDED_DIR / "customers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            customers[d["customer_id"]] = d

    triggers = {}
    for p in (EXPANDED_DIR / "triggers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            triggers[d["id"]] = d

    with open(EXPANDED_DIR / "test_pairs.json", encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]

    return categories, merchants, customers, triggers, pairs


def generate_submission():
    categories, merchants, customers, triggers, pairs = load_all_contexts()

    print(f"Generating submission for {len(pairs)} test pairs...")
    lines = []

    for pair in pairs:
        test_id = pair["test_id"]
        trigger_id = pair["trigger_id"]
        merchant_id = pair["merchant_id"]
        customer_id = pair["customer_id"]

        trg = triggers[trigger_id]
        mer = merchants[merchant_id]
        cat = categories[mer["category_slug"]]
        cust = customers.get(customer_id) if customer_id else None

        result = compose(
            category=cat,
            merchant=mer,
            trigger=trg,
            customer=cust,
        )

        entry = {
            "test_id": test_id,
            "body": result["body"],
            "cta": result["cta"],
            "send_as": result["send_as"],
            "suppression_key": result["suppression_key"],
            "rationale": result["rationale"],
        }
        lines.append(json.dumps(entry, ensure_ascii=False))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    print(f"Successfully generated {OUTPUT_FILE} with {len(lines)} entries.")


if __name__ == "__main__":
    generate_submission()
