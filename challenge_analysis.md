# Phase 0 — Challenge Analysis (from the actual ZIP)

Source files inspected (all under the extracted `magicpin-ai-challenge.zip`):

- `challenge-brief.md` (544 lines) — product/eval spec
- `challenge-testing-brief.md` (557 lines) — HTTP contract + harness lifecycle
- `engagement-design.md` (326 lines) — internal design rationale (background only)
- `engagement-research.md` (198 lines) — internal data-access research notes (background only)
- `judge_simulator.py` (962 lines) — the actual local test harness we will run against
- `dataset/generate_dataset.py` (312 lines) — deterministic seed→expanded dataset generator
- `dataset/{merchants_seed,customers_seed,triggers_seed}.json` — 10/15/25 seed records
- `dataset/categories/{dentists,salons,restaurants,gyms,pharmacies}.json` — 5 full CategoryContexts
- `examples/api-call-examples.md` (615 lines) — literal request/response wire examples
- `examples/case-studies.md` (338 lines) — 10 worked "what good looks like" examples with score breakdowns

No code has been written yet, per instructions.

---

## A. Exact required API

Confirmed in `challenge-testing-brief.md` §2 and cross-checked against `judge_simulator.py`'s `BotClient` and `examples/api-call-examples.md`.

### `GET /v1/healthz`
- No request body.
- Response `200`:
  ```json
  { "status": "ok", "uptime_seconds": 3600,
    "contexts_loaded": { "category": 5, "merchant": 50, "customer": 200, "trigger": 100 } }
  ```
- Judge polls every 60s during the test window. **3 consecutive non-200 failures → bot disqualified for that slot.**
- Must return all-zero counts before any context is pushed (verified fresh-start state).

### `GET /v1/metadata`
- No request body.
- Response `200`:
  ```json
  { "team_name": "...", "team_members": [...], "model": "...", "approach": "...",
    "contact_email": "...", "version": "...", "submitted_at": "..." }
  ```
- Purely informational; no scoring impact directly, but `approach` is read by a human/judge for qualitative context.

### `POST /v1/context`
- Request:
  ```json
  { "scope": "category" | "merchant" | "customer" | "trigger",
    "context_id": "<string>", "version": <int>,
    "payload": { ... }, "delivered_at": "<ISO8601>" }
  ```
- **Idempotent by `(scope, context_id, version)`** — actually keyed as `(scope, context_id)` with version comparison, per both the brief and the reference skeleton in §7 of the testing brief.
- Same version replayed → `409 { "accepted": false, "reason": "stale_version", "current_version": N }`.
- Higher version for existing `(scope, context_id)` → replaces atomically → `200 { "accepted": true, "ack_id": "...", "stored_at": "..." }`.
- Malformed → `400 { "accepted": false, "reason": "invalid_scope", "details": "..." }`.
- Payload size cap: **500 KB**.
- State must persist for the whole test; **no restarts**. In-memory store is acceptable.
- **Note (ambiguity):** the reference skeleton code compares `cur["version"] >= body.version` (strictly-not-lower rejected), which matches "idempotent on same version, replace on higher version" — confirmed consistent across brief, testing brief, and reference code.

### `POST /v1/tick`
- Request: `{ "now": "<ISO8601>", "available_triggers": ["<trigger context_id>", ...] }`.
- `available_triggers` is a **hint**, not a mandate — bot may act on any subset or ignore it entirely (it's free to consult context it already has, though in practice a trigger not yet pushed via `/v1/context` won't be resolvable).
- Response `200`:
  ```json
  { "actions": [ {
      "conversation_id": "...", "merchant_id": "...", "customer_id": null|"...",
      "send_as": "vera" | "merchant_on_behalf",
      "trigger_id": "...", "template_name": "...", "template_params": [...],
      "body": "...", "cta": "open_ended" | "binary_yes_no" | "binary_confirm_cancel" | "multi_choice_slot" | "none" | ...,
      "suppression_key": "...", "rationale": "..."
  } ] }
  ```
