"""AI Message Personalization module for LeadHunter AI.

Generates tailored cold email and WhatsApp outreach messages for QUALIFIED leads
using the Anthropic Python SDK.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from ..config import Config, load_env_file, DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH
from ..db import Database
from ..log import get_logger, setup_logging
from ..models import Lead, LeadStatus

log = get_logger("personalizer")

SYSTEM_PROMPT = (
    "You are writing a cold email from a small agency to a local service business. "
    "PRODUCT: AI receptionist. It answers every phone call 24/7, books appointments "
    "into the practice's calendar, and knows their services and insurance info. When "
    "the front desk is busy or closed, it answers instead of going to voicemail. "
    "PRICING: $500 setup fee (one-time) plus $300 per month. First month of service "
    "is included in the setup fee. "
    "RULES: 5 to 7 sentences maximum. Mention the practice by name and reference "
    "their real rating and review count. NEVER claim their website is missing or "
    "broken, and never mention websites. NEVER use placeholders like {DEMO_URL}. "
    "NEVER ask for a phone call or meeting; ask a simple yes or no question instead. "
    "Never invent facts about the practice. End with 'Best regards' only. "
    "Include the pricing clearly in the message."
)

MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")


def get_anthropic_key(config: Optional[Config] = None) -> Optional[str]:
    """Retrieve ANTHROPIC_API_KEY from config or environment."""
    if config:
        key = config.get_secret("ANTHROPIC_API_KEY")
        if key:
            return key
    return os.environ.get("ANTHROPIC_API_KEY")


def build_user_prompt(lead: Lead) -> str:
    """Construct structured prompt with lead attributes for Claude."""
    tags = lead.tags or {}
    instagram = tags.get("instagram") or ("instagram.com" in (lead.website or "") and lead.website) or "None"
    facebook = tags.get("facebook") or ("facebook.com" in (lead.website or "") and lead.website) or "None"

    lead_data = {
        "business_name": lead.name,
        "city": lead.city,
        "category": lead.category,
        "phone": lead.phone or lead.phone_normalized or "None",
        "website_status": lead.website_status or "NO_WEBSITE",
        "rating": lead.rating if lead.rating is not None else "None",
        "review_count": lead.reviews_count if lead.reviews_count is not None else 0,
        "instagram": str(instagram),
        "facebook": str(facebook),
    }

    return (
        f"Business data:\n{json.dumps(lead_data, indent=2)}\n\n"
        f"Write a cold email to this business. Follow the system prompt rules exactly."
    )


def generate_template_fallback(lead: Lead) -> Dict[str, str]:
    """High-quality deterministic fallback when ANTHROPIC_API_KEY is not configured."""
    name = lead.name
    city = lead.city
    rating = f"{lead.rating}⭐" if lead.rating else "top-rated"
    reviews = f"{lead.reviews_count} Google reviews" if lead.reviews_count else "great customer reviews"

    email_subject = f"Never miss another call at {name}"
    email_body = (
        f"Hi Team {name},\n\n"
        f"With {reviews} ({rating}), you clearly deliver great service in {city}. But when your team is busy or after hours, missed calls go to voicemail.\n\n"
        f"I set up AI receptionists for businesses like yours. It answers every call 24/7 and books appointments directly into your calendar.\n\n"
        f"Setup is $500, then $300/month. Would this help you capture more calls?\n\n"
        f"Best regards"
    )

    wa_body = (
        f"Hi {name}! I set up an AI receptionist that answers calls 24/7 for $500 setup + $300/month. Want to hear how it sounds?"
    )

    return {
        "email_subject": email_subject,
        "email_message": email_body,
        "whatsapp_message": wa_body,
    }


def _call_claude(lead: Lead, api_key: str) -> str:
    """Make the actual API call to Anthropic."""
    client = anthropic.Anthropic(api_key=api_key, base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)
    user_prompt = build_user_prompt(lead)

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def generate_messages_for_lead(lead: Lead, api_key: Optional[str] = None) -> Dict[str, str]:
    """Generate outreach messages using Claude, with fallback."""
    if not api_key:
        api_key = get_anthropic_key()

    if not api_key:
        log.info("ANTHROPIC_API_KEY not set; utilizing deterministic template generation for Lead [ID %s]", lead.id)
        return generate_template_fallback(lead)

    try:
        text = _call_claude(lead, api_key)
        
        # Extract JSON from response
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            sanitized = match.group(0)
            parsed = json.loads(sanitized, strict=False)
            return {
                "email_subject": parsed.get("email_subject", f"Quick question for {lead.name}"),
                "email_message": parsed.get("email_message", ""),
                "whatsapp_message": parsed.get("whatsapp_message", ""),
            }
    except Exception as exc:
        log.error("Anthropic API error for lead '%s': %s", lead.name, exc)

    return generate_template_fallback(lead)


def personalize_qualified_leads(
    db: Optional[Database] = None,
    config: Optional[Config] = None,
    city: Optional[str] = None,
    limit: int = 100,
    delay_s: float = 0.5,
) -> List[Dict[str, Any]]:
    """Process QUALIFIED leads sitting at HOT or WARM tier and generate outreach messages."""
    load_env_file(DEFAULT_ENV_PATH)

    if config is None:
        try:
            config = Config.load(DEFAULT_CONFIG_PATH)
        except Exception:
            config = None

    if db is None:
        db = Database()

    # Query leads with status QUALIFIED and HOT or WARM tier
    if city:
        query = (
            "SELECT * FROM leads WHERE status = 'QUALIFIED' "
            "AND (lead_tier = 'HOT' OR lead_tier = 'WARM') "
            f"AND city = '{city}' ORDER BY id ASC LIMIT ?"
        )
        params = (limit,)
    else:
        query = (
            "SELECT * FROM leads WHERE status = 'QUALIFIED' "
            "AND (lead_tier = 'HOT' OR lead_tier = 'WARM') "
            "ORDER BY id ASC LIMIT ?"
        )
        params = (limit,)

    rows = db.conn.execute(query, params).fetchall()
    leads = [Lead.from_row(dict(r)) for r in rows]

    log.info("Starting AI personalization for %d QUALIFIED leads (limit=%d)...", len(leads), limit)

    api_key = get_anthropic_key(config)
    results: List[Dict[str, Any]] = []

    for idx, lead in enumerate(leads):
        log.info("Generating personalized outreach for Lead [ID %s]: '%s' (%s, %s)...", lead.id, lead.name, lead.lead_tier, lead.website_status)
        
        messages = generate_messages_for_lead(lead, api_key=api_key)
        
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        update_fields = {
            "email_subject": messages["email_subject"],
            "email_message": messages["email_message"],
            "whatsapp_message": messages["whatsapp_message"],
            "personalized_message": messages["email_message"],
            "updated_at": now,
        }

        db.update_lead(lead.id, update_fields)
        db.transition(
            lead_id=lead.id,
            to_status=LeadStatus.PERSONALIZED.value,
            stage="personalizer",
            event=f"Generated cold email & WhatsApp messages via Claude ({MODEL_NAME})",
            level="INFO",
            extra_fields=update_fields,
        )

        lead.status = LeadStatus.PERSONALIZED
        lead.email_subject = messages["email_subject"]
        lead.email_message = messages["email_message"]
        lead.whatsapp_message = messages["whatsapp_message"]

        log.info("Lead [ID %s] '%s' -> PERSONALIZED", lead.id, lead.name)
        
        results.append({
            "id": lead.id,
            "name": lead.name,
            "email_subject": lead.email_subject,
            "email_message": lead.email_message,
            "whatsapp_message": lead.whatsapp_message,
        })

        if delay_s > 0 and idx < len(leads) - 1:
            time.sleep(delay_s)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LeadHunter AI Personalizer")
    parser.add_argument("--city", default=None, help="City name filter")
    parser.add_argument("--limit", type=int, default=100, help="Max leads to process")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between calls in seconds")
    args = parser.parse_args()

    print(f"\n=== Running AI Personalization (city='{args.city}', limit={args.limit}) ===")
    results = personalize_qualified_leads(city=args.city, limit=args.limit, delay_s=args.delay)

    print("\n====================================================================================================")
    print("                    LEADHUNTER AI — GENERATED OUTREACH MESSAGES                        ")
    print("====================================================================================================")

    for r in results:
        print(f"\n---------------------------------------------------------------------------------")
        print(f"Lead ID {r['id']} | {r['name']}")
        print(f"📧 COLD EMAIL:")
        print(f"Subject: {r['email_subject']}")
        print(f"{r['email_message']}")
        print(f"\n💬 WHATSAPP:")
        print(f"{r['whatsapp_message']}")
        
    print(f"------------------------------------------------------------------------------------------")