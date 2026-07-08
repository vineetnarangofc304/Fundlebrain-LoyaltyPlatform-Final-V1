"""Master Brain attachment ingestion — images (vision) + reports (CSV/XLSX/PDF).

Parses an uploaded file into an `mb_attachments` document and returns a compact
summary the chat can reference. Reports also get their phone/mobile column
auto-detected so Master Brain can ACT on the listed customers.
"""
import base64
import csv
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import mb_attachments_col

IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_BYTES = 8_000_000
MAX_REPORT_BYTES = 6_000_000
DATASET_ROW_CAP = 20000  # full rows persisted per report so it becomes a searchable dataset
MOBILE_HEADER_HINTS = ("mobile", "phone", "msisdn", "contact", "whatsapp", "number")
POINTS_HEADER_HINTS = ("point", "credit", "pts")
_MOBILE_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ext(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()


def _norm_mobile(v: Any) -> Optional[str]:
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    if len(digits) >= 10:
        last10 = digits[-10:]
        if last10[0] in "6789":
            return last10
    return None


def _mobile_col_index(headers: List[str], rows: List[List[Any]]) -> Optional[int]:
    if not headers:
        return None
    # 1) header hint
    for i, h in enumerate(headers):
        if any(hint in str(h).lower() for hint in MOBILE_HEADER_HINTS):
            return i
    # 2) else the column whose NON-EMPTY values look most like mobiles (ignore blank
    #    cells so hundreds of trailing empty rows can't dilute the score below threshold)
    if rows:
        best, best_score = None, 0.0
        for i in range(len(headers)):
            vals = [r[i] for r in rows[:1000]
                    if i < len(r) and str(r[i]).strip() not in ("", "None")]
            if not vals:
                continue
            score = sum(1 for v in vals if _norm_mobile(v)) / len(vals)
            if score > best_score:
                best, best_score = i, score
        if best is not None and best_score >= 0.6:
            return best
    return None


def _detect_mobiles(headers: List[str], rows: List[List[Any]]) -> List[str]:
    col_idx = _mobile_col_index(headers, rows)
    mobiles: List[str] = []
    if col_idx is not None:
        seen = set()
        for r in rows:
            if col_idx < len(r):
                m = _norm_mobile(r[col_idx])
                if m and m not in seen:
                    seen.add(m)
                    mobiles.append(m)
    return mobiles


def _to_int_points(v: Any) -> Optional[int]:
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    try:
        f = float(s)
    except Exception:
        return None
    if f != f:  # NaN
        return None
    return int(round(f))


def _points_col_index(headers: List[str], rows: List[List[Any]], mobile_idx: Optional[int]) -> Optional[int]:
    if not headers:
        return None
    # 1) header hint (never the mobile column)
    for i, h in enumerate(headers):
        if i == mobile_idx:
            continue
        if any(hint in str(h).lower() for hint in POINTS_HEADER_HINTS):
            return i
    # 2) else a numeric column (not mobile) whose values are integer-like
    if rows:
        best, best_score = None, 0.0
        for i in range(len(headers)):
            if i == mobile_idx:
                continue
            vals = [r[i] for r in rows[:200] if i < len(r) and str(r[i]).strip() != ""]
            if not vals:
                continue
            score = sum(1 for v in vals if _to_int_points(v) is not None) / max(len(vals), 1)
            if score > best_score:
                best, best_score = i, score
        if best is not None and best_score >= 0.8:
            return best
    return None


def _detect_points_pairs(headers: List[str], rows: List[List[Any]]):
    """Return (mobile_points, dup_count). `mobile_points` is a list of
    {"mobile": <10-digit>, "points": <int>} read from a per-row points column;
    duplicate mobiles are SUMMED. Empty list when no points column is present."""
    if not headers or not rows:
        return [], 0
    m_idx = _mobile_col_index(headers, rows)
    if m_idx is None:
        return [], 0
    p_idx = _points_col_index(headers, rows, m_idx)
    if p_idx is None:
        return [], 0
    agg: Dict[str, int] = {}
    order: List[str] = []
    dups = 0
    for r in rows:
        if m_idx >= len(r) or p_idx >= len(r):
            continue
        m = _norm_mobile(r[m_idx])
        pts = _to_int_points(r[p_idx])
        if not m or pts is None:
            continue
        if m in agg:
            dups += 1
            agg[m] += pts
        else:
            agg[m] = pts
            order.append(m)
    return [{"mobile": m, "points": agg[m]} for m in order], dups


def _row_is_empty(r: Any) -> bool:
    return all(c is None or str(c).strip() == "" for c in r)


def _looks_like_data_row(r: List[Any]) -> bool:
    """A header row carries text labels; a DATA row carries values. We treat the first
    row as DATA (i.e. the file is HEADERLESS) when any of its cells already normalises to
    a valid mobile number — e.g. a bare single-column list of mobiles with no header."""
    return any(_norm_mobile(c) for c in r)


def _finalize_table(all_rows: List[Any]) -> (List[str], List[List[Any]]):
    """Turn raw spreadsheet/CSV rows into (headers, data_rows):
    - drops fully-empty rows (xlsx often reports hundreds of phantom trailing rows that
      otherwise dilute the mobile-detection score to ~0),
    - auto-detects a HEADERLESS file (first row is already data) and synthesises generic
      column names so a bare list of mobiles is still parsed."""
    rows = [list(r) for r in all_rows if not _row_is_empty(r)]
    if not rows:
        return [], []
    if _looks_like_data_row(rows[0]):
        width = max(len(r) for r in rows)
        headers = [f"col{i + 1}" for i in range(width)]
        return headers, rows
    headers = [str(h) for h in rows[0]]
    return headers, rows[1:]


def _parse_csv(raw: bytes) -> Dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV is empty")
    headers, body = _finalize_table(rows)
    if not headers:
        raise ValueError("CSV is empty")
    return {"columns": headers, "rows": body}


def _parse_xlsx(raw: bytes) -> Dict[str, Any]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not all_rows:
        raise ValueError("Spreadsheet is empty")
    headers, body = _finalize_table(all_rows)
    if not headers:
        raise ValueError("Spreadsheet is empty")
    return {"columns": headers, "rows": body}


def _parse_pdf(raw: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    out = []
    for page in reader.pages[:30]:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(out)


def _process_image(raw: bytes, ext: str) -> Dict[str, str]:
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # bound the longest side to keep payloads sane for the vision model
    maxside = 1600
    if max(img.size) > maxside:
        ratio = maxside / max(img.size)
        img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))
    buf = io.BytesIO()
    fmt = "PNG" if ext == "png" else "JPEG"
    save_kwargs = {} if fmt == "PNG" else {"quality": 85}
    img.save(buf, format=fmt, **save_kwargs)
    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    return {"image_base64": base64.b64encode(buf.getvalue()).decode(), "mime": mime}


