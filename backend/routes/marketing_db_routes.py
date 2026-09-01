"""Marketing Databases — externally-supplied audience lists (paste or CSV/Excel upload).

A dataset stores a de-duplicated list of mobile numbers (optionally with a store code) and,
computed against the loyalty base, how many are existing MEMBERS vs NON-members. Datasets are
selectable as a campaign audience (audience_type='marketing_db').
"""
import io
import re
import csv
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from database import db, customers_col
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from routes.blacklist_util import norm10

router = APIRouter(prefix="/marketing-db", tags=["marketing-db"])

marketing_db_col = db["marketing_databases"]
MAX_MOBILES = 200000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_mobiles_text(text: str) -> List[str]:
    """Extract 10-digit mobiles from free text (comma / space / newline / any separator)."""
    if not text:
        return []
    out = []
    for tok in re.split(r"[^0-9]+", text):
        m = norm10(tok)
        if len(m) == 10:
            out.append(m)
    return out


# Variable columns we can carry per-mobile from an upload and merge into the SMS as
# {{name}} {{points}} {{expiry}} {{link}} (KAZO Point 1 — variable part in Upload DB).
_VAR_ALIASES = {
    "mobile": ("mobile", "phone", "number", "msisdn", "contact", "mob"),
    "name": ("name", "customer", "first"),
    "points": ("points", "point", "pts", "balance"),
    "expiry": ("expiry", "expire", "expires", "valid", "validity"),
    "link": ("link", "url", "short"),
}


def _detect_columns(fields: List[Any]) -> Dict[str, Optional[str]]:
    """Map our variable keys → the actual header name found in the file (case-insensitive)."""
    res: Dict[str, Optional[str]] = {k: None for k in _VAR_ALIASES}
    for f in fields:
        fl = str(f).strip().lower()
        for key, keys in _VAR_ALIASES.items():
            if res[key] is None and any(k in fl for k in keys):
                res[key] = f
    return res


def _clean_val(v: Any) -> str:
    s = str(v).strip() if v is not None else ""
    return "" if s.lower() in ("", "nan", "none", "null") else s