- `actions` **may be empty** — explicitly rewarded ("restraint is rewarded; spam is penalized").
- `conversation_id` must be **new** on `/v1/tick` (starting a fresh conversation); continuing an existing one happens only via `/v1/reply`.
- **Cap: 20 actions per tick.** Only one action per `(merchant_id, conversation_id)` pair per tick (FAQ §14).
- Must respond within the time budget or return `{"actions": []}` immediately and skip the cycle — **no background/late processing** (late responses are dropped).
- **Timeout discrepancy (flagged below):** testing-brief §5 rate-limit table says 30s; `examples/api-call-examples.md`'s summary table says 10s for `/v1/tick`. Design for the **tighter (10s) budget** to be safe, but confirm before finalizing if you can query the actual judge/organizers.

### `POST /v1/reply`
- Request:
  ```json
  { "conversation_id": "...", "merchant_id": "...", "customer_id": null|"...",
    "from_role": "merchant" | "customer" (implied), "message": "...",
    "received_at": "<ISO8601>", "turn_number": <int> }
  ```
- Response `200` — exactly one of three shapes:
  - `{ "action": "send", "body": "...", "cta": "...", "rationale": "..." }`
  - `{ "action": "wait", "wait_seconds": <int>, "rationale": "..." }`
  - `{ "action": "end", "rationale": "..." }`
- 30-second SLA per the testing brief's dedicated §2.3 statement ("the bot has 30 seconds"); the examples' summary table says 10s. **Same discrepancy as `/v1/tick` — treat 10s as the working target.**
- Timeout → judge marks turn `bot_silent` and moves on; **no retries**.

### Endpoint summary table

| Endpoint | Method | Judge retry? | Stated budget (testing-brief) | Stated budget (api-examples table) |
|---|---|---|---|---|
| `/v1/healthz` | GET | 3× before disqualify | not explicit (poll every 60s) | 2s |
| `/v1/metadata` | GET | no | not explicit | 2s |
| `/v1/context` | POST | no | not explicit | 5s |
| `/v1/tick` | POST | no | 30s (rate-limit table) | 10s |
| `/v1/reply` | POST | no | 30s (§2.3 explicit) | 10s |

**Build against the tighter numbers (2s/2s/5s/10s/10s).** This is the single most consequential ambiguity in the whole spec because it constrains whether a live LLM call is safe to put in the hot path.

---

## B. Core composer contract

Two related but distinct compose surfaces exist — don't conflate them:

1. **`challenge-brief.md`'s `bot.py` submission contract** (§5, §7.1):
   ```python
   def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None) -> dict:
       # returns: body, cta, send_as, suppression_key, rationale
   ```
   This is the conceptual "pure function" framing used for narrative/scoring explanation and for the offline `submission.jsonl` (30 lines, one per canonical test pair) deliverable described in §7.2.

2. **The actual live contract is `/v1/tick` and `/v1/reply`**, which wrap this same composition logic inside a stateful HTTP server (per `challenge-testing-brief.md`). This is what's actually scored in the live judge run. **The `bot.py`/`submission.jsonl` artifacts from the main brief appear to be a legacy/offline submission mode described in that doc; the testing brief (the more recent, "companion", operational doc) supersedes it with the HTTP harness.** Build the HTTP server as primary; keep `compose()` as an internal pure function that both `/v1/tick` and `/v1/reply` call into, so you can also emit `submission.jsonl` cheaply if required.

**Every composed message needs exactly these fields**, regardless of call path:
- `body` — WhatsApp text. No hard length cap, but keep concise.
- `cta` — one of a small controlled vocabulary observed in examples: `open_ended`, `binary_yes_no`, `binary_confirm_cancel`, `multi_choice_slot`, `none` (for pure-info triggers). Must be **exactly one** primary ask.
- `send_as` — `"vera"` (merchant-facing) or `"merchant_on_behalf"` (customer-facing, i.e. `customer` is populated).
- `suppression_key` — should equal (or derive deterministically from) the trigger's own `suppression_key` in most cases; must support the dedup semantics in §F below.
- `rationale` — free text explaining *why this message, why now* — **scored directly** ("did the rationale match the actual output?").
- (`/v1/tick` only) `conversation_id`, `merchant_id`, `customer_id`, `trigger_id`, `template_name`, `template_params`.

**Grounding constraint (critical, repeated everywhere):** never state a number, date, name, offer, or citation not present in the supplied context. Case Study 6's own annotation flags this explicitly ("assumes building data ... fabricates — judge will check"), and case-studies.md's closing rules make it a hard cap: any fabrication or repetition **caps that message at 5/10 per dimension regardless of otherwise-good quality**.

---

## C. Dataset

