"""Fundle Brain - AI Chat with real DB function calling."""
import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    ai_chats_col, points_ledger_col, nps_col
)
from auth import get_current_user, log_audit
from models import AIChatRequest

router = APIRouter(prefix="/ai", tags=["ai"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

SYSTEM_PROMPT = """You are Fundle Brain, the AI analytics assistant for KAZO (premium Indian women's fashion brand) powered by Fundle.

Your role:
- Answer business questions about Kazo's loyalty, CRM, customers, sales, stores, campaigns
- ALWAYS query the real database via the tools/data provided to you in the user message
- NEVER fabricate numbers - if data is not present say "Data not available"
- Be concise, executive-friendly, and action-oriented
- When you have data, summarise insights then suggest 1-2 concrete actions (e.g., "Launch a win-back campaign with 20% coupon")

Brand voice: Refined, premium fashion editorial tone. Use ₹ for currency.
"""


async def _gather_context(query: str) -> dict:
    """Pre-fetch relevant data based on query keywords."""
    q = query.lower()
    ctx = {}

    if any(k in q for k in ["churn", "win-back", "winback", "win back", "inactive", "dormant"]):
        # Top churning customers
        cutoff = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        top_churn = await customers_col.find(
            {"last_visit_at": {"$lt": cutoff}, "lifetime_spend": {"$gt": 5000}},
            {"_id": 0, "name": 1, "mobile": 1, "city": 1, "lifetime_spend": 1, "tier": 1, "last_visit_at": 1, "churn_risk": 1}
        ).sort("lifetime_spend", -1).limit(15).to_list(15)
        ctx["churning_customers"] = top_churn

    if any(k in q for k in ["store", "stores", "city", "region", "underperform"]):
        # Store performance last 30d
        start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        pipe = [
            {"$match": {"bill_date": {"$gte": start}}},
            {"$group": {"_id": "$store_id", "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
            {"$sort": {"net": -1}},
        ]
        rows = await transactions_col.aggregate(pipe).to_list(50)
        store_ids = [r["_id"] for r in rows]
        stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}
        ctx["store_performance_30d"] = [
            {"store": stores.get(r["_id"], {}).get("name"), "city": stores.get(r["_id"], {}).get("city"),
             "net": round(r["net"], 2), "txns": r["txns"]} for r in rows
        ]

    if any(k in q for k in ["campaign", "roi", "best campaign"]):
        camps = await campaigns_col.find({}, {"_id": 0}).sort("revenue_generated", -1).limit(15).to_list(15)
        ctx["campaigns"] = [
            {"name": c["name"], "channels": c.get("channels", []), "sent": c["sent"],
             "delivered": c["delivered"], "redeemed": c["redeemed"],
             "revenue": round(c["revenue_generated"], 2), "status": c.get("status")}
            for c in camps
        ]

    if any(k in q for k in ["sku", "product", "best seller", "top selling", "category"]):
        start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        pipe = [
            {"$match": {"bill_date": {"$gte": start}}},
            {"$unwind": "$items"},
            {"$group": {"_id": {"sku": "$items.sku", "name": "$items.name", "category": "$items.category"},
                        "revenue": {"$sum": "$items.total"}, "qty": {"$sum": "$items.quantity"}}},
            {"$sort": {"revenue": -1}}, {"$limit": 15}
        ]
        rows = await transactions_col.aggregate(pipe).to_list(20)
        ctx["top_skus_30d"] = [
            {"sku": r["_id"]["sku"], "name": r["_id"]["name"], "category": r["_id"]["category"],
             "revenue": round(r["revenue"], 2), "qty": r["qty"]}
            for r in rows
        ]

    if any(k in q for k in ["loyalty", "penetration", "tier", "vip"]):
        pipe = [{"$group": {"_id": "$tier", "count": {"$sum": 1}, "spend": {"$sum": "$lifetime_spend"}}}]
        rows = await customers_col.aggregate(pipe).to_list(20)
        ctx["tier_distribution"] = [{"tier": r["_id"], "count": r["count"], "spend": round(r["spend"], 2)} for r in rows]

    if any(k in q for k in ["nps", "feedback", "complaint", "satisfaction"]):
        start = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        pipe = [
            {"$match": {"created_at": {"$gte": start}}},
            {"$group": {"_id": "$sentiment", "count": {"$sum": 1}}}
        ]
        rows = await nps_col.aggregate(pipe).to_list(10)
        ctx["nps_60d"] = [{"sentiment": r["_id"], "count": r["count"]} for r in rows]

    # Always include overall summary
    total_customers = await customers_col.count_documents({})
    start30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    sales_pipe = [
        {"$match": {"bill_date": {"$gte": start30}}},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}}
    ]
    sales = await transactions_col.aggregate(sales_pipe).to_list(1)
    ctx["overall_30d"] = {
        "total_customers": total_customers,
        "net_sales_30d": round(sales[0]["net"], 2) if sales else 0,
        "txns_30d": sales[0]["txns"] if sales else 0,
    }
    return ctx


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    rows = await ai_chats_col.find({"user_id": user["id"]}, {"_id": 0, "messages": 0}).sort("updated_at", -1).limit(50).to_list(50)
    return rows


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    s = await ai_chats_col.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Session not found")
    return s


@router.post("/chat")
async def chat(req: AIChatRequest, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")

    session_id = req.session_id or uuid.uuid4().hex
    existing = await ai_chats_col.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})

    # Gather real DB context based on query
    ctx = await _gather_context(req.message)

    enriched = (
        f"User question: {req.message}\n\n"
        f"=== Real-time data from Kazo MongoDB (use these numbers ONLY) ===\n"
        f"{json.dumps(ctx, indent=2, default=str)}\n\n"
        f"Analyse the above data and answer the user's question. If specific data isn't above, say 'Data not available'."
    )

    model_name = req.model or "gpt-5.2"
    provider = "openai"
    if "claude" in model_name.lower():
        provider = "anthropic"
        model_name = "claude-sonnet-4-5-20250929"
    elif "gemini" in model_name.lower():
        provider = "gemini"
        model_name = "gemini-2.5-pro"
    else:
        model_name = "gpt-5.2"

    try:
        llm = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=SYSTEM_PROMPT).with_model(provider, model_name)
        msg = UserMessage(text=enriched)
        reply = await llm.send_message(msg)
    except Exception as e:
        raise HTTPException(500, f"AI error: {str(e)}")

    now = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user", "content": req.message, "timestamp": now}
    bot_msg = {"role": "assistant", "content": reply, "timestamp": now, "data": ctx if len(json.dumps(ctx)) < 8000 else None}
    if existing:
        await ai_chats_col.update_one(
            {"id": session_id},
            {"$push": {"messages": {"$each": [user_msg, bot_msg]}}, "$set": {"updated_at": now}}
        )
    else:
        title = req.message[:50]
        await ai_chats_col.insert_one({
            "id": session_id,
            "user_id": user["id"],
            "title": title,
            "messages": [user_msg, bot_msg],
            "created_at": now,
            "updated_at": now,
            "model": f"{provider}/{model_name}",
        })

    await log_audit(user, "ai_chat", "ai_session", session_id, {"q": req.message[:200]})
    return {"session_id": session_id, "reply": reply, "data_used": ctx}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    await ai_chats_col.delete_one({"id": session_id, "user_id": user["id"]})
    return {"success": True}


@router.get("/suggested-prompts")
async def suggested_prompts(user: dict = Depends(get_current_user)):
    return [
        "Show me top churning customers this month",
        "Which stores are underperforming in last 30 days?",
        "Which campaign gave the best ROI?",
        "Which customers should get win-back coupons?",
        "Which SKUs drive the most repeat purchases?",
        "Which cities have the strongest loyalty penetration?",
        "What is the breakdown of customers by tier?",
        "How is the NPS trending and what should we do?",
    ]
