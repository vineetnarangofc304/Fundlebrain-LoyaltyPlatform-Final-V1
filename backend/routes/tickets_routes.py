"""Support tickets."""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from database import tickets_col
from auth import get_current_user, log_audit
from models import TicketCreate
import uuid

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("")
async def list_tickets(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    fil = {}
    if status:
        fil["status"] = status
    return await tickets_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)


@router.post("")
async def create_ticket(payload: TicketCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = uuid.uuid4().hex
    doc["status"] = "open"
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = doc["created_at"]
    doc["created_by"] = user["id"]
    doc["notes"] = []
    await tickets_col.insert_one(doc)
    await log_audit(user, "create_ticket", "ticket", doc["id"])
    doc.pop("_id", None)
    return doc


@router.patch("/{ticket_id}")
async def update_ticket(ticket_id: str, updates: dict, user: dict = Depends(get_current_user)):
    t = await tickets_col.find_one({"id": ticket_id})
    if not t:
        raise HTTPException(404, "Not found")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    if updates.get("status") == "resolved":
        updates["resolved_at"] = updates["updated_at"]
    await tickets_col.update_one({"id": ticket_id}, {"$set": updates})
    await log_audit(user, "update_ticket", "ticket", ticket_id, updates)
    return await tickets_col.find_one({"id": ticket_id}, {"_id": 0})


@router.post("/{ticket_id}/notes")
async def add_note(ticket_id: str, body: dict, user: dict = Depends(get_current_user)):
    note = {
        "id": uuid.uuid4().hex,
        "content": body.get("content", ""),
        "author_id": user["id"],
        "author_email": user["email"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await tickets_col.update_one({"id": ticket_id}, {"$push": {"notes": note}, "$set": {"updated_at": note["created_at"]}})
    return note
