# Dataset Schema Specification & Field Inventory

This document defines the real, inspected schema of the magicpin AI Challenge expanded dataset generated via `python dataset/generate_dataset.py --seed-dir ./dataset --out ./expanded` (deterministic fixed seed `SEED = 20260426`).

---

## 1. Dataset Generation Summary

| Entity / File Type | Location | Total Count | Seed Count | Generated Count | Notes |
|---|---|---|---|---|---|
| **Categories** | `expanded/categories/{slug}.json` | **5** | 5 | 0 | Copied verbatim from `dataset/categories/` |
| **Merchants** | `expanded/merchants/m_NNN_*.json` | **50** | 10 | 40 | 10 merchants per category |
| **Customers** | `expanded/customers/c_NNN_*.json` | **200** | 15 | 185 | ~4 customers per merchant |
| **Triggers** | `expanded/triggers/trg_NNN_*.json` | **100** | 25 | 75 | 25 rich seed payloads, 75 placeholder payloads |
| **Test Pairs** | `expanded/test_pairs.json` | **30** | — | 30 | Canonical test suite (18 trigger kinds, 19 merchants) |

---

## 2. CategoryContext (`expanded/categories/{slug}.json`)

All 5 category files share 11 root keys. However, internal fields (notably `peer_stats`, `digest`, `regulatory_authorities`, and `professional_journals`) vary significantly across categories.

### Root Fields

```json
{
  "slug": "dentists",
  "display_name": "Dentists & Dental Clinics",
  "voice": { ... },
  "offer_catalog": [ ... ],
  "peer_stats": { ... },
  "digest": [ ... ],
  "patient_content_library": [ ... ],
  "seasonal_beats": [ ... ],
  "trend_signals": [ ... ],
  "regulatory_authorities": [ ... ],
  "professional_journals": [ ... ]
}
```

### Detailed Field Breakdown

- **`slug`** (`str`): Unique category identifier: `"dentists"`, `"salons"`, `"restaurants"`, `"gyms"`, `"pharmacies"`.
- **`display_name`** (`str`): Human-readable name.
- **`voice`** (`object`):
  - `tone` (`str`): e.g. `"peer_clinical"`, `"warm_busy_practical"`.
  - `register` (`str`): e.g. `"respectful_collegial"`, `"fellow_operator"`.
  - `code_mix` (`str`): e.g. `"english_with_hindi_markers"`.
  - `vocab_allowed` (`list[str]`): Permitted category terminology (e.g. `["caries", "OPG"]`).
  - `vocab_taboo` (`list[str]`): Hard-forbidden terminology (e.g. `["guaranteed", "100% safe"]`).
  - `salutation_examples` (`list[str]`): e.g. `["Dr. {last_name}", "Doctor Sahib"]`.
  - `tone_examples` (`list[str]`): Worked reference sentences.
- **`offer_catalog`** (`list[object]`): 8 offers per category.
  - `id` (`str`): e.g. `"off_dent_01"`.
  - `title` (`str`): e.g. `"Dental Cleaning @ ₹299"`.
  - `type` (`str`): e.g. `"service_plus_price"`, `"consultation"`, `"discount"`.
  - `value` (`str`): e.g. `"₹299 (save ₹500)"`.
  - `audience` (`str`): e.g. `"all_lapsed_6mo"`, `"walk_in_first_time"`.
- **`peer_stats`** (`object` — **Varies by Category**):
  - **Shared Core (all 5 categories):**
    - `scope` (`str`): `"category"`
    - `avg_rating` (`float`): e.g. `4.4`
    - `avg_review_count` (`int` | `float`): e.g. `142`
    - `avg_views_30d` (`int` | `float`): e.g. `2450`
    - `avg_calls_30d` (`int` | `float`): e.g. `118`
    - `avg_directions_30d` (`int` | `float`): e.g. `86`
    - `avg_ctr` (`float`): e.g. `0.048`
    - `avg_photos` (`int` | `float`): e.g. `28`
    - `avg_post_freq_days` (`int` | `float`): e.g. `8`
  - **Category-Specific Metrics:**
    - `dentists`: `retention_6mo_pct` (`float`)
    - `salons`: `retention_3mo_pct` (`float`)
    - `restaurants`: `retention_30d_pct` (`float`)
    - `gyms`: `monthly_churn_pct` (`float`), `trial_to_paid_pct` (`float`)
    - `pharmacies`: `delivery_share_pct` (`float`), `repeat_customer_pct` (`float`)
