# Vera Message Engine — magicpin AI Challenge Submission

An intelligent, grounded, and compliant WhatsApp merchant and customer engagement engine rebuilt for **Vera** (magicpin local-commerce).

---

## 1. Architecture & Approach

The Vera Message Engine is designed for high-scoring, zero-hallucination, and fatigue-safe local commerce engagement. It supports both **Live HTTP Mode** (FastAPI server for the official competition harness) and **Pure Function Mode** (`from bot import compose` + `submission.jsonl`).

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Inbound / Context Ingress                       │
│              GET /healthz  │  POST /context  │  POST /tick             │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │     ContextStore (v1/v2)      │
                     │  Thread-safe, 500KB cap,      │
                     │  atomic version replacement   │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │   SuppressionEngine Gate      │
                     │  • Zero-tolerance Consent     │
                     │  • Suppression Key Dedup      │
                     │  • 1 Action / Merchant / Tick │
                     │  • 20 Action Global Cap       │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │ SignalSelector & Degradation  │
                     │  • Semantic Family Classifier │
                     │  • Grounded Fact Provenance   │
                     │  • Real Merchant Fallback     │
                     │    for Placeholder Triggers   │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │   Category Vertical Strategy  │
                     │  • Dentists, Salons, Gyms,    │
                     │    Restaurants, Pharmacies    │
                     │  • Taboo neutralizer (cure)   │
                     │  • Disallowed URL stripper    │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                        POST /v1/tick Wire Action
```

### Core Design Principles:
1. **Semantic Family Routing**: Rather than brittle exact-string matching against inconsistent trigger kinds (`winback_eligible` vs `winback`, `customer_lapsed_soft`), triggers map to 8 canonical families (`RECALL_REMINDER`, `PERFORMANCE_MOVEMENT`, `DORMANCY_LAPSE`, `RESEARCH_COMPLIANCE_TREND`, `MILESTONE`, `PLANNING_INTENT`, `SUPPLY_ALERT`, `SEASONAL_EVENT`).
2. **Zero-Fabrication Grounding**: Every number, citation, date, and offer is verified from ingested context. Facts are tagged with their provenance (`GroundedFact(field, value, source, citation)`).
3. **Graceful Fallback for Placeholder Payloads**: The 75 generated placeholder triggers fall back to genuine merchant data (performance deltas, active offers, review quotes) and category beats rather than inventing fictitious details.
4. **Immediate Action Mode on Commitment**: When a merchant indicates commitment (*"Ok lets do it. Whats next?"*), Vera immediately switches to action mode (`"done"`, `"sending"`, `"draft"`, `"confirm"`), strictly avoiding qualifying questions (`"would you"`, `"do you"`).
5. **Auto-Reply Absorption**: Automatically detects repeated WhatsApp Business canned greetings (*"Thank you for contacting us..."*) and ends/waits cleanly.

---

## 2. Tradeoffs Made

1. **Deterministic Core vs. Unconstrained LLM Sampling**: We built a deterministic priority ranking and vertical strategy engine in the hot path with an optional LLM tone-polish layer. This guarantees <15ms execution latency (well within the strict 10s budget), 100% determinism, and zero hallucination risk.
2. **Strict URL Disallowance**: While general brief prose mentioned URLs, the competition operational failure-mode spec specifies a hard −3 penalty for URLs. We enforce strict URL stripping to protect message scores.
3. **Restraint Filtering**: Low-urgency placeholder triggers lacking actionable merchant context are suppressed (`MIN_SCORE_THRESHOLD = 25.0`), prioritizing merchant goodwill and avoiding spam penalties.

---

## 3. What Additional Context Would Have Helped Most

1. **Clarification on Latency SLA**: Reconciling the 30-second budget in `challenge-testing-brief.md` §2.3 with the 10-second budget in `api-call-examples.md`.
2. **URL Policy Ambiguity**: Defining whether URLs are permissible for specific verified deep-links or universally prohibited due to Meta WhatsApp Business template policies.
3. **Dynamic Customer Ingress Schemas**: Clarifying whether mid-test customers will always contain explicit `phone_redacted` or if additional anonymous walk-in edge cases should be anticipated.

---

## 4. How to Run

### Live Server Mode
```bash
# Run the FastAPI server on port 8080
python bot.py
# or: uvicorn bot:app --host 0.0.0.0 --port 8080
```

### Run the Judge Simulator
```bash
JUDGE_LLM_API_KEY="your-key-here" \
JUDGE_LLM_PROVIDER="gemini" \
JUDGE_BOT_URL="https://magicpinaichallenge.vercel.app" \
python judge_simulator.py
```

Optional overrides: `JUDGE_LLM_MODEL`, `JUDGE_OLLAMA_URL`, and `JUDGE_TEST_SCENARIO`.
The simulator loads a project-root `.env` when present; `JUDGE_LLM_API_KEY` takes precedence, with `GEMINI_API_KEY` and `GOOGLE_API_KEY` accepted as fallbacks.

### Run Full Test Suite (65 Tests)
```bash
pytest -v
```

### Generate Offline Submission Artifact
```bash
python scripts/generate_submission.py
# Generates submission.jsonl (30 entries for expanded/test_pairs.json)
```