def _rows_to_records(rows: List[Dict[str, Any]], cols: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
    """Build per-mobile variable records from parsed rows using the detected columns."""
    recs: List[Dict[str, Any]] = []
    for row in rows:
        rec: Dict[str, Any] = {"mobile": row.get(cols["mobile"]) if cols["mobile"] else None}
        for k in ("name", "points", "expiry", "link"):
            if cols.get(k) is not None:
                rec[k] = row.get(cols[k])
        recs.append(rec)
    return recs


async def _member_stats(mobiles: List[str]) -> Dict[str, Any]:
    """Count how many mobiles exist in the loyalty base (members) vs not, in chunks."""
    member_set = set()
    CH = 5000
    for i in range(0, len(mobiles), CH):
        chunk = mobiles[i:i + CH]
        async for c in customers_col.find({"mobile": {"$in": chunk}}, {"_id": 0, "mobile": 1}):
            member_set.add(c["mobile"])
    members = len(member_set)
    return {"member_count": members, "non_member_count": len(mobiles) - members,
            "member_set": member_set}


class MarketingDbIn(BaseModel):
    name: str
    description: Optional[str] = ""
    store_code: Optional[str] = None
    mobiles_text: Optional[str] = ""
    mobiles: Optional[List[str]] = None


async def _create(name: str, description: str, store_code: Optional[str],
                  records: List[Dict[str, Any]], source: str, user: dict) -> dict:
    if not name or not name.strip():
        raise HTTPException(400, "Dataset name is required")
    # Dedup by mobile (last row wins) while collecting its {name, points, expiry, link} vars.
    seen: Dict[str, Dict[str, str]] = {}
    for r in records:
        m = norm10(str(r.get("mobile") or ""))
        if len(m) != 10:
            continue
        vars_ = {k: _clean_val(r.get(k)) for k in ("name", "points", "expiry", "link")}
        seen[m] = {k: v for k, v in vars_.items() if v}
    mobiles = sorted(seen.keys())
    if not mobiles:
        raise HTTPException(400, "No valid 10-digit mobile numbers found")
    if len(mobiles) > MAX_MOBILES:
        raise HTTPException(400, f"Too many numbers ({len(mobiles)}). Max {MAX_MOBILES} per dataset.")
    variables = {m: v for m, v in seen.items() if v}
    # Guard the 16MB doc limit — cap the embedded per-mobile variable map.
    VAR_CAP = 120000
    if len(variables) > VAR_CAP:
        variables = {m: variables[m] for m in list(variables)[:VAR_CAP]}
    variable_columns = sorted({k for v in variables.values() for k in v})
    stats = await _member_stats(mobiles)
    doc = {
        "id": uuid.uuid4().hex,
        "name": name.strip(),
        "description": (description or "").strip(),
        "store_code": (store_code or "").strip() or None,
        "source": source,
        "mobiles": mobiles,
        "variables": variables,
        "variable_columns": variable_columns,
        "has_variables": bool(variables),
        "total": len(mobiles),
        "member_count": stats["member_count"],
        "non_member_count": stats["non_member_count"],
        "created_at": _now_iso(),
        "created_by": user.get("id"),
        "created_by_email": user.get("email"),
    }
    await marketing_db_col.insert_one(doc)
    await log_audit(user, "create_marketing_db", "marketing_db", doc["id"],
                    {"name": doc["name"], "total": doc["total"], "vars": variable_columns})
    doc.pop("_id", None)
    doc.pop("mobiles", None)
    doc.pop("variables", None)
    return doc


@router.post("")
async def create_marketing_db(body: MarketingDbIn, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    # Paste path — free text, mobiles only (no per-row variables).
    raw = list(body.mobiles or []) + _parse_mobiles_text(body.mobiles_text or "")
    records = [{"mobile": m} for m in raw]
    return await _create(body.name, body.description or "", body.store_code, records, "paste", user)


@router.post("/upload")
async def upload_marketing_db(file: UploadFile = File(...), name: str = Form(...),
                              description: str = Form(""), store_code: str = Form(""),
                              user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    raw_bytes = await file.read()
    fname = (file.filename or "").lower()
    records: List[Dict[str, Any]] = []
    if fname.endswith(".xlsx") or fname.endswith(".xls"):
        try:
            import pandas as pd
            xl = pd.read_excel(io.BytesIO(raw_bytes), dtype=str)
            cols = _detect_columns(list(xl.columns))
            if not cols["mobile"] and len(xl.columns):
                cols["mobile"] = xl.columns[0]
            rows = xl.to_dict(orient="records")
            records = _rows_to_records(rows, cols)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Could not parse Excel: {e}")
    else:
        # CSV / TXT — header-aware (capture variable columns), fall back to raw digit extraction.
        text = raw_bytes.decode("utf-8", errors="ignore")
        try:
            reader = csv.DictReader(io.StringIO(text))
            fields = list(reader.fieldnames or [])
            cols = _detect_columns(fields)
            if cols["mobile"]:
                records = _rows_to_records(list(reader), cols)
            else:
                records = [{"mobile": m} for m in _parse_mobiles_text(text)]
        except Exception:  # noqa: BLE001
            records = [{"mobile": m} for m in _parse_mobiles_text(text)]
    return await _create(name, description, store_code, records, f"upload:{fname}", user)


@router.get("")
async def list_marketing_db(user: dict = Depends(get_current_user)):
    rows = await marketing_db_col.find(
        {}, {"_id": 0, "mobiles": 0, "variables": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"rows": rows, "total": len(rows)}


@router.get("/{mdb_id}")
async def get_marketing_db(mdb_id: str, user: dict = Depends(get_current_user)):
    d = await marketing_db_col.find_one({"id": mdb_id}, {"_id": 0, "mobiles": 0, "variables": 0})
    if not d:
        raise HTTPException(404, "Marketing database not found")
    return d


@router.get("/{mdb_id}/customers")
async def marketing_db_customers(mdb_id: str, page: int = 1, page_size: int = 50,
                                 member: Optional[str] = None, q: Optional[str] = None,
                                 user: dict = Depends(get_current_user)):
    """Paginated view of the dataset's numbers with a member/non-member flag + name/tier for members."""
    d = await marketing_db_col.find_one({"id": mdb_id}, {"_id": 0, "mobiles": 1, "variables": 1})
    if not d:
        raise HTTPException(404, "Marketing database not found")
    mobiles = d.get("mobiles") or []
    var_map = d.get("variables") or {}
    if q:
        needle = norm10(q) or re.sub(r"\D", "", q)
        mobiles = [m for m in mobiles if needle in m]
    # Resolve members for the (filtered) list — chunked
    member_map: Dict[str, dict] = {}
    CH = 5000
    for i in range(0, len(mobiles), CH):
        chunk = mobiles[i:i + CH]
        async for c in customers_col.find(
                {"mobile": {"$in": chunk}},
                {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "city": 1, "points_balance": 1}):
            member_map[c["mobile"]] = c
    rows_all = [{"mobile": m, "is_member": m in member_map, "vars": var_map.get(m) or {}, **({
        "name": member_map[m].get("name"), "tier": member_map[m].get("tier"),
        "city": member_map[m].get("city"), "points_balance": member_map[m].get("points_balance"),
    } if m in member_map else {})} for m in mobiles]
    if member == "true":
        rows_all = [r for r in rows_all if r["is_member"]]
    elif member == "false":
        rows_all = [r for r in rows_all if not r["is_member"]]
    total = len(rows_all)
    start = max(0, (page - 1) * page_size)
    rows = rows_all[start:start + page_size]
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


@router.post("/{mdb_id}/recompute")
async def recompute_marketing_db(mdb_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    d = await marketing_db_col.find_one({"id": mdb_id}, {"_id": 0, "mobiles": 1})
    if not d:
        raise HTTPException(404, "Marketing database not found")
    stats = await _member_stats(d.get("mobiles") or [])
    await marketing_db_col.update_one({"id": mdb_id}, {"$set": {
        "member_count": stats["member_count"], "non_member_count": stats["non_member_count"],
        "recomputed_at": _now_iso()}})
    return {"ok": True, "member_count": stats["member_count"], "non_member_count": stats["non_member_count"]}


@router.delete("/{mdb_id}")
async def delete_marketing_db(mdb_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    res = await marketing_db_col.delete_one({"id": mdb_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Marketing database not found")
    await log_audit(user, "delete_marketing_db", "marketing_db", mdb_id, {})
    return {"ok": True}