### Directory layout produced by `dataset/generate_dataset.py --out ./expanded`
```
expanded/
├── categories/{slug}.json         # 5 files, copied verbatim from dataset/categories/
├── merchants/m_NNN_*.json         # 50 files (10 seed + 40 generated, 10 per category)
├── customers/c_NNN_*.json         # 200 files (15 seed + 185 generated, ~4/merchant)
├── triggers/trg_NNN_*.json        # 100 files (25 seed + 75 generated)
└── test_pairs.json                # {"pairs": [ {test_id, trigger_id, merchant_id, customer_id}, ... ]} — 30 entries
```
Generation is **deterministic**: fixed `SEED = 20260426` passed to `random.Random(SEED)`, so every candidate gets an identical expanded dataset. **Do not hand-edit generated files** — regenerate from seeds if anything looks wrong.

### `CategoryContext` (scope=`category`) — fields actually present
`slug`, `display_name`, `voice` (`tone`, `register`, `code_mix`, `vocab_allowed[]`, `vocab_taboo[]`, `salutation_examples[]`, `tone_examples[]`), `offer_catalog[]` (`id, title, value, audience, type`), `peer_stats` (category-specific keys — see below, **not identical across categories**), `digest[]` (`id, kind, title, source, summary, actionable`, some with `trial_n`, `patient_segment`, `date`, `credits`), `patient_content_library[]` (`id, title, channel, length_seconds, body`), `seasonal_beats[]` (`month_range, note`), `trend_signals[]` (`query, delta_yoy, segment_age, skew`), plus category-only extras: `regulatory_authorities[]`, `professional_journals[]` (dentists only, per file inspected).

**`peer_stats` keys differ by category** (confirmed by direct inspection):
- dentists: `avg_rating, avg_review_count, avg_views_30d, avg_calls_30d, avg_directions_30d, avg_ctr, avg_photos, avg_post_freq_days, retention_6mo_pct`
- salons: same core + `retention_3mo_pct` (no 6mo)
- gyms: same core + `monthly_churn_pct, trial_to_paid_pct` (no retention_Nmo)
- restaurants: same core + `retention_30d_pct`
- pharmacies: same core + `delivery_share_pct, repeat_customer_pct`

→ **Do not assume a fixed peer_stats schema across categories.** Model it as a typed core + a category-specific extras dict, or a loose dict with category-aware accessors.

### `MerchantContext` (scope=`merchant`)
`merchant_id, category_slug, identity{name, city, locality, place_id, verified, languages[], owner_first_name, established_year}, subscription{status, plan, days_remaining|days_since_expiry, renewed_at?}, performance{window_days, views, calls, directions, ctr, leads, delta_7d{views_pct, calls_pct, ctr_pct?}}, offers[]{id, title, status, started?, ended?}, conversation_history[]{ts, from, body, engagement}, customer_aggregate{...loose, category/merchant-varying keys}, signals[] (free-form strings, often "key:value" shaped e.g. `"stale_posts:22d"`), review_themes[]{theme, sentiment, occurrences_30d, common_quote?}`.

`subscription.status` observed values: `active`, `expired`, `trial`. `customer_aggregate` keys vary per merchant (e.g. `high_risk_adult_count` only on the dentist; `delivery_orders_30d`/`dine_in_orders_30d` only on restaurants) — **model as a loose dict, not a rigid schema.**

### `CustomerContext` (scope=`customer`)
`customer_id, merchant_id, identity{name, phone_redacted, language_pref, age_band, senior_citizen?}, relationship{first_visit, last_visit, visits_total, services_received[], lifetime_value, favourite_dish?, chronic_conditions?}, state ∈ {new, active, lapsed_soft, lapsed_hard, churned}, preferences{...loose, channel/preferred_slots/reminder_opt_in + merchant-specific extras}, consent{opted_in_at, scope[]}`.

Edge case present in seed data: `c_015_anonymous_for_m010` has `phone_redacted: null`, `identity.name: "(walk-in, no profile)"`, `consent.opted_in_at: null`, `consent.scope: []` — **the engine must handle customers with effectively no usable identity/consent gracefully** (almost certainly → suppress any customer-facing send; there is no valid consent to message them on).

### `TriggerContext` (scope=`trigger`)
`id, scope ∈ {merchant, customer}, kind, source ∈ {external, internal}, merchant_id, customer_id (null unless scope=customer), payload{...kind-specific, loose dict}, urgency ∈ [1,5], suppression_key, expires_at`.

