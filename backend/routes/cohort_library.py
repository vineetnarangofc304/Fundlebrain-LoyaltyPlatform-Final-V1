"""KAZO Cohort Library — curated, pre-built customer segments rooted in
loyalty analyst best practices (R1-R6 rules).

Each cohort = a name + category + description + build_filter callable.
The callable receives a context dict with system-wide metrics (e.g. ATV) that
get substituted into the filter tree at request time.

Mounted under /api/segments/cohort-library
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import get_current_user
from database import customers_col, transactions_col
from routes._loyalty import LOYALTY_TX_MATCH


router = APIRouter(prefix="/segments/cohort-library", tags=["segments"])


# ============================================================
# System-wide context (used as thresholds in cohort filters)
# ============================================================
async def build_context() -> Dict[str, Any]:
    """Compute system-wide metrics that thresholds depend on.

    Returns:
      atv:        system-wide Average Transaction Value (₹) across all
                  loyalty bills (R5). Used as the "Above/Below ATV" threshold.
      total_loyalty_customers, total_bills, etc — informational only.
    """
    sums = await transactions_col.aggregate([
        {"$match": LOYALTY_TX_MATCH},
        {"$group": {"_id": None,
                    "net": {"$sum": "$net_amount"},
                    "bills": {"$sum": 1}}},
    ]).to_list(1)
    if sums:
        net = sums[0].get("net", 0) or 0
        bills = sums[0].get("bills", 0) or 1
        atv = round(net / max(bills, 1), 2)
    else:
        atv = 0
    total_cust = await customers_col.count_documents({"mobile": {"$nin": [None, ""]}})
    return {"atv": atv, "total_loyalty_customers": total_cust,
             "total_bills": sums[0].get("bills", 0) if sums else 0}


# ============================================================
# Cohort builder helpers — small functions composed below
# ============================================================
def _r(field: str, operator: str, value: Any) -> Dict[str, Any]:
    return {"field": field, "operator": operator, "value": value}


def _and(*rules) -> Dict[str, Any]:
    return {"op": "AND", "rules": list(rules)}


def _or(*rules) -> Dict[str, Any]:
    return {"op": "OR", "rules": list(rules)}


def f_lifecycle(*kinds: str) -> Dict[str, Any]:
    return _r("lifecycle", "in", list(kinds))


def f_recency_band(*bands: str) -> Dict[str, Any]:
    return _r("recency_band", "in", list(bands))


def f_days_since_visit(lo: int, hi: int) -> Dict[str, Any]:
    return _r("days_since_last_visit", "between", [lo, hi])


def f_aov_above(threshold: float) -> Dict[str, Any]:
    return _r("aov", "gte", float(threshold))


def f_aov_below(threshold: float) -> Dict[str, Any]:
    return _r("aov", "lte", float(threshold))


def f_visits_between(lo: int, hi: int) -> Dict[str, Any]:
    return _r("visit_count", "between", [lo, hi])


def f_visits_gte(n: int) -> Dict[str, Any]:
    return _r("visit_count", "gte", n)


def f_visits_eq(n: int) -> Dict[str, Any]:
    return _r("visit_count", "eq", n)


def f_day_pattern(p: str) -> Dict[str, Any]:
    return _r("day_pattern", "in", [p])


def f_tier(*tiers: str) -> Dict[str, Any]:
    return _r("tier", "in", list(tiers))


def f_birthday_in(days: int) -> Dict[str, Any]:
    return _r("birthday_window", "lte", days)


def f_anniversary_in(days: int) -> Dict[str, Any]:
    return _r("anniversary_window", "lte", days)


def f_points_gte(p: int) -> Dict[str, Any]:
    return _r("points_balance", "gte", p)


def f_points_lte(p: int) -> Dict[str, Any]:
    return _r("points_balance", "lte", p)


def f_lifetime_earned_gte(n: int) -> Dict[str, Any]:
    return _r("lifetime_points_earned", "gte", n)


def f_lifetime_redeemed_gte(n: int) -> Dict[str, Any]:
    return _r("lifetime_points_redeemed", "gte", n)


def f_burn_ratio_lte(pct: float) -> Dict[str, Any]:
    return _r("burn_ratio", "lte", pct)


def f_burn_ratio_gte(pct: float) -> Dict[str, Any]:
    return _r("burn_ratio", "gte", pct)


def f_churn_risk(*levels: str) -> Dict[str, Any]:
    return _r("churn_risk", "in", list(levels))


def f_wa_optin(v: bool = True) -> Dict[str, Any]:
    return _r("wa_opt_in", "eq", v)


def f_has_email(v: bool = True) -> Dict[str, Any]:
    return _r("has_email", "eq", v)


# ============================================================
# CATALOG — the meat of this module
# Each entry: dict with id / category / name / description / build(ctx)
# ============================================================
CATALOG: List[Dict[str, Any]] = []


def _C(category: str, cid: str, name: str, description: str,
       build: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    CATALOG.append({"id": cid, "category": category, "name": name,
                     "description": description, "build": build})


# ──────────────────────────────────────────────────────────────
# 1. Overall + Sanity cohorts
# ──────────────────────────────────────────────────────────────
_C("Overall", "loyal_members",
    "Overall Loyalty Members",
    "Every customer holding a loyalty record (i.e. has a mobile on file). The denominator for almost every other cohort.",
    lambda ctx: _and(_r("has_mobile", "eq", True)))

_C("Overall", "zero_purchase",
    "Members with Zero Purchase",
    "Loyalty members who have NEVER transacted — sign-ups that never converted. Re-engagement priority.",
    lambda ctx: _and(f_lifecycle("never")))


# ──────────────────────────────────────────────────────────────
# 2. One-Timer (visit_count == 1) cohorts
# ──────────────────────────────────────────────────────────────
_C("One-Timer", "one_timer",
    "One-Timer · Overall",
    "Bought exactly once. The largest reactivation pool — convert them into Repeat customers.",
    lambda ctx: _and(f_lifecycle("one_timer")))

_C("One-Timer", "one_timer_above_atv",
    "One-Timer · Above ATV",
    "Bought once with a ticket above the brand's ATV (₹{atv}). High-value first impression — premium upsell candidates.",
    lambda ctx: _and(f_lifecycle("one_timer"), f_aov_above(ctx["atv"])))

_C("One-Timer", "one_timer_below_atv",
    "One-Timer · Below ATV",
    "Bought once at a smaller ticket. Volume reactivation pool — bundle / accessory campaigns work best.",
    lambda ctx: _and(f_lifecycle("one_timer"), f_aov_below(ctx["atv"])))

# Recency × Spend grid (One-Timer)
def _ot_recency(spend_label: str, spend_fn, recency_label: str,
                  recency_rule, day_label: str = "", day_rule=None):
    rules = [f_lifecycle("one_timer"), spend_fn, recency_rule]
    if day_rule is not None:
        rules.append(day_rule)
    title_day = f" · {day_label}" if day_label else ""
    return _and(*rules), title_day


def _add_one_timer_grid():
    """One-timer × Above/Below ATV × Recency × Day-pattern grid."""
    recency_buckets = [
        ("0-3 months",  f_days_since_visit(0, 90)),
        ("3-6 months",  f_days_since_visit(91, 180)),
        ("6-12 months", f_days_since_visit(181, 365)),
    ]
    day_buckets = [
        ("", None),
        ("Weekday Only", f_day_pattern("weekday_only")),
        ("Weekend Only", f_day_pattern("weekend_only")),
    ]
    spend_buckets = [
        ("Above ATV", f_aov_above, "above_atv"),
        ("Below ATV", f_aov_below, "below_atv"),
    ]
    for s_lbl, s_fn, s_id in spend_buckets:
        for r_lbl, r_rule in recency_buckets:
            for d_lbl, d_rule in day_buckets:
                day_suffix = f" ({d_lbl})" if d_lbl else ""
                day_id = f"_{d_lbl.lower().replace(' ', '_')}" if d_lbl else ""
                short = r_lbl.replace(" months", "m").replace("-", "_")
                cid = f"one_timer_{s_id}_{short}{day_id}"
                title = f"One-Timer · {s_lbl} · Visited last {r_lbl}{day_suffix}"
                desc = f"Bought once {s_lbl.lower()}, last visit {r_lbl} ago{day_suffix.lower()}. "
                if d_lbl == "Weekday Only":
                    desc += "Predictable mid-week shopper — push office/work-wear stories."
                elif d_lbl == "Weekend Only":
                    desc += "Weekend-oriented shopper — push occasion / event launches."
                else:
                    desc += "Reactivation push within their recency window."
                # Use closure with frozen args
                def make_build(spend_fn=s_fn, recency_rule=r_rule, day_rule=d_rule):
                    def b(ctx):
                        rules = [f_lifecycle("one_timer"), spend_fn(ctx["atv"]), recency_rule]
                        if day_rule is not None:
                            rules.append(day_rule)
                        return _and(*rules)
                    return b
                _C("One-Timer Recency × Spend", cid, title, desc, make_build())


_add_one_timer_grid()

# Long-dormant one-timers
_C("One-Timer Dormant", "one_timer_12_24m",
    "One-Timers · Not Visited 12-24 months",
    "Bought once, last visit 12–24 months ago. Win-back territory — strong incentive needed.",
    lambda ctx: _and(f_lifecycle("one_timer"), f_days_since_visit(365, 730)))

_C("One-Timer Dormant", "one_timer_24_plus_m",
    "One-Timers · Not Visited 24+ months",
    "Bought once, dormant 24+ months. Effectively lapsed — consider a final goodbye / lapsed-VIP offer.",
    lambda ctx: _and(f_lifecycle("one_timer"), _r("days_since_last_visit", "gte", 730)))


# ──────────────────────────────────────────────────────────────
# 3. Repeat customer cohorts (visit_count >= 2)
# ──────────────────────────────────────────────────────────────
_C("Repeat", "repeat",
    "Repeat Customers · Overall",
    "Anyone who's bought 2+ times. The retained base — defend the relationship.",
    lambda ctx: f_visits_gte(2))

_C("Repeat", "repeat_above_atv",
    "Repeat · Above ATV · Overall",
    "Repeat customers transacting above the brand's ATV (₹{atv}) on average. High-LTV retention focus.",
    lambda ctx: _and(f_visits_gte(2), f_aov_above(ctx["atv"])))

_C("Repeat", "repeat_below_atv",
    "Repeat · Below ATV · Overall",
    "Repeat customers transacting below ATV (₹{atv}) on average. Frequency-up / basket-up targeting.",
    lambda ctx: _and(f_visits_gte(2), f_aov_below(ctx["atv"])))


def _add_repeat_frequency_grid():
    """Repeat × visit-count buckets × Above/Below ATV."""
    buckets = [
        ("2-5",   f_visits_between(2, 5),   "2_5"),
        ("6-10",  f_visits_between(6, 10),  "6_10"),
        ("11-15", f_visits_between(11, 15), "11_15"),
        ("16-20", f_visits_between(16, 20), "16_20"),
        ("21+",   f_visits_gte(21),          "21_plus"),
    ]
    spend_buckets = [
        ("Above ATV", f_aov_above, "above_atv"),
        ("Below ATV", f_aov_below, "below_atv"),
    ]
    for vis_lbl, vis_rule, vis_id in buckets:
        for s_lbl, s_fn, s_id in spend_buckets:
            cid = f"repeat_{vis_id}_visits_{s_id}"
            title = f"Repeat · {vis_lbl} visits · {s_lbl}"
            desc = f"Customers with {vis_lbl} lifetime visits at {s_lbl.lower()} ticket."
            if vis_lbl == "21+":
                desc += " VIP tier — protect & reward."
            elif vis_lbl in ("11-15", "16-20"):
                desc += " Loyal champions — incentivise advocacy & referrals."
            elif vis_lbl == "6-10":
                desc += " Habit-forming — push tier-upgrade nudges."
            elif vis_lbl == "2-5":
                desc += " Early-repeat — drive 3rd/4th visit."

            def make_build(vrule=vis_rule, sfn=s_fn):
                def b(ctx):
                    return _and(vrule, sfn(ctx["atv"]))
                return b
            _C("Repeat Frequency × Spend", cid, title, desc, make_build())


_add_repeat_frequency_grid()

# Repeat dormant
_C("Repeat Dormant", "repeat_12_24m",
    "Repeat · Not Visited 12-24 months",
    "Was a repeat customer, now silent 12–24 months. Highest-LTV win-back priority.",
    lambda ctx: _and(f_visits_gte(2), f_days_since_visit(365, 730)))

_C("Repeat Dormant", "repeat_24_plus_m",
    "Repeat · Not Visited 24+ months",
    "Repeat customers fully lapsed 24+ months. Final-attempt or quietly-archive.",
    lambda ctx: _and(f_visits_gte(2), _r("days_since_last_visit", "gte", 730)))


# ──────────────────────────────────────────────────────────────
# 4. Recency Bands (universal slice)
# ──────────────────────────────────────────────────────────────
_C("Recency", "recency_0_3m",
    "All Customers · Last visit 0-3 months",
    "Active in the last quarter. Capacity to convert to higher-frequency.",
    lambda ctx: f_days_since_visit(0, 90))

_C("Recency", "recency_3_6m",
    "All Customers · Last visit 3-6 months",
    "Slowing down — push a 'we missed you' nudge before they drift further.",
    lambda ctx: f_days_since_visit(91, 180))

_C("Recency", "recency_6_12m",
    "All Customers · Last visit 6-12 months",
    "At-risk band. Strong incentive needed to bring back.",
    lambda ctx: f_days_since_visit(181, 365))

_C("Recency", "recency_12_24m",
    "All Customers · Last visit 12-24 months",
    "Lapsed pool — high-friction reactivation segment.",
    lambda ctx: f_days_since_visit(365, 730))

_C("Recency", "recency_24_plus_m",
    "All Customers · Lapsed 24+ months",
    "Dormant beyond recovery for most. Use for goodbye / data-cleanup decisioning.",
    lambda ctx: _r("days_since_last_visit", "gte", 730))


# ──────────────────────────────────────────────────────────────
# 5. Lifecycle journey — new, 2nd-visit, milestone, reactivated
# ──────────────────────────────────────────────────────────────
_C("Lifecycle Journey", "new_customer_30d",
    "First Bill in last 30 days",
    "Brand new loyalty customers — welcome flow & 2nd-visit nudge are priority.",
    lambda ctx: _and(_r("first_purchase_at", "gte",
                          # last 30 days
                          (__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
                           - __import__('datetime').timedelta(days=30)).isoformat())))

_C("Lifecycle Journey", "new_customer_90d",
    "First Bill in last 90 days",
    "New within the quarter. Tier-velocity targeting.",
    lambda ctx: _and(_r("first_purchase_at", "gte",
                          (__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
                           - __import__('datetime').timedelta(days=90)).isoformat())))

_C("Lifecycle Journey", "second_visit_milestone",
    "Hit 2nd Visit · Recent",
    "Customers with exactly 2 bills, last visit in last 60 days. Critical 3rd-visit nudge.",
    lambda ctx: _and(f_visits_eq(2), f_days_since_visit(0, 60)))

_C("Lifecycle Journey", "reactivated_after_gap",
    "Reactivated after 6+ month gap",
    "Returned in the last 30 days after a 180+ day silent gap. Re-onboard with care.",
    lambda ctx: _and(f_days_since_visit(0, 30), f_visits_gte(2)))


# ──────────────────────────────────────────────────────────────
# 6. Tier strategy
# ──────────────────────────────────────────────────────────────
_C("Tier Strategy", "tier_platinum",
    "Platinum tier members",
    "Top-most spending tier. Concierge messaging, no discount-heavy noise.",
    lambda ctx: f_tier("platinum"))

_C("Tier Strategy", "tier_gold",
    "Gold tier members",
    "High-value tier. Reinforce status; tease platinum-upgrade rewards.",
    lambda ctx: f_tier("gold"))

_C("Tier Strategy", "tier_silver",
    "Silver tier members",
    "Mid-tier — biggest tier-upgrade opportunity pool.",
    lambda ctx: f_tier("silver"))

_C("Tier Strategy", "tier_bronze",
    "Bronze tier members",
    "Entry tier — focus on visit frequency to graduate them up.",
    lambda ctx: f_tier("bronze"))

_C("Tier Strategy", "tier_gold_plus_dormant_90d",
    "Gold/Platinum · Dormant 90+ days",
    "High-tier members who've gone quiet >90 days. Retention SOS — escalate to personal outreach.",
    lambda ctx: _and(f_tier("gold", "platinum"), _r("days_since_last_visit", "gte", 90)))

_C("Tier Strategy", "tier_silver_high_visit",
    "Silver · 6+ visits · Above ATV",
    "Silver tier behaving like gold — instant tier-upgrade campaign targets.",
    lambda ctx: _and(f_tier("silver"), f_visits_gte(6), f_aov_above(ctx["atv"])))


# ──────────────────────────────────────────────────────────────
# 7. Wallet & Points behaviour
# ──────────────────────────────────────────────────────────────
_C("Wallet & Points", "wallet_rich_never_redeemed",
    "Wallet-rich · Never Redeemed",
    "Holding 500+ points but lifetime redemptions = 0. Education / first-burn nudges.",
    lambda ctx: _and(f_points_gte(500), _r("lifetime_points_redeemed", "lte", 0)))

_C("Wallet & Points", "wallet_rich_heavy_burner",
    "Wallet-rich · Heavy Burner",
    "500+ points balance AND burn ratio ≥ 50%. Active redeemers — protect from over-discount.",
    lambda ctx: _and(f_points_gte(500), f_burn_ratio_gte(50)))

_C("Wallet & Points", "wallet_low_active",
    "Wallet-low · Active",
    "Points balance ≤ 100 but visited in last 90 days. Accrual nudge to drive next basket.",
    lambda ctx: _and(f_points_lte(100), f_days_since_visit(0, 90)))

_C("Wallet & Points", "wallet_no_burn_3y",
    "Lifetime earned 1000+ · Never redeemed",
    "Earned 1000+ points across their lifetime, zero burn. Communicate redemption value.",
    lambda ctx: _and(f_lifetime_earned_gte(1000), _r("lifetime_points_redeemed", "lte", 0)))

_C("Wallet & Points", "high_lifetime_redeemed",
    "Lifetime redeemed 5000+ points",
    "Has burned 5000+ points lifetime. Loyalty-program champions.",
    lambda ctx: f_lifetime_redeemed_gte(5000))


# ──────────────────────────────────────────────────────────────
# 8. Birthday & Anniversary
# ──────────────────────────────────────────────────────────────
_C("Birthday & Anniversary", "birthday_30d",
    "Birthday in next 30 days",
    "Anyone whose birthday falls in the next 30 days. Plan a birthday treat campaign.",
    lambda ctx: _and(f_birthday_in(30), _r("has_mobile", "eq", True)))

_C("Birthday & Anniversary", "birthday_7d",
    "Birthday in next 7 days",
    "Birthday this week — last-minute send window.",
    lambda ctx: _and(f_birthday_in(7), _r("has_mobile", "eq", True)))

_C("Birthday & Anniversary", "birthday_premium",
    "Birthday in 30d · Gold/Platinum",
    "High-tier members with birthdays in 30 days. Premium gifting / VIP touch.",
    lambda ctx: _and(f_birthday_in(30), f_tier("gold", "platinum")))

_C("Birthday & Anniversary", "anniversary_30d",
    "Anniversary in next 30 days",
    "Customer's account anniversary in 30 days. Loyalty-milestone storytelling.",
    lambda ctx: _and(f_anniversary_in(30), _r("has_mobile", "eq", True)))


# ──────────────────────────────────────────────────────────────
# 9. Channel reach
# ──────────────────────────────────────────────────────────────
_C("Channel Reach", "wa_reachable",
    "WhatsApp reachable",
    "Customers with mobile + WA opt-in. Primary KAZO comms channel.",
    lambda ctx: _and(_r("has_mobile", "eq", True), f_wa_optin(True)))

_C("Channel Reach", "email_reachable",
    "Email reachable",
    "Customers with an email + email opt-in.",
    lambda ctx: _and(f_has_email(True), _r("email_opt_in", "eq", True)))

_C("Channel Reach", "multi_channel",
    "Multi-channel reachable (WA + Email)",
    "Both WA and email — flexible campaign cadence.",
    lambda ctx: _and(_r("has_mobile", "eq", True), f_wa_optin(True),
                      f_has_email(True), _r("email_opt_in", "eq", True)))

_C("Channel Reach", "opt_out_all",
    "Opted-out (any channel)",
    "Customers who have explicitly opted out of any channel. DO NOT contact list.",
    lambda ctx: _or(_r("wa_opt_in", "eq", False),
                     _r("sms_opt_in", "eq", False),
                     _r("email_opt_in", "eq", False)))


# ──────────────────────────────────────────────────────────────
# 10. Risk & retention
# ──────────────────────────────────────────────────────────────
_C("Risk & Retention", "churn_risk_high",
    "Churn risk · High",
    "Algorithm-tagged high-churn-risk customers. Top-priority retention list.",
    lambda ctx: f_churn_risk("high"))

_C("Risk & Retention", "vip_at_risk",
    "VIPs at Risk · No visit 90+ days",
    "Top-spending (≥5 visits + above-ATV) members silent 90+ days. Concierge intervention.",
    lambda ctx: _and(f_visits_gte(5), f_aov_above(ctx["atv"]),
                      _r("days_since_last_visit", "gte", 90)))


# ============================================================
# Endpoints
# ============================================================
class CountsIn(BaseModel):
    cohort_ids: List[str]


@router.get("/")
async def list_cohorts(
    include_counts: bool = Query(False, description="Slow on large datasets — prefer lazy + /counts batch endpoint"),
    user: dict = Depends(get_current_user),
):
    """List the cohort catalog (metadata).

    By default returns catalog metadata WITHOUT counts (instant).
    Use POST /counts in batches to fetch counts for visible cohorts.
    """
    ctx = await build_context()

    out: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}

    if include_counts:
        from routes.segments_routes import compile_tree  # lazy import to avoid cycle
        async def _count_one(c: Dict[str, Any]) -> tuple:
            try:
                tree = c["build"](ctx)
                match = await asyncio.wait_for(compile_tree(tree), timeout=5.0)
                n = await asyncio.wait_for(
                    customers_col.count_documents(match), timeout=5.0
                )
                return c["id"], n
            except Exception:
                return c["id"], -1
        results = await asyncio.gather(*[_count_one(c) for c in CATALOG])
        counts = dict(results)

    for c in CATALOG:
        item = {
            "id": c["id"],
            "category": c["category"],
            "name": c["name"],
            "description": c["description"].format(atv=int(ctx["atv"])),
        }
        if include_counts:
            item["matched_total"] = counts.get(c["id"], -1)
        out.append(item)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in out:
        grouped.setdefault(item["category"], []).append(item)

    return {"context": ctx, "categories": [
        {"name": cat, "cohorts": items} for cat, items in grouped.items()
    ]}


@router.post("/counts")
async def batch_counts(
    body: CountsIn,
    user: dict = Depends(get_current_user),
):
    """Return matched_total for a batch of cohort_ids. Runs in parallel with
    a per-cohort timeout so one slow query never blocks the whole batch.

    Use this from the frontend when a category is expanded — request counts
    only for those visible cohort tiles.
    """
    if not body.cohort_ids:
        return {"counts": {}}

    ctx = await build_context()
    from routes.segments_routes import compile_tree  # lazy import

    catalog_index = {c["id"]: c for c in CATALOG}

    async def _count_one(cid: str) -> tuple:
        c = catalog_index.get(cid)
        if not c:
            return cid, -1
        try:
            tree = c["build"](ctx)
            match = await asyncio.wait_for(compile_tree(tree), timeout=8.0)
            n = await asyncio.wait_for(
                customers_col.count_documents(match), timeout=8.0
            )
            return cid, n
        except Exception:
            return cid, -1

    pairs = await asyncio.gather(*[_count_one(cid) for cid in body.cohort_ids])
    return {"counts": {cid: n for cid, n in pairs}}


@router.get("/{cohort_id}")
async def get_cohort(cohort_id: str, user: dict = Depends(get_current_user)):
    """Return the resolved filter tree for a single cohort (uses live ATV)."""
    found = next((c for c in CATALOG if c["id"] == cohort_id), None)
    if not found:
        raise HTTPException(404, "Cohort not found")
    ctx = await build_context()
    return {
        "id": found["id"],
        "category": found["category"],
        "name": found["name"],
        "description": found["description"].format(atv=int(ctx["atv"])),
        "tree": found["build"](ctx),
        "context": ctx,
    }


@router.post("/{cohort_id}/preview")
async def preview_cohort(cohort_id: str, user: dict = Depends(get_current_user)):
    """Run a full preview (count + reach + sample) for a cohort id."""
    found = next((c for c in CATALOG if c["id"] == cohort_id), None)
    if not found:
        raise HTTPException(404, "Cohort not found")
    ctx = await build_context()
    tree = found["build"](ctx)
    # Lazy import to avoid cycle
    from routes.segments_routes import _compute_preview
    pre = await _compute_preview(tree, None)
    return {"cohort": {"id": found["id"], "name": found["name"], "tree": tree}, **pre}