- **`digest`** (`list[object]`): 5 research/clinical/business briefs per category.
  - Core fields: `id` (`str`), `kind` (`str`), `title` (`str`), `source` (`str`), `summary` (`str`), `actionable` (`str`).
  - Conditional fields:
    - `credits` (`int`): e.g. on CDE items (`dentists`).
    - `trial_n` (`int`): Clinical study sample size (`dentists`).
    - `patient_segment` (`str`): Target demographic (`dentists`).
    - `date` (`str`): e.g. `"2026-04-18"` (`dentists`, `salons`).
- **`patient_content_library`** (`list[object]`): 2-3 educational/marketing pieces.
  - `id` (`str`), `title` (`str`), `channel` (`str`), `length_seconds` (`int`), `body` (`str`).
- **`seasonal_beats`** (`list[object]`): 4-5 temporal patterns.
  - `month_range` (`str`): e.g. `"Apr-Jun"`.
  - `note` (`str`): Context and behavioral trends.
- **`trend_signals`** (`list[object]`): 4-5 search/market trends.
  - `query` (`str`): e.g. `"clear aligners delhi"`.
  - `delta_yoy` (`float`): e.g. `0.62` (+62% YoY).
  - `segment_age` (`str`): e.g. `"28-45"`, `"all"`.
  - `skew` (`str`): e.g. `"female"`, `"male"`, `"balanced"`.
- **`regulatory_authorities`** (`list[str]`): List of authority names (e.g. `["DCI", "State Dental Council"]`).
- **`professional_journals`** (`list[str]`): List of journal names (e.g. `["JIDA", "IJDR"]`).

---

## 3. MerchantContext (`expanded/merchants/m_NNN_*.json`)

All 50 merchant files share 10 root keys. Internal dictionaries (`customer_aggregate` and `subscription`) vary across categories and lifecycle states.

### Root Fields

```json
{
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "category_slug": "dentists",
  "identity": { ... },
  "subscription": { ... },
  "performance": { ... },
  "offers": [ ... ],
  "conversation_history": [ ... ],
  "customer_aggregate": { ... },
  "signals": [ ... ],
  "review_themes": [ ... ]
}
```

### Detailed Field Breakdown

- **`merchant_id`** (`str`): Unique merchant ID, formatted as `m_NNN_{name}_{category}_{city}`.
- **`category_slug`** (`str`): One of the 5 category slugs.
- **`identity`** (`object`):
  - `name` (`str`): Merchant trade name.
  - `city` (`str`): City name (e.g. `"Delhi"`, `"Mumbai"`, `"Bangalore"`).
  - `locality` (`str`): Neighborhood name (e.g. `"Lajpat Nagar"`, `"Bandra"`).
  - `place_id` (`str`): Google/GBP place ID.
  - `verified` (`bool`): True if GBP listing is verified.
  - `languages` (`list[str]`): Languages spoken/supported (e.g. `["en", "hi"]`).
  - `owner_first_name` (`str`): Salutation/operator name.
  - `established_year` (`int`): Year established (e.g. `2018`).
- **`subscription`** (`object` — **Varies by Lifecycle State**):
  - `status` (`str`): `"active"` | `"trial"` | `"expired"`.
  - `plan` (`str`): `"Trial"` | `"Basic"` | `"Pro"`.
  - `days_remaining` (`int | None`): Present/positive for `active` and `trial`; `None` for `expired`.
  - `days_since_expiry` (`int | None`): Present/positive for `expired`; `None` for `active`/`trial`.
  - `renewed_at` (`str | None`): ISO date or null.
- **`performance`** (`object`):
  - `window_days` (`int`): Reporting window (always `30`).
  - `views` (`int`): Profile/search impressions.
  - `calls` (`int`): Call button clicks.
  - `directions` (`int`): Direction requests.
  - `ctr` (`float`): Click-through rate.
  - `leads` (`int`): Total leads generated.
  - `delta_7d` (`object`):
    - `views_pct` (`float`): 7-day view change percentage.
    - `calls_pct` (`float`): 7-day call change percentage.
    - `ctr_pct` (`float | None`): 7-day CTR change percentage (optional).
- **`offers`** (`list[object]`): Current offers active on merchant profile.
  - `id` (`str`), `title` (`str`), `status` (`str`), `started` (`str | None`), `ended` (`str | None`).