**Generated (non-seed) triggers have placeholder payloads**: `generate_dataset.py`'s `expand_triggers()` writes `"payload": {"placeholder": True, "metric_or_topic": kind}` for all 75 generated triggers — i.e. **75 of the 100 triggers in the expanded set carry no real content**, only the 25 seed triggers have fully fleshed-out payloads. This has a direct consequence for Phase 6/15: **the composer must degrade gracefully (or legitimately return "no action") when `trigger.payload` is just a placeholder**, since roughly 3/4 of the trigger pool by volume is like this. This also strongly suggests the 30 canonical `test_pairs.json` — built by `write_test_pairs()`, which walks triggers sorted by `kind` and takes up to 2 per kind — will include a substantial share of placeholder-payload triggers, not just the 25 rich seed ones. Confirm this once the dataset is actually generated (Phase 1) rather than assuming.

---

## D. Trigger taxonomy

Consolidated from `challenge-brief.md` §4.3, `triggers_seed.json`, and `generate_dataset.py`'s `additional_kinds` list. Kind → scope → source → typical urgency:

| kind | scope | source | urgency (seed data) | seen in seeds? |
|---|---|---|---|---|
| `research_digest` | merchant | external | 1–2 | yes |
| `regulation_change` | merchant | external | 4 | yes |
| `recall_due` | customer | internal | 3 | yes |
| `perf_dip` | merchant | internal | 3–4 | yes |
| `renewal_due` | merchant | internal | 4 | yes |
| `festival_upcoming` | merchant | external | 1 | yes |
| `wedding_package_followup` | customer | internal | 2 | yes (seed only, not in generator's list — check exact string match) |
| `curious_ask_due` | merchant | internal | 1 | yes |
| `winback_eligible` | merchant | internal | 2 | yes |
| `ipl_match_today` | merchant | external | 3 | yes |
| `review_theme_emerged` | merchant | internal | 3 | yes |
| `milestone_reached` | merchant | internal | 1 | yes |
| `active_planning_intent` | merchant | internal | 4 | yes |
| `seasonal_perf_dip` | merchant | internal | 1 | yes |
| `customer_lapsed_hard` | customer | internal | 3 | yes |
| `trial_followup` | customer | internal | 2 | yes |
| `supply_alert` | merchant | external | 5 | yes |
| `chronic_refill_due` | customer | internal | 2–3 | yes |
| `category_seasonal` | merchant | external | 2 | yes |
| `gbp_unverified` | merchant | internal | 3 | yes |
| `cde_opportunity` | merchant | external | 1 | yes |
| `competitor_opened` | merchant | external | 2 | yes |
| `perf_spike` | merchant | internal | 1 | yes |
| `dormant_with_vera` | merchant | internal | 2 | yes |
| `customer_lapsed_soft` | customer | internal | 3 | generator only |
| `appointment_tomorrow` | customer | internal | 2 | generator only |
| `unplanned_slot_open` | customer | internal | — | mentioned in engagement-design.md only, **not implemented in generator or seeds** — likely aspirational/future, do not build a strategy assuming it will appear in test data |

**Naming inconsistency to flag:** `challenge-brief.md` prose (§4.3) lists a trigger called `dormant_with_vera`, `customer_lapsed_soft`, `appointment_tomorrow` as canonical kinds; the generator's `additional_kinds` list matches most of these but the *seed* file uses a couple of near-synonyms (`winback_eligible` vs the brief's conceptual "winback", `customer_lapsed_hard` present in seeds but `customer_lapsed_soft` only in the generator, not in seeds). **Route trigger handling by semantic family (recall/reminder, performance movement, dormancy/lapse, research/compliance/trend, milestone, planning-intent, supply/compliance-alert, seasonal) rather than hard-matching exact kind strings**, exactly as the original phase plan already intends — this dataset reality reinforces that design choice rather than contradicts it.

---

## E. Reply taxonomy

From `challenge-testing-brief.md` §2.3, `examples/api-call-examples.md` §Phase 2/4, and `judge_simulator.py`'s test scenarios (`_auto_reply`, `_intent`, `_hostile`):

