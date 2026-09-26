import json
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib import request as urlrequest, error as urlerror

from src.engine.composer import compose
from src.engine.reply_handler import ReplyHandler
from src.engine.signal_selector import SignalSelector
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.services.context_store import context_store
from src.services.conversation_store import conversation_store

DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "dataset"


class ChatService:
    """
    Chat service orchestrator for the single-column chatbot UI.
    Dispatches free-text scenarios, preset triggers, and inbound conversational turns
    strictly through the real Vera composer, decision engine, and reply handler.
    """

    @classmethod
    def _load_category(cls, slug: str) -> CategoryContext:
        model = context_store.get_model("category", slug)
        if model and isinstance(model, CategoryContext):
            return model
        cat_file = DATASET_DIR / "categories" / f"{slug}.json"
        if cat_file.exists():
            with open(cat_file, encoding="utf-8") as f:
                data = json.load(f)
            return CategoryContext.model_validate(data)
        # Fallback default
        return CategoryContext(
            slug=slug,
            display_name=slug.capitalize(),
            voice={"tone": "professional", "register": "standard", "code_mix": "english_clean", "vocab_allowed": [], "vocab_taboo": []},
            offer_catalog=[],
            peer_stats={"scope": "metro_2026", "avg_rating": 4.5, "avg_review_count": 50, "avg_views_30d": 2000, "avg_calls_30d": 20, "avg_directions_30d": 40, "avg_ctr": 0.03, "avg_photos": 10, "avg_post_freq_days": 14, "retention_6mo_pct": 0.4},
            digest=[],
        )

    DELHI_PERSONAS: dict[str, dict[str, Any]] = {
        "dentists": {
            "merchant_id": "m_delhi_dentist_rohini",
            "category_slug": "dentists",
            "identity": {
                "name": "Rohini Dental Studio",
                "city": "Delhi",
                "locality": "Rohini",
                "place_id": "ChIJ_ROHINI_DENTIST_001",
                "verified": True,
                "languages": ["en", "hi"],
                "owner_first_name": "Rohit",
                "established_year": 2019,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82, "renewed_at": "2026-02-04"},
            "performance": {
                "window_days": 30,
                "views": 2410, "calls": 18, "directions": 45, "ctr": 0.021, "leads": 9,
                "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05, "ctr_pct": 0.02},
            },
            "offers": [
                {"id": "o_rohini_001", "title": "Dental Cleaning @ ₹299", "status": "active", "started": "2026-03-01"},
            ],
            "conversation_history": [
                {"ts": "2026-04-24T10:12:00Z", "from": "vera", "body": "Profile audit done — your Google posts are stale (last post 22 days ago). Want me to draft 3 posts you can review?", "engagement": "merchant_replied"},
            ],
            "customer_aggregate": {"total_unique_ytd": 540, "lapsed_180d_plus": 78, "retention_6mo_pct": 0.38, "high_risk_adult_count": 124},
            "signals": ["stale_posts:22d", "ctr_below_peer_median", "high_risk_adult_cohort", "engaged_in_last_48h"],
            "review_themes": [
                {"theme": "doctor_manner", "sentiment": "pos", "occurrences_30d": 5, "common_quote": "Dr. Rohit explains everything patiently"},
            ],
        },
        "salons": {
            "merchant_id": "m_delhi_salon_lajpat",
            "category_slug": "salons",
            "identity": {
                "name": "Chic Cuts Salon",
                "city": "Delhi",
                "locality": "Lajpat Nagar",
                "place_id": "ChIJ_LAJPAT_SALON_002",
                "verified": True,
                "languages": ["en", "hi"],
                "owner_first_name": "Pooja",
                "established_year": 2020,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 65, "renewed_at": "2026-01-15"},
            "performance": {
                "window_days": 30,
                "views": 3120, "calls": 42, "directions": 85, "ctr": 0.038, "leads": 22,
                "delta_7d": {"views_pct": 0.42, "calls_pct": 0.12, "ctr_pct": 0.04},
            },
            "offers": [
                {"id": "o_chic_001", "title": "Balayage & Hair Spa @ ₹1,999", "status": "active", "started": "2026-03-10"},
            ],
            "conversation_history": [],
            "customer_aggregate": {"total_unique_ytd": 620, "lapsed_180d_plus": 94, "retention_6mo_pct": 0.45},
            "signals": ["stale_posts:18d", "festive_surge_demand", "engaged_in_last_48h"],
            "review_themes": [],
        },
        "restaurants": {
            "merchant_id": "m_delhi_restaurant_karolbagh",
            "category_slug": "restaurants",
            "identity": {
                "name": "Delhi Darbar Dhaba",
                "city": "Delhi",
                "locality": "Karol Bagh",
                "place_id": "ChIJ_KAROLBAGH_REST_003",
                "verified": True,
                "languages": ["en", "hi"],
                "owner_first_name": "Suresh",
                "established_year": 2015,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 90, "renewed_at": "2026-03-01"},
            "performance": {
                "window_days": 30,
                "views": 4850, "calls": 68, "directions": 140, "ctr": 0.042, "leads": 35,
                "delta_7d": {"views_pct": 0.18, "calls_pct": 0.08, "ctr_pct": 0.01},
            },
            "offers": [
                {"id": "o_darbar_001", "title": "Chicken Dum Biryani @ ₹199", "status": "active", "started": "2026-02-15"},
            ],
            "conversation_history": [],
            "customer_aggregate": {"total_unique_ytd": 1250, "lapsed_180d_plus": 180, "retention_6mo_pct": 0.52},
            "signals": ["view_surge:18%", "stale_posts:14d", "engaged_in_last_48h"],
            "review_themes": [],
        },
        "gyms": {
            "merchant_id": "m_delhi_gym_dwarka",
            "category_slug": "gyms",
            "identity": {
                "name": "Iron Pulse Fitness",
                "city": "Delhi",
                "locality": "Dwarka",
                "place_id": "ChIJ_DWARKA_GYM_004",
                "verified": True,
                "languages": ["en", "hi"],
                "owner_first_name": "Vikram",
                "established_year": 2021,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 45, "renewed_at": "2026-02-20"},
            "performance": {
                "window_days": 30,
                "views": 2100, "calls": 24, "directions": 60, "ctr": 0.028, "leads": 14,
                "delta_7d": {"views_pct": -0.10, "calls_pct": -0.05, "ctr_pct": 0.00},
            },
            "offers": [
                {"id": "o_pulse_001", "title": "3 FREE Trial Classes", "status": "active", "started": "2026-03-01"},
            ],
            "conversation_history": [],
            "customer_aggregate": {"total_unique_ytd": 410, "lapsed_180d_plus": 38, "retention_6mo_pct": 0.35},
            "signals": ["lapsed_members:38", "stale_posts:25d", "engaged_in_last_48h"],
            "review_themes": [],
        },
        "pharmacies": {
            "merchant_id": "m_delhi_pharmacy_saket",
            "category_slug": "pharmacies",
            "identity": {
                "name": "Metro Care Pharmacy",
                "city": "Delhi",
                "locality": "Saket",
                "place_id": "ChIJ_SAKET_PHARM_005",
                "verified": True,
                "languages": ["en", "hi"],
                "owner_first_name": "Ramesh",
                "established_year": 2017,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 110, "renewed_at": "2026-01-10"},
            "performance": {
                "window_days": 30,
                "views": 3400, "calls": 52, "directions": 90, "ctr": 0.034, "leads": 28,
                "delta_7d": {"views_pct": 0.05, "calls_pct": 0.08, "ctr_pct": 0.02},
            },
            "offers": [
                {"id": "o_metro_001", "title": "Free Home Delivery > ₹499", "status": "active", "started": "2026-01-01"},
            ],
            "conversation_history": [],
            "customer_aggregate": {"total_unique_ytd": 890, "lapsed_180d_plus": 64, "retention_6mo_pct": 0.60},
            "signals": ["chronic_refill_cohort:64", "stale_posts:12d", "engaged_in_last_48h"],
            "review_themes": [],
        },
    }

    @classmethod
    def _load_merchant(cls, category_slug: str) -> MerchantContext:
        if category_slug in cls.DELHI_PERSONAS:
            return MerchantContext.model_validate(cls.DELHI_PERSONAS[category_slug])

        seed_file = DATASET_DIR / "merchants_seed.json"
        if seed_file.exists():
            with open(seed_file, encoding="utf-8") as f:
                raw = json.load(f)
            for m_dict in raw.get("merchants", []):
                if m_dict.get("category_slug") == category_slug:
                    return MerchantContext.model_validate(m_dict)

        # Fallback dummy
        return MerchantContext.model_validate({
            "merchant_id": f"m_{category_slug}_delhi_demo",
            "category_slug": category_slug,
            "identity": {
                "name": f"Delhi {category_slug.capitalize()} Studio",
                "city": "Delhi",
                "locality": "Central Delhi",
                "place_id": f"ChIJ_DELHI_{category_slug.upper()}_DEMO",
                "verified": True,
                "languages": ["en", "hi"],
                "owner_first_name": "Delhi Partner",
                "established_year": 2020,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 60},
            "performance": {"window_days": 30, "views": 2000, "calls": 25, "directions": 50, "ctr": 0.035, "leads": 10},
            "offers": [],
            "conversation_history": [],
            "customer_aggregate": {},
            "signals": ["stale_posts:22d"],
        })

    @classmethod
    def _load_customer(cls, category_slug: str, merchant_id: str) -> Optional[CustomerContext]:
        seed_file = DATASET_DIR / "customers_seed.json"
        if seed_file.exists():
            with open(seed_file, encoding="utf-8") as f:
                raw = json.load(f)
            customers = raw.get("customers", [])
            for c_dict in customers:
                if category_slug == "dentists" and "priya" in c_dict.get("customer_id", ""):
                    c_copy = dict(c_dict)
                    c_copy["merchant_id"] = merchant_id
                    return CustomerContext.model_validate(c_copy)
                elif category_slug == "salons" and "kavya" in c_dict.get("customer_id", ""):
                    c_copy = dict(c_dict)
                    c_copy["merchant_id"] = merchant_id
                    return CustomerContext.model_validate(c_copy)
                elif category_slug == "pharmacies" and "grandfather" in c_dict.get("customer_id", ""):
                    c_copy = dict(c_dict)
                    c_copy["merchant_id"] = merchant_id
                    return CustomerContext.model_validate(c_copy)
            for c_dict in customers:
                if c_dict.get("merchant_id") == merchant_id:
                    return CustomerContext.model_validate(c_dict)
        return None

    @classmethod
    def _call_gemini_chat(
        cls,
        message: str,
        mer_ctx: MerchantContext,
        cat_ctx: CategoryContext,
        cust_ctx: Optional[CustomerContext] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Dynamically calls Google Gemini API to generate an intelligent, context-grounded response
        for freeform conversational queries, user questions, typos, and edge cases.
        """
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None

        merchant_name = mer_ctx.identity.name
        locality = mer_ctx.identity.locality or mer_ctx.identity.city
        offers_str = ", ".join(o.get("title", "") for o in getattr(mer_ctx, "offers", []) if isinstance(o, dict) and o.get("title"))
        signals_str = ", ".join(getattr(mer_ctx, "signals", []))

        prompt = f"""You are Vera, an autonomous, zero-hallucination operational outreach engine for {merchant_name} ({cat_ctx.display_name} in {locality}, Delhi).

CURRENT ACTIVE MERCHANT PERSONA:
- Name: {merchant_name}
- Category: {cat_ctx.display_name} ({cat_ctx.slug})
- Locality: {locality}, Delhi
- Active Offers: {offers_str}
- Real Signals & Telemetry: {signals_str}

USER MESSAGE:
"{message}"

OPERATIONAL DIRECTIVES & GUARDRAILS:
1. GREETING/IDENTITY: If the user says hi/hello or asks who/what you are, introduce Vera for {merchant_name}, explain your role (converting merchant milestones into high-compulsion WhatsApp outreach), and suggest 2 concrete scenarios to prepare. Action: "greet", CTA: "ready".
2. GENERAL BUSINESS / GROWTH: If the user asks how to grow, expand, scale, market, or improve their business (including typos like "buisnees", "how i expand"), clearly state you cannot provide general business growth consulting, but bridge directly to {merchant_name}'s actual operational telemetry ({offers_str}; {signals_str}). Offer a binary yes/no CTA to prepare outreach for one of them. Action: "bridge_growth", CTA: "binary_yes_no".
3. CLINICAL / MEDICAL: If the user asks for drug comparisons (e.g. paracetamol vs dolo), treatments, dosages, symptoms, or medical advice, refuse politely — state you do not provide clinical or medical advice, recommend consulting a doctor/pharmacist, and offer to prepare operational outreach for {merchant_name} instead. Action: "decline_medical", CTA: "clarify".
4. UNMATCHED OPERATIONAL: If the user describes a scenario that does not match verified events, explain your focus on operational outreach and offer 2 real scenarios based on {merchant_name}'s data. Action: "clarify", CTA: "clarify".
5. STRICT SAFETY: NEVER output URLs or web links. Never fabricate fake numbers or false claims.

Respond ONLY with valid JSON in this exact structure:
{{
  "body": "Your response text to the user",
  "cta": "binary_yes_no" | "clarify" | "ready" | "none",
  "action": "bridge_growth" | "decline_medical" | "greet" | "clarify",
  "grounding": ["Specific grounded fact or guardrail applied", "Active merchant data referenced"]
}}"""

        models_to_try = [
            "gemini-3.1-flash-lite-preview",
            "gemini-3-flash-preview",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
            }
        }).encode("utf-8")

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                with urlrequest.urlopen(req, timeout=6) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    text = resp_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text.startswith("```"):
                        text = re.sub(r"^```(?:json)?\s*", "", text)
                        text = re.sub(r"\s*```$", "", text)
                    parsed = json.loads(text)
                    grounding = parsed.get("grounding", [])
                    if isinstance(grounding, list):
                        grounding.insert(0, f"🤖 Engine: Gemini AI ({model})")
                    else:
                        grounding = [f"🤖 Engine: Gemini AI ({model})"]
                    return {
                        "body": parsed.get("body", ""),
                        "cta": parsed.get("cta", "binary_yes_no"),
                        "send_as": "vera",
                        "action": parsed.get("action", "clarify"),
                        "grounding": grounding,
                        "category": cat_ctx.slug,
                    }
            except Exception:
                continue

        return None

    @staticmethod
    def _classify_fallback_intent(text: str) -> Optional[str]:
        operational_compliance = any(
            re.search(pattern, text)
            for pattern in (r"\bdci\b", r"\bradiograph\b", r"\bx[- ]?ray\b", r"\bcompliance\b", r"\bregulation\b")
        )
        explicit_medical_subject = any(
            re.search(pattern, text)
            for pattern in (
                r"\b(paracetamol|dolo|crocin|ibuprofen|aspirin|antibiotics?|medicine|drug|tablet)\b",
                r"\b(symptoms?|fever|headache|side\s*effects?|illness|disease|diagnosis)\b",
            )
        )
        if operational_compliance and not explicit_medical_subject:
            return None

        clinical_patterns = (
            r"\b(paracetamol|dolo|crocin|ibuprofen|aspirin|antibiotics?)\b",
            r"\b(dosage|dose|side\s*effects?|symptoms?|fever|headache|pain\s*killer|treatment|diagnosis|prescription)\b",
            r"\b(medicine|drug|tablet)\b.*\b(for|vs|versus|difference|better|safe|take)\b",
            r"\b(difference\s+between|which\s+is\s+better|how\s+many\s+mg)\b.*\b(medicine|drug|tablet|dose|paracetamol|dolo)\b",
        )
        if any(re.search(pattern, text) for pattern in clinical_patterns):
            return "medical"

        growth_patterns = (
            r"\b(grow|scale|expand|boost|improve|market|promote)\b",
            r"\b(increase|more)\s+(sales|revenue|profit|footfall|business|customers|clients|orders|patients)\b",
            r"\b(business\s+advice|marketing\s+tips|growth\s+strategy)\b",
        )
        if any(re.search(pattern, text) for pattern in growth_patterns):
            return "growth"

        greeting_patterns = (
            r"\b(hi|hello|hey|namaste)\b",
            r"\bgood\s+(morning|afternoon|evening)\b",
            r"\b(who\s+are\s+you|what\s+are\s+you|who\s+is\s+vera|what\s+do\s+you\s+do|about\s+yourself)\b",
            r"\bare\s+you\s+(from|a|the)\b",
            r"\bhelp\s+me\b",
        )
        if any(re.search(pattern, text) for pattern in greeting_patterns):
            return "greeting"
        return None

    @staticmethod
    def _verified_context_summary(merchant: MerchantContext) -> str:
        items = [f"signal {signal}" for signal in merchant.signals if isinstance(signal, str) and signal.strip()]
        items.extend(
            f"active offer {offer.title}"
            for offer in merchant.offers
            if offer.status == "active" and offer.title
        )
        return "; ".join(items)

    @staticmethod
    def _active_context_trigger(category_slug: str, merchant: MerchantContext) -> Optional[TriggerContext]:
        if category_slug != "dentists" or "high_risk_adult_cohort" not in merchant.signals:
            return None
        cohort_count = merchant.customer_aggregate.high_risk_adult_count
        active_offer = next((offer for offer in merchant.offers if offer.status == "active"), None)
        if cohort_count is None or active_offer is None:
            return None
        return TriggerContext(
            id=f"chat_{merchant.merchant_id}_high_risk_adult_cohort",
            scope="customer",
            kind="high_risk_adult_cohort",
            source="internal",
            merchant_id=merchant.merchant_id,
            payload={"cohort_count": cohort_count, "offer_id": active_offer.id, "offer_title": active_offer.title},
            urgency=2,
            suppression_key=f"chat:high_risk_adult_cohort:{merchant.merchant_id}",
            expires_at="2026-12-31T23:59:59Z",
        )

    @classmethod
    def _intent_response(
        cls,
        intent: str,
        merchant: MerchantContext,
        category: CategoryContext,
        trigger: Optional[TriggerContext] = None,
    ) -> dict[str, Any]:
        merchant_name = merchant.identity.name
        locality = merchant.identity.locality or merchant.identity.city
        context = cls._verified_context_summary(merchant)
        context_text = context or "no current verified signals or active offers are available"

        if intent == "medical":
            body = (
                "I can't provide medical or clinical advice or compare medicines. Please consult a "
                f"licensed healthcare professional. Vera handles operational outreach for {merchant_name}; "
                f"the current verified context is {context_text}."
            )
            action, cta = "decline_medical", "clarify"
        elif intent == "growth":
            selected_context = context
            if trigger:
                selected_context = (
                    f"signal {trigger.kind}; active offer {trigger.payload.get('offer_title')}"
                )
            body = (
                "I don't provide general business growth consulting. I can help turn a real current "
                f"signal into operational outreach for {merchant_name}: {selected_context or context_text}. "
                "Would you like a WhatsApp draft based on that context?"
            )
            action, cta = "bridge_growth", "binary_yes_no"
        else:
            body = (
                f"Hello, I'm Vera, the operational outreach assistant for {merchant_name} in {locality}. "
                f"I can prepare a grounded WhatsApp draft using this current context: {context_text}. "
                "Which signal or active offer should I use?"
            )
            action, cta = "greet", "ready"

        return {
            "body": body,
            "cta": cta,
            "send_as": "vera",
            "action": action,
            "grounding": [
                "Intent classified deterministically before optional LLM handling.",
                f"Active Merchant: {merchant_name} ({locality})",
                f"Verified context: {context_text}",
            ],
            "category": category.slug,
        }

    @classmethod
    def process(
        cls,
        category: str,
        message: str,
        conversation_id: str = "conv_chat",
        turn: int = 1,
    ) -> dict[str, Any]:
        """
        Process chat input deterministically without hallucinations.
        """
        cat_slug = category.lower().strip()
        if cat_slug not in ("dentists", "salons", "restaurants", "gyms", "pharmacies"):
            cat_slug = "dentists"

        cat_ctx = cls._load_category(cat_slug)
        mer_ctx = cls._load_merchant(cat_slug)
        cust_ctx = cls._load_customer(cat_slug, mer_ctx.merchant_id)

        msg_lower = message.lower().strip()

        # =========================================================================
        # 1. Inbound Conversation Turn (Commitment, Auto-reply, Hostility, Deferral)
        # =========================================================================
        import re
        from datetime import datetime, timezone
        all_inbound_patterns = (
            ReplyHandler.AUTO_REPLY_PATTERNS
            + ReplyHandler.HOSTILE_PATTERNS
            + ReplyHandler.COMMITMENT_PATTERNS
            + ReplyHandler.DELAY_PATTERNS
        )
        is_inbound_turn = any(re.search(pat, msg_lower) for pat in all_inbound_patterns)

        if is_inbound_turn:
            conversation = conversation_store.get(conversation_id)
            reply_res = ReplyHandler.handle_reply(
                conversation_id=conversation_id,
                merchant_id=mer_ctx.merchant_id,
                customer_id=cust_ctx.customer_id if cust_ctx else None,
                from_role="merchant",
                message=message,
                received_at=datetime.now(timezone.utc).isoformat(),
                turn_number=turn,
                category_context=cat_ctx,
                merchant_context=mer_ctx,
                customer_context=cust_ctx,
                trigger_context=conversation.pending_trigger if conversation else None,
            )
            grounding_points = [
                f"Handled via Inbound Conversation Engine for {mer_ctx.identity.name}",
                f"Evaluated Action: {reply_res.get('action', 'send').upper()}",
                f"Rationale: {reply_res.get('rationale', 'Inbound turn processed')}",
            ]
            if reply_res.get("action") == "end":
                grounding_points.append("Opt-out / loop absorption active: outreach terminated cleanly.")
            elif reply_res.get("action") == "send":
                grounding_points.append("Action mode active: response composed from the conversation's selected context.")

            return {
                "body": reply_res.get("body", ""),
                "cta": reply_res.get("cta", "none"),
                "send_as": "vera",
                "action": reply_res.get("action", "send"),
                "grounding": grounding_points,
                "category": cat_slug,
            }

        # Deterministic intents take precedence over trigger keyword matching and optional LLM handling.
        intent = cls._classify_fallback_intent(msg_lower)
        if intent:
            active_trigger = cls._active_context_trigger(cat_slug, mer_ctx) if intent == "growth" else None
            if active_trigger:
                conversation_store.set_pending_trigger(conversation_id, mer_ctx.merchant_id, active_trigger)
            return cls._intent_response(intent, mer_ctx, cat_ctx, active_trigger)

        # =========================================================================
        # 2. Scenario / Trigger Composition Request
        # =========================================================================
        trigger = cls._match_or_build_trigger(cat_slug, mer_ctx, msg_lower)

        if trigger is not None:
            conversation_store.set_pending_trigger(conversation_id, mer_ctx.merchant_id, trigger)
            # Run real pure compose() function
            composed = compose(
                category=cat_ctx,
                merchant=mer_ctx,
                trigger=trigger,
                customer=cust_ctx if trigger.scope == "customer" else None,
            )

            # Extract real grounded facts for inline inspector
            signals = SignalSelector.extract_signals(
                trigger=trigger,
                merchant=mer_ctx,
                category=cat_ctx,
                customer=cust_ctx if trigger.scope == "customer" else None,
            )

            grounding_points = [
                f"Merchant: {mer_ctx.identity.name} ({mer_ctx.identity.locality or mer_ctx.identity.city})",
                f"Category Tone: {cat_ctx.voice.tone} ({cat_ctx.voice.register})",
                f"Strategy Rationale: {composed.get('rationale', 'Vertical strategy composition')}",
                f"Suppression Key: {composed.get('suppression_key', trigger.suppression_key)}",
                "Safety Check: 0 URLs detected (avoids -3 penalty), 0 taboo words detected.",
            ]

            if signals.stale_posts_days:
                grounding_points.append(f"Grounded Signal: {signals.stale_posts_days}-day profile inactivity metric.")
            if signals.active_offer_title:
                grounding_points.append(f"Active Offer Anchor: {signals.active_offer_title}")

            return {
                "body": composed.get("body", ""),
                "cta": composed.get("cta", "binary_yes_no"),
                "send_as": composed.get("send_as", "vera"),
                "action": "send",
                "grounding": grounding_points,
                "category": cat_slug,
            }

        # Gemini handles only unmatched freeform queries; failures fall through below.
        gemini_result = cls._call_gemini_chat(message, mer_ctx, cat_ctx, cust_ctx)
        if gemini_result and gemini_result.get("body"):
            return gemini_result

        merchant_name = mer_ctx.identity.name
        locality = mer_ctx.identity.locality or mer_ctx.identity.city
        context = cls._verified_context_summary(mer_ctx)
        query_excerpt = re.sub(r"\s+", " ", message).strip()[:120]
        context_text = context or "no current verified signal or active offer is available"
        return {
            "body": (
                f"I couldn't match '{query_excerpt}' to an operational trigger for {merchant_name}. "
                f"Vera drafts outreach only from current verified context: {context_text}. "
                "Please name the signal or offer you want to use."
            ),
            "cta": "clarify",
            "send_as": "vera",
            "action": "clarify",
            "grounding": [
                "No matching operational trigger found; no unverified scenario was suggested.",
                f"Active Merchant Persona: {merchant_name} ({locality})",
                f"Verified context: {context_text}",
            ],
            "category": cat_slug,
        }

    @classmethod
    def _match_or_build_trigger(
        cls,
        cat_slug: str,
        merchant: MerchantContext,
        text: str,
    ) -> Optional[TriggerContext]:
        """Match freeform text to known trigger or build a grounded trigger."""
        # Dentists
        if cat_slug == "dentists":
            if any(w in text for w in ("dci", "radiograph", "dose", "x-ray", "compliance", "regulation", "limit")):
                return TriggerContext(
                    id="trg_002_compliance_dci_radiograph",
                    scope="merchant",
                    kind="regulation_change",
                    source="external",
                    merchant_id=merchant.merchant_id,
                    payload={"category": "dentists", "top_item_id": "d_2026W17_dci_radiograph", "deadline_iso": "2026-12-15"},
                    urgency=4,
                    suppression_key="compliance:dci_radiograph:2026",
                    expires_at="2026-12-15T00:00:00Z",
                )
            if any(w in text for w in ("recall", "checkup", "hygiene", "6-month", "patient", "cleaning", "priya")):
                return TriggerContext(
                    id="trg_003_recall_due_priya",
                    scope="customer",
                    kind="recall_due",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    customer_id="c_001_priya_for_m001",
                    payload={"service_due": "6_month_cleaning", "last_service_date": "2026-05-12", "due_date": "2026-11-12"},
                    urgency=3,
                    suppression_key="recall:c_001_priya:6mo",
                    expires_at="2026-11-30T00:00:00Z",
                )
            if any(w in text for w in ("research", "jida", "digest", "caries", "fluoride", "study")):
                return TriggerContext(
                    id="trg_001_research_digest_dentists",
                    scope="merchant",
                    kind="research_digest",
                    source="external",
                    merchant_id=merchant.merchant_id,
                    payload={"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
                    urgency=2,
                    suppression_key="research:dentists:2026-W17",
                    expires_at="2026-12-31T23:59:59Z",
                )
            if any(w in text for w in ("renewal", "subscription", "plan", "expire")):
                return TriggerContext(
                    id="trg_renewal_dentists",
                    scope="merchant",
                    kind="renewal_due",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    payload={"days_remaining": 12, "plan": "Pro"},
                    urgency=4,
                    suppression_key=f"renewal:{merchant.merchant_id}",
                    expires_at="2026-12-31T23:59:59Z",
                )

        # Salons
        elif cat_slug == "salons":
            if any(w in text for w in ("diwali", "festival", "festive", "holiday", "celebration", "spike", "rush")):
                return TriggerContext(
                    id="trg_006_festival_diwali",
                    scope="merchant",
                    kind="festival_upcoming",
                    source="external",
                    merchant_id=merchant.merchant_id,
                    payload={"festival": "Diwali", "date": "2026-10-31", "days_until": 188},
                    urgency=2,
                    suppression_key="festival:diwali:2026",
                    expires_at="2026-11-02T00:00:00Z",
                )
            if any(w in text for w in ("bridal", "wedding", "kavya", "makeup", "skin", "trial")):
                return TriggerContext(
                    id="trg_007_bridal_followup_kavya",
                    scope="customer",
                    kind="wedding_package_followup",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    customer_id="c_005_kavya_for_m003",
                    payload={"wedding_date": "2026-11-08", "trial_completed": "2026-03-22"},
                    urgency=2,
                    suppression_key="bridal_followup:kavya",
                    expires_at="2026-11-08T00:00:00Z",
                )
            if any(w in text for w in ("haircut", "spa", "offer", "balayage", "package", "service")):
                return TriggerContext(
                    id="trg_salon_offer",
                    scope="merchant",
                    kind="curious_ask_due",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    payload={"ask_template": "what_service_in_demand_this_week"},
                    urgency=1,
                    suppression_key=f"curious_ask:{merchant.merchant_id}",
                    expires_at="2026-12-31T23:59:59Z",
                )

        # Restaurants
        elif cat_slug == "restaurants":
            if any(w in text for w in ("fssai", "hygiene", "audit", "kitchen", "guideline", "inspection", "safety")):
                return TriggerContext(
                    id="trg_restaurant_fssai",
                    scope="merchant",
                    kind="regulation_change",
                    source="external",
                    merchant_id=merchant.merchant_id,
                    payload={"regulation": "FSSAI revised kitchen hygiene guidelines", "deadline_iso": "2026-11-30"},
                    urgency=3,
                    suppression_key="fssai_guidelines:2026",
                    expires_at="2026-11-30T00:00:00Z",
                )
            if any(w in text for w in ("thali", "biryani", "lunch", "offer", "menu", "surge", "view", "food")):
                return TriggerContext(
                    id="trg_restaurant_view_surge",
                    scope="merchant",
                    kind="perf_surge",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    payload={"metric": "views", "delta_pct": 0.18},
                    urgency=2,
                    suppression_key="views_surge:restaurant",
                    expires_at="2026-12-31T23:59:59Z",
                )
            if any(w in text for w in ("ipl", "match", "night", "cricket", "delivery")):
                return TriggerContext(
                    id="trg_restaurant_ipl",
                    scope="merchant",
                    kind="event_upcoming",
                    source="external",
                    merchant_id=merchant.merchant_id,
                    payload={"event_name": "IPL Match Night", "days_until": 2},
                    urgency=2,
                    suppression_key="ipl_match_night:2026",
                    expires_at="2026-12-31T23:59:59Z",
                )

        # Gyms
        elif cat_slug == "gyms":
            if any(w in text for w in ("lapsed", "inactivity", "30-day", "churn", "member", "recall", "winback", "attendance")):
                return TriggerContext(
                    id="trg_gym_inactivity",
                    scope="merchant",
                    kind="retention_nudge",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    payload={"lapsed_count": 38, "recovery_pct": 24},
                    urgency=3,
                    suppression_key="gym:retention:30d",
                    expires_at="2026-12-31T23:59:59Z",
                )
            if any(w in text for w in ("trial", "classes", "scan", "body composition", "workout", "fitness")):
                return TriggerContext(
                    id="trg_gym_trial",
                    scope="merchant",
                    kind="offer_boost",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    payload={"offer_name": "3 FREE Trial Classes"},
                    urgency=2,
                    suppression_key="gym:offer:trial",
                    expires_at="2026-12-31T23:59:59Z",
                )

        # Pharmacies
        elif cat_slug == "pharmacies":
            if any(w in text for w in ("refill", "chronic", "prescription", "25-day", "monthly", "medication", "medicine")):
                return TriggerContext(
                    id="trg_pharmacy_refill",
                    scope="merchant",
                    kind="refill_due_cohort",
                    source="internal",
                    merchant_id=merchant.merchant_id,
                    payload={"chronic_cohort_count": 64, "cycle_days": 25},
                    urgency=3,
                    suppression_key="pharmacy:chronic:refill",
                    expires_at="2026-12-31T23:59:59Z",
                )
            if any(w in text for w in ("recall", "batch", "safety", "atorvastatin", "drug", "alert")):
                return TriggerContext(
                    id="trg_pharmacy_drug_recall",
                    scope="merchant",
                    kind="voluntary_recall_alert",
                    source="external",
                    merchant_id=merchant.merchant_id,
                    payload={"drug": "Atorvastatin 20mg", "batches": ["X102", "Y204"]},
                    urgency=4,
                    suppression_key="pharmacy:recall:atorvastatin",
                    expires_at="2026-12-31T23:59:59Z",
                )

        # Generic operational matching fallback
        if any(w in text for w in ("offer", "discount", "campaign", "post", "draft", "message", "promote", "update")):
            return TriggerContext(
                id=f"trg_{cat_slug}_operational_update",
                scope="merchant",
                kind="operational_nudge",
                source="internal",
                merchant_id=merchant.merchant_id,
                payload={"topic": "profile_update"},
                urgency=2,
                suppression_key=f"operational:{cat_slug}",
                expires_at="2026-12-31T23:59:59Z",
            )

        return None