- **`conversation_history`** (`list[object]`): Chronological prior messages with Vera.
  - `ts` (`str`): ISO timestamp.
  - `from` (`str`): `"merchant"` | `"vera"`.
  - `body` (`str`): Message text.
  - `engagement` (`str | None`): Interaction metadata (e.g. `"engaged"`, `"replied"`, `"ignored"`).
- **`customer_aggregate`** (`object` — **Varies by Category**):
  - **Shared Core:**
    - `total_unique_ytd` (`int`): Cumulative unique customers year-to-date.
  - **Category Variations:**
    - `dentists`: `retention_6mo_pct` (`float`), `high_risk_adult_count` (`int`), `lapsed_180d_plus` (`int`).
    - `salons`: `retention_3mo_pct` (`float`), `lapsed_90d_plus` (`int`).
    - `restaurants`: `dine_in_orders_30d` (`int`), `delivery_orders_30d` (`int`), `delivery_share_pct` (`float`), `repeat_customer_pct` (`float`).
    - `gyms`: `total_active_members` (`int`), `monthly_churn_pct` (`float`), `trial_to_paid_pct` (`float`).
    - `pharmacies`: `chronic_rx_count` (`int`), `repeat_customer_pct` (`float`).
- **`signals`** (`list[str]`): Operational indicators, typically formatted as `"key:value"` (e.g. `["stale_posts:22d"]`, `["bad_weather_weekend:rain"]`).
- **`review_themes`** (`list[object]`):
  - `theme` (`str`), `sentiment` (`str` e.g. `"positive"` | `"negative"`), `occurrences_30d` (`int`), `common_quote` (`str | None`).

---

## 4. CustomerContext (`expanded/customers/c_NNN_*.json`)

All 200 customer files share 7 root keys.

### Root Fields

```json
{
  "customer_id": "c_001_priya_for_m001",
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "identity": { ... },
  "relationship": { ... },
  "state": "lapsed_soft",
  "preferences": { ... },
  "consent": { ... }
}
```

### Detailed Field Breakdown

- **`customer_id`** (`str`): Unique customer identifier.
- **`merchant_id`** (`str`): ID of the merchant to whom this customer belongs.
- **`state`** (`str`): Lifecycle state: `"new"` | `"active"` | `"lapsed_soft"` | `"lapsed_hard"` | `"churned"`.
- **`identity`** (`object`):
  - `name` (`str`): Customer name (e.g. `"Priya Sharma"`, or `"(walk-in, no profile)"`).
  - `phone_redacted` (`str | None`): Redacted phone number (e.g. `"+91-98100-XXXXX"` or `null`).
  - `language_pref` (`str`): ISO language code (e.g. `"en"`, `"hi"`, `"kn"`, `"ta"`).
  - `age_band` (`str`): Demographic bracket (e.g. `"25-34"`, `"unknown"`).
  - `senior_citizen` (`bool | None`): Present for pharmacies/elderly customers; optional.
- **`relationship`** (`object`):
  - `first_visit` (`str`): ISO date string.
  - `last_visit` (`str`): ISO date string.
  - `visits_total` (`int`): Total visits count.
  - `services_received` (`list[str]`): Services/items purchased.
  - `lifetime_value` (`float | int`): Cumulative spend in ₹.
  - `favourite_dish` (`str | None`): Present on restaurant customers.
  - `chronic_conditions` (`list[str] | None`): Present on pharmacy customers (e.g. `["hypertension", "diabetes_type2"]`).
- **`preferences`** (`object` — **Loose/Extensible Schema**):
  - Common keys:
    - `channel` (`str`): e.g. `"whatsapp"`, `"none_recorded"`.
    - `reminder_opt_in` (`bool`): Whether customer opted in for automated reminders.
  - Category / Merchant Extras:
    - `preferred_slots` (`list[str]`): e.g. `["saturday_morning"]`.
    - `preferred_stylist` (`str`): e.g. `"Anita"`.
    - `delivery_address` (`str`): Saved delivery location.
    - `wedding_date` (`str`): ISO date for bridal clients.
    - `training_focus` (`str`): e.g. `"strength"`, `"weight_loss"`.
    - `health_focus` (`str`): e.g. `"cardiac"`.
    - `family_size` / `household_size` (`int`).
    - `office_nearby` (`bool`).