| Reply pattern | Expected bot `action` | Notes |
|---|---|---|
| Explicit acceptance ("Yes please...", "send me the abstract") | `send` | Advance to next concrete step; don't re-qualify |
| Explicit commitment / intent transition ("Ok let's do it", "what's next?") | `send` | **Must switch to action mode immediately** — judge's `_intent` check literally scans for qualifying-language words (`"would you", "do you", "can you tell", "what if", "how about"`) vs action-language words (`"done", "sending", "draft", "here", "confirm", "proceed", "next"`) and fails you if qualifying words appear without action words |
| Canned WhatsApp Business auto-reply (near-identical text 2–4× in a row) | 1st occurrence: `send` (one gentle re-prompt) or `wait`; repeated occurrence: `wait` then `end` | Judge's `_auto_reply` scenario sends the exact same string 4 times and checks for `action: end` (or at least `wait`) — **detect via literal repeated-text matching is sufficient and is what the harness itself checks for** |
| Explicit rejection / opt-out ("Not interested", "Stop messaging me") | `end` | Must not send again on that `conversation_id` |
| Hostile message | `end`, or `send` with an apology + no further push | Judge's `_hostile` check accepts either `action=="end"` OR (`action=="send"` AND apology words present: `"sorry", "apolog", "won't"`) |
| Off-topic / curveball question | `send` — politely decline out-of-scope ask, then redirect back to the live trigger thread | Don't end the conversation just because the topic drifted |
| Ambiguous / unclear | Not explicitly tested by the simulator; treat conservatively — likely `send` with a clarifying, still-on-topic nudge, or `wait` if truly unreadable |
| Delay/deferral ("later", "give me some time") | `wait` with a `wait_seconds` estimate | No literal example payload text given beyond the general shape; infer from `wait` semantics |

**Important scoring mechanic to design around:** the auto-reply and intent-transition checks in `judge_simulator.py` are **keyword/substring heuristics**, not LLM judgment, for the *local* self-test tool. The **actual competition judge** (per the briefs) uses an LLM sub-agent to *play* the merchant and presumably also to *score* conversation flow more holistically — so don't over-fit to the exact keyword lists in `judge_simulator.py`; treat them as a useful regression check, not the full spec of "correct" reply behavior.

---

## F. Suppression behavior

- Every `TriggerContext` carries its own `suppression_key` (e.g. `"research:dentists:2026-W17"`, `"recall:c_001_priya_for_m001:6mo"`, `"perf_dip:m_002_bharat_dentist_mumbai:calls:2026-W17"`). Keys are pre-namespaced by the dataset itself along lines of: **trigger-family : scope-identifier(s) : time-bucket**.
- The bot's own composed `suppression_key` in `/v1/tick` responses should, in the common case, **just echo the trigger's own `suppression_key`** (both `examples/api-call-examples.md` Example 2.2 and Example 2.9 do exactly this) — don't invent a different key unless you have a specific reason (e.g. collapsing multiple triggers into one send).
- Explicit failure modes the harness checks (`challenge-testing-brief.md` §10, `api-call-examples.md` Failure-mode section):
  - Sending the **exact same `body`** twice in the same `conversation_id` → `-2` anti-repetition penalty per repeat.
  - No explicit test of cross-tick suppression-key reuse blocking a second send is shown in the examples, but the framework strongly implies: **once a `suppression_key` has been used for a successful send, do not send again for that same key** until/unless the underlying trigger legitimately changes (new version, new time bucket, etc.) — this needs to be enforced by the bot itself since nothing in the HTTP contract stops the judge from re-offering the same `available_triggers` hint on a later tick.
- Suppression must be scoped correctly: a key like `research:dentists:2026-W17` is **category+time-bucket** scoped (shared across all dentist merchants that week for that same digest item) whereas `recall:c_001_priya_for_m001:6mo` is **customer**-scoped. Don't build a single suppression dimension set — derive/echo the key's actual semantics per trigger rather than assuming one fixed dimension tuple (merchant+customer+trigger+time) applies uniformly.

---

## G. Determinism requirements