async def ingest(raw: bytes, filename: str, user: Dict[str, Any],
                 session_id: Optional[str]) -> Dict[str, Any]:
    ext = _ext(filename)
    doc: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "user_id": user.get("id"),
        "session_id": session_id,
        "filename": filename,
        "size": len(raw),
        "created_at": _now_iso(),
    }

    if ext in IMAGE_EXT:
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Image too large (max 8 MB)")
        img = _process_image(raw, "png" if ext == "png" else "jpg")
        doc.update({"kind": "image", "mime": img["mime"], "image_base64": img["image_base64"]})
        summary = {"id": doc["id"], "kind": "image", "filename": filename}

    elif ext in {"csv", "xlsx", "xls"}:
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("Report too large (max 6 MB)")
        parsed = _parse_csv(raw) if ext == "csv" else _parse_xlsx(raw)
        headers, rows = parsed["columns"], parsed["rows"]
        mobiles = _detect_mobiles(headers, rows)
        mobile_points, dup_mobiles = _detect_points_pairs(headers, rows)
        points_total = sum(int(p["points"]) for p in mobile_points)
        preview = [dict(zip(headers, [str(c) for c in r])) for r in rows[:30]]
        full_rows = [dict(zip(headers, [str(c) for c in r])) for r in rows[:DATASET_ROW_CAP]]
        doc.update({"kind": "report", "report_type": ext, "columns": headers,
                    "row_count": len(rows), "preview": preview,
                    "rows": full_rows, "rows_truncated": len(rows) > DATASET_ROW_CAP,
                    "mobiles": mobiles, "mobile_points": mobile_points,
                    "points_total": points_total, "dup_mobiles": dup_mobiles})
        summary = {"id": doc["id"], "kind": "report", "filename": filename,
                   "columns": headers, "row_count": len(rows),
                   "mobiles_detected": len(mobiles),
                   "points_rows_detected": len(mobile_points),
                   "points_total": points_total}

    elif ext == "pdf":
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("PDF too large (max 6 MB)")
        text = _parse_pdf(raw)
        mobiles = list(dict.fromkeys(
            m for m in (_norm_mobile(x) for x in _MOBILE_RE.findall(text)) if m))
        doc.update({"kind": "report", "report_type": "pdf",
                    "extracted_text": text[:20000], "row_count": 0, "mobiles": mobiles})
        summary = {"id": doc["id"], "kind": "report", "filename": filename,
                   "report_type": "pdf", "mobiles_detected": len(mobiles),
                   "text_chars": len(text)}

    else:
        raise ValueError(f"Unsupported file type '.{ext}'. Allowed: images (png/jpg/webp), csv, xlsx, pdf.")

    await mb_attachments_col.insert_one(doc)
    return summary