- **`consent`** (`object`):
  - `opted_in_at` (`str | None`): ISO timestamp when consent was granted, or `null`.
  - `scope` (`list[str]`): Explicitly granted permissions (e.g. `["appointment_reminders", "marketing"]`).

### Edge Case: Anonymous / Walk-in Customer (`c_015_anonymous_for_m010`)

The dataset contains walk-in customers with no profile or consent:
```json
{
  "customer_id": "c_015_anonymous_for_m010",
  "identity": {
    "name": "(walk-in, no profile)",
    "phone_redacted": null,
    "language_pref": "hi",
    "age_band": "unknown"
  },
  "preferences": {
    "channel": "none_recorded",
    "reminder_opt_in": false
  },
  "consent": {
    "opted_in_at": null,
    "scope": []
  }
}
```
**Engine Requirement:** The engine must handle this without crashing and must suppress customer-facing sends when `consent.opted_in_at` is null or `phone_redacted` is null.

---

## 5. TriggerContext (`expanded/triggers/trg_NNN_*.json`)

All 100 trigger files share 10 root keys.

### Root Fields

```json
{
  "id": "trg_001_digest_oral_systemic",
  "scope": "merchant",
  "kind": "research_digest",
  "source": "external",
  "merchant_id": "m_001_drmeera_dentist_delhi",
  "customer_id": null,
  "payload": { ... },
  "urgency": 2,
  "suppression_key": "research:dentists:2026-W17",
  "expires_at": "2026-05-02T23:59:59"
}
```

### Detailed Field Breakdown

- **`id`** (`str`): Trigger identifier (`trg_NNN_*`).
- **`scope`** (`str`): `"merchant"` (merchant-facing) or `"customer"` (customer-facing).
- **`kind`** (`str`): Trigger kind string (e.g. `"recall_due"`, `"perf_dip"`, `"festival_upcoming"`).
- **`source`** (`str`): `"internal"` (platform telemetry/database) or `"external"` (market, regulations, sports, calendar).
- **`merchant_id`** (`str`): Targeted merchant ID.
- **`customer_id`** (`str | None`): Targeted customer ID if `scope == "customer"`; `null` if `scope == "merchant"`.
- **`urgency`** (`int`): Priority integer between 1 (informational) and 5 (critical/regulatory).
- **`suppression_key`** (`str`): Namespaced deduplication key (e.g. `"recall:c_001_priya_for_m001:6mo"`).
- **`expires_at`** (`str`): ISO timestamp when the trigger is no longer actionable.
- **`payload`** (`object` — **Critical Bifurcation**):
  - **Seed Payloads (25 triggers):** Rich, structured context matching the specific `kind`.
  - **Placeholder Payloads (75 triggers):** Generated triggers carry only:
    ```json
    {
      "placeholder": true,
      "metric_or_topic": "<kind>"
    }
    ```
  **Engine Requirement:** When a trigger payload is a placeholder, composition logic must degrade gracefully by relying on available merchant signals, performance deltas, and category context, without inventing imaginary payload specifics.

---

## 6. Canonical Test Suite (`expanded/test_pairs.json`)

`test_pairs.json` contains 30 canonical pairs generated deterministically:

- **Total Test Cases**: 30 (`T01` to `T30`).
- **Unique Trigger Kinds Covered**: 18
  - 2 pairs: `active_planning_intent`, `appointment_tomorrow`, `chronic_refill_due`, `competitor_opened`, `curious_ask_due`, `customer_lapsed_soft`, `dormant_with_vera`, `festival_upcoming`, `milestone_reached`, `perf_dip`, `perf_spike`, `recall_due`.
  - 1 pair: `category_seasonal`, `cde_opportunity`, `customer_lapsed_hard`, `gbp_unverified`, `ipl_match_today`, `regulation_change`.
- **Payload Split**:
  - **17 real seed payloads (56.7%)**
  - **13 placeholder payloads (43.3%)**
- **Category Coverage**:
  - `dentists`: 7 (23.3%)
  - `restaurants`: 7 (23.3%)
  - `salons`: 6 (20.0%)
  - `gyms`: 5 (16.7%)
  - `pharmacies`: 5 (16.7%)
- **Scope Coverage**:
  - `merchant`: 21
  - `customer`: 9
- **Merchant Distribution**: 19 distinct merchants (10 seed merchants with 21 pairs; 9 generated merchants with 9 pairs).