- `bot.py`'s `compose()` "must be deterministic given the same inputs (set temperature=0 if using LLMs)" — from `challenge-brief.md` §7.1. This applies to the underlying composer logic used inside the live HTTP bot too.
- Dataset generation itself is deterministic (`SEED = 20260426`), so **everyone gets byte-identical expanded data** — good for local regression testing against fixed expected outputs.
- Determinism has two layers to design for:
  1. **Decision determinism** — given the same context state, the same trigger set, and the same `now`, `/v1/tick` should return the same actions. This should be enforced by pure, deterministic Python logic (signal scoring, decision engine), not dependent on LLM sampling.
  2. **Wording determinism** — if an LLM composes the final message text, temperature=0 (or a cached/fixed response) is the way to keep wording stable across repeated runs of the same inputs. Since live LLM calls are non-deterministic in practice even at temperature 0 (model updates, minor variance), **a deterministic fallback template path is required regardless**, both for reliability and for reproducible local testing.

---

## H. Judge behavior — how `/context`, `/tick`, `/reply` interact

Full lifecycle, from `challenge-testing-brief.md` §4 (cross-checked against `judge_simulator.py`'s `_warmup`/`_full`/`_phase2_short` methods, which implement a simplified local version of the same shape):

1. **Warmup (T-15 min):** judge calls `/healthz` + `/metadata`, then pushes the **entire base dataset** via `/v1/context` — 5 categories, 50 merchants, 200 customers, **0 triggers** (triggers arrive only during the test window). Waits 60s, re-checks `/healthz`; `contexts_loaded` must reflect all 255 base contexts or warmup fails.
2. **Test window (T0 → T0+60 simulated minutes, ~30–45 real minutes), 5-minute simulated ticks:** each tick: judge pushes any new/updated context for that tick → calls `/v1/tick` with `now` + `available_triggers` → for each returned action, judge logs it, has a sub-LLM play the merchant/customer and reply, POSTs that reply to `/v1/reply`, bot answers `send`/`wait`/`end`, repeats up to 5 turns or until the bot ends.
3. **Adaptive context injection (interleaved in phase 2):** new digest items (5/category), updated performance on 10 merchants, 15 new triggers, and for 5 specific merchants a brand-new `CustomerContext` pushed mid-test followed 2 minutes later by a `recall_due` trigger. **The bot must incorporate new context in later sends and must not hallucinate content it wasn't pushed.**
4. **Replay test (top 10 bots only):** 3 standalone deep-dive scenarios — auto-reply hell (canned text ×4), intent transition (commit after 2 qualifying turns), hostile/off-topic. 5 turns each, scored on conversation flow only.
5. **Scoring (T0+90min):** Phase-2 5-dimension rubric scores + Phase-3 adaptation bonus (max +5/dimension) + Phase-4 replay scores (top 10 only, max +30) + operational penalties (timeouts, healthz failures, malformed responses; max −20).

Rate/volume limits: max 10 req/s from judge to bot; `/v1/context` payload cap 500KB; `/v1/tick` cap 20 actions; 3 consecutive healthz failures = disqualification for that slot.

---

## I. Canonical test cases

**Not literally embedded in the ZIP as static text** — `dataset/generate_dataset.py`'s `write_test_pairs()` function *generates* `expanded/test_pairs.json` deterministically from the (also-deterministic) 100 expanded triggers: it groups triggers by `kind`, sorted alphabetically by kind name, takes up to 2 triggers per kind, and stops at 30 pairs. Each pair is `{test_id: "T01".."T30", trigger_id, merchant_id, customer_id}`.

Consequences verified from generated `expanded/test_pairs.json` (Phase 1 inspection):
- **18 unique trigger kinds** are covered across the 30 pairs (each kind has 1 or 2 pairs, up to the 30 limit):
  - 2 pairs each: `active_planning_intent`, `appointment_tomorrow`, `chronic_refill_due`, `competitor_opened`, `curious_ask_due`, `customer_lapsed_soft`, `dormant_with_vera`, `festival_upcoming`, `milestone_reached`, `perf_dip`, `perf_spike`, `recall_due` (12 kinds × 2 = 24 pairs)
  - 1 pair each: `category_seasonal`, `cde_opportunity`, `customer_lapsed_hard`, `gbp_unverified`, `ipl_match_today`, `regulation_change` (6 kinds × 1 = 6 pairs)
- **Payload distribution**: **17 of 30 pairs (56.7%)** point at real (seed) payloads, while **13 of 30 pairs (43.3%)** carry **placeholder payloads** (`{"placeholder": true, "metric_or_topic": "<kind>"}`). Over 43% of the canonical test suite has thin placeholder inputs, proving that graceful fallback to merchant signals, history, and category context is a primary requirement, not an edge case.
- **Category distribution**: Well balanced across all 5 verticals:
  - `dentists`: 7 pairs (23.3%)
  - `restaurants`: 7 pairs (23.3%)
  - `salons`: 6 pairs (20.0%)
  - `gyms`: 5 pairs (16.7%)
  - `pharmacies`: 5 pairs (16.7%)
- **Merchant distribution**: 19 unique merchants are represented:
  - 10 seed merchants (`m_001` through `m_010`) account for 21 pairs (e.g. `m_001` has 4, `m_006` has 4, `m_008` has 3, `m_003`/`m_009`/`m_010` have 2 each).
  - 9 generated merchants (`m_011`, `m_014`, `m_019`, `m_020`, `m_023`, `m_029`, `m_032`, `m_037`, `m_049`) account for the remaining 9 pairs.
- **Scope distribution**: 21 merchant-facing pairs (`scope: merchant`, `customer_id: None`), 9 customer-facing pairs (`scope: customer`, valid `customer_id`).
- The **10 worked examples in `examples/case-studies.md`** are the best available proxy for "what a top-scoring canonical case looks like" even though they aren't literally the 30 test pairs — they cover 2 examples each for dentists, salons, restaurants, gyms, pharmacies, mixing merchant-facing and customer-facing scopes, each with a full dimension-by-dimension score breakdown and named compulsion levers. Use these as gold-standard calibration targets in Phase 15/16, not as literal fixtures to hard-code against (per the anti-overfitting rule).
- One case study (`Case Study 3`) contains a **visible authoring error** in the source doc — it starts by describing a gym trigger, self-corrects mid-paragraph to a salon/bridal-followup trigger. This is a documentation artifact, not a schema signal; ignore the aborted gym framing and only use the corrected bridal-followup version.

---

## Additional category-specific rules worth carrying into Phase 7

Derived from direct inspection of all 5 `dataset/categories/*.json` files (not just the dentist example in the brief):

| Category | Tone/register | Distinctive vocab | Taboo highlights | Offer style |
|---|---|---|---|---|
| Dentists | `peer_clinical`, respectful_collegial | fluoride varnish, caries, RCT, OPG, aligner | "guaranteed", "100% safe", "completely cure", "miracle" | service+price (`Dental Cleaning @ ₹299`), some free/consult offers |
| Salons | `warm_practical`, approachable_expert | balayage, keratin, olaplex, brand names (Wella, L'Oréal) | "guaranteed glow", "permanent results", "instant transformation" | service+price + membership tier |
| Restaurants | `warm_busy_practical`, fellow_operator | covers, AOV, RPC, table turnover, GRO | "best food in city", "guaranteed packed house" | mix of discount ("Flat 30% OFF... limit ₹500") **and** service+price — restaurants are the one category where a plain discount offer exists natively in the catalog, so "avoid generic discounts" is a *preference*, not a hard category rule, for this vertical specifically |
| Gyms | `energetic_disciplined`, coach_to_member | footfall, 1RM, EMOM, AMRAP, PT sessions | "guaranteed weight loss", "shred in 7 days" | trial/membership/PT-session pricing |
| Pharmacies | `trustworthy_precise`, neighbourhood_pharmacist | OTC, schedule H/X, molecule, MRP, batch | "miracle cure", "100% safe", "doctor recommended (without disclosure)" | delivery/health-card/senior-discount, chronic-refill subscription framing |

Each category file also carries its own `peer_stats` key set (see §C) and its own `seasonal_beats`/`trend_signals` — category strategy modules should read these dynamically rather than assuming a fixed shape.

---

## Ambiguities / inconsistencies found (flagging per instructions)

1. **Latency budget conflict** — `/v1/tick` and `/v1/reply` are given a 30s SLA in `challenge-testing-brief.md` (§2.3 explicit statement, §5 rate-limit table) but a 10s budget in `examples/api-call-examples.md`'s summary table; `/healthz`/`/metadata`/`/context` similarly show 2s/2s/5s there with no explicit figure in the testing brief. **Resolution used for this build:** design to the tighter numbers from the examples doc, since violating those would also satisfy the looser testing-brief numbers, but not vice versa.
2. **URL policy conflict** — `challenge-brief.md` §5 constraint 4 says "URLs allowed when they add clear value to the merchant"; `examples/api-call-examples.md` Failure-mode Example F.4 says a URL in the body is a **hard fail (−3 penalty)**, framed as "Meta would reject" (WhatsApp template policy reasoning). **Resolution used for this build: treat URLs as disallowed in composed bodies**, since the penalty example is more specific/operational and the "Meta would reject" reasoning is a real constraint the brief's general statement doesn't override.
3. **Submission artifact vs. live HTTP bot** — `challenge-brief.md` §7 describes a `bot.py` + `submission.jsonl` + optional `conversation_handlers.py` file-based submission; `challenge-testing-brief.md` describes a fully different live HTTP-server submission (a public URL). These read as two different generations of the same challenge (the testing brief explicitly calls itself "companion" and focuses on "how it's tested"). **Resolution used for this build:** the HTTP server is the primary, scored deliverable (per the current phase plan already in progress); keep a pure `compose()`-shaped function inside the engine so a `submission.jsonl` can still be trivially produced if ever asked for.
4. **Trigger `kind` naming isn't 100% consistent** between the prose taxonomy in `challenge-brief.md` §4.3 and the concrete `kind` strings actually used in `triggers_seed.json`/`generate_dataset.py` (e.g., `winback_eligible` vs. conceptual "winback", `dormant_with_vera` appears in both but `customer_lapsed_soft`/`appointment_tomorrow` only exist in the generator's list, not the seed data; `unplanned_slot_open` is mentioned only in `engagement-design.md`'s aspirational roadmap section and never implemented anywhere in the actual dataset or generator). **Resolution:** route by semantic trigger family, not exact string match, so unseen or renamed kinds still get sensible handling.
5. **75 of 100 expanded triggers carry only placeholder payloads** (`{"placeholder": True, "metric_or_topic": kind}`) — this isn't flagged anywhere in the prose docs but is a direct fact from reading `generate_dataset.py`. It materially affects Phase 4 (signal selection — there may be nothing but the `kind` string to go on) and Phase 15 (a meaningful fraction of canonical cases may have thin inputs). The engine's "return no action" path and graceful-degradation behavior (Phase 18) needs to specifically handle "trigger kind is known, but payload is just a placeholder" as a first-class case, likely by falling back to whatever `merchant.signals[]` / `performance` / `conversation_history` data is genuinely available rather than inventing a specific reason tied to fictional payload fields.
6. **`case-studies.md` self-correction** — Case Study 3 visibly starts drafting a *gyms* trigger example, catches its own mistake mid-document, and redoes it as a *salons* bridal-followup case. Purely a doc artifact; already accounted for in §I above.
7. **Category-specific offer taxonomy isn't uniform** — restaurants' native `offer_catalog` includes a plain percentage discount (`"Flat 30% OFF on total bill (limit ₹500)"`), which cuts against the brief's general "specificity/service+price beats generic discount" guidance (§10, §11 anti-patterns). Treat that guidance as a strong per-message preference to reach for service+price offers *when available*, not as grounds to refuse to ever reference a discount-style offer that's genuinely in a restaurant's own active catalog.

---

## Recommended architecture (unchanged from the original phase plan, confirmed appropriate)

Nothing in the actual ZIP contradicts the `vera-engine/` structure proposed at the start of this project (FastAPI app; `engine/` for composer/decision/signal-selector/suppression/validator; `strategies/` split into trigger-family and category layers; `services/` for the context/conversation/state stores). Two refinements based on what was actually found:

- `services/context_store.py` needs to key on `(scope, context_id)` with a `version` field and support the exact idempotent/replace/stale-version response shapes documented in §A — this is now a concrete, testable contract rather than a general description.
- `engine/composer.py`'s internal pure function should match the `compose(category, merchant, trigger, customer=None) -> {body, cta, send_as, suppression_key, rationale}` shape from `challenge-brief.md` §5/§7.1 exactly, so it can serve both the `/v1/tick` path (wrapped with `conversation_id`/`trigger_id`/`template_name`/`template_params`) and, if ever needed, a standalone `submission.jsonl` generator.

---

## Next step

Reply `NEXT` to proceed to **Phase 1 — Generate and Validate the Dataset**: run `dataset/generate_dataset.py`, inspect the real `expanded/test_pairs.json` and confirm/replace the provisional statements in §I above, and build the Pydantic models in `src/models/` directly off the field inventories in §C (loose dicts where the data itself is loose, typed fields where it's consistent).