async def load_for_chat(attachment_ids: List[str], user: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not attachment_ids:
        return []
    return await mb_attachments_col.find(
        {"id": {"$in": attachment_ids}, "user_id": user.get("id")}, {"_id": 0}
    ).to_list(20)


async def bind_session(attachment_ids: List[str], user: Dict[str, Any], session_id: str) -> None:
    """Bind freshly-used attachments to the chat session so later turns can find them."""
    if attachment_ids and session_id:
        await mb_attachments_col.update_many(
            {"id": {"$in": attachment_ids}, "user_id": user.get("id")},
            {"$set": {"session_id": session_id}})


async def latest_session_report(session_id: Optional[str], user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    return await mb_attachments_col.find_one(
        {"session_id": session_id, "user_id": user.get("id"), "kind": "report"},
        {"_id": 0}, sort=[("created_at", -1)])


def light_report_context(att: Dict[str, Any]) -> str:
    """A small reminder (just the id + shape) so the attachment stays referenceable
    across turns (e.g. preview -> confirm) without resending the whole preview."""
    mp = att.get("mobile_points") or []
    pts_hint = (f" It has a PER-ROW points column ({len(mp)} rows, {att.get('points_total')} points total) — "
                f"to credit each mobile its own amount call credit_points_from_file with attachment_id='{att['id']}'."
                if mp else "")
    return (f"[An uploaded report is still active for this conversation: '{att.get('filename')}' "
            f"(attachment_id={att['id']}), {len(att.get('mobiles') or [])} mobiles detected.{pts_hint} "
            f"For a bulk action with the SAME value for all rows, call apply_to_uploaded_report with attachment_id='{att['id']}'.]")


def build_context_block(att: Dict[str, Any]) -> str:
    """Text context injected for a REPORT attachment (images go in as vision)."""
    import json as _json
    if att.get("kind") != "report":
        return ""
    head = f"[Attached report: '{att.get('filename')}' (id={att['id']})]"
    if att.get("report_type") == "pdf":
        return (f"{head} PDF text extracted ({len(att.get('extracted_text', ''))} chars); "
                f"{len(att.get('mobiles') or [])} mobile numbers detected.\n"
                f"--- TEXT START ---\n{(att.get('extracted_text') or '')[:8000]}\n--- TEXT END ---")
    cols = att.get("columns") or []
    mp = att.get("mobile_points") or []
    if mp:
        # PER-ROW points file: deliberately DO NOT dump the rows here. If the model can see the
        # data it tends to fabricate a fake "credited" summary instead of calling the tool. With
        # no rows in context, the ONLY way to act is the tool (which resolves customers + balances).
        return (f"{head} {att.get('row_count')} rows, columns: {cols}. This file has a PER-ROW points "
                f"column: {len(mp)} (mobile -> points) rows, {att.get('points_total')} points total"
                + (f", {att.get('dup_mobiles')} duplicate mobiles summed" if att.get('dup_mobiles') else "")
                + f". The per-row amounts are NOT shown here — to credit each mobile ITS OWN amount you MUST "
                  f"call credit_points_from_file with attachment_id='{att['id']}' (confirm=false to preview "
                  f"first). Do NOT claim anything was credited until that tool returns. (Use "
                  f"apply_to_uploaded_report only if the user wants the SAME amount for everyone.)")
    return (f"{head} {att.get('row_count')} rows, columns: {cols}. "
            f"{len(att.get('mobiles') or [])} mobile numbers detected. "
            f"For a bulk action with the SAME value on every customer, call apply_to_uploaded_report with attachment_id='{att['id']}'.\n"
            f"First rows (preview):\n{_json.dumps(att.get('preview') or [], default=str)[:9000]}")
