"""Public /watch demo-reel support: server-side narration script + cached OpenAI TTS.

The /watch page is a public, self-running cinematic product demo. Narration text is the
single source of truth here (used both for the voiceover audio AND the on-screen captions
the frontend fetches). Audio is generated once via OpenAI TTS and CACHED in MongoDB keyed
by a content hash, so repeated plays / many public viewers never re-generate (bounded cost).
"""
import os
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Response
from dotenv import load_dotenv

from database import db

load_dotenv()

logger = logging.getLogger("kazo-fundle.watch")
router = APIRouter(prefix="/watch", tags=["watch"])
_tts_cache = db["demo_tts_cache"]

TTS_MODEL = "tts-1-hd"   # HD quality — generated once, then cached, so quality over speed
TTS_VOICE = "onyx"       # deep, authoritative — reads as a confident brand narrator

# scene_id -> narration line. Order/visuals live on the frontend; this is the audio + caption text.
WATCH_NARRATION = {
    "open": ("Meet Fundle — the intelligence behind your loyalty program. Two minds, working for you. "
             "Fundle Brain, that thinks, analyzes and advises. And Master Brain, that executes everything, on its own. "
             "No teams. No agencies. Just your data, and your instructions, in plain English."),
    "act1": ("Act one. Fundle Brain — your private analyst that never sleeps. "
             "Ask anything about your customers, your stores, your points, in your own words."),
    "fb_underperform": ("Which stores are slipping? Just ask. Fundle Brain reads your live data and answers in seconds — "
                        "not only a chart, but what it means, and exactly what to do about it."),
    "fb_churn": ("Who is about to leave you? Fundle Brain finds your at-risk customers, values what they are worth, "
                 "and tells you how to win them back — before they are gone."),
    "fb_diagnose": ("When something drops, it does not just show you the dip — it explains why. "
                    "Fundle Brain traces the root cause across campaigns, stores and seasons, so you are never guessing."),
    "fb_upload": ("Have a spreadsheet? Drop it in. Fundle Brain analyzes your own files instantly and privately. "
                  "Your data stays yours — and the more you use it, the sharper it gets."),
    "act2": ("Act two. Master Brain — the executor. "
             "Everything you would wait on a team to do, done the moment you ask."),
    "mb_topup": ("Top up points for the customers who matter. Master Brain previews the exact impact, waits for your yes, "
                 "then applies it to thousands of customers in seconds — every change audited, every change reversible."),
    "mb_campaign": ("Win them back with one sentence. Master Brain builds the audience, drafts the message, "
                    "and launches the campaign — texting lapsed customers automatically, while you watch it happen live."),
    "mb_reconcile": ("Numbers gone wrong? Master Brain repairs them. It reads the true ledger, shows you the wrong balance "
                     "beside the genuine one, and corrects it — safely, and only once."),
    "mb_rule": ("Change the rules of your program on the fly. A festive double-points weekend? Just say so. "
                "Master Brain updates your earning logic, and it goes live instantly."),
    "mb_error": ("And when something has already been done, it will not do it twice. Master Brain catches the duplicate, "
                 "explains what happened, and applies the exact adjustment needed — protecting your points and your customers."),
    "close": ("This is loyalty, run by intelligence. Lower cost, higher profit, fully in your control. "
              "This is Fundle. Ready when you are."),
}


@router.get("/script")
async def watch_script():
    """Ordered narration lines (captions come from the same text that voices the audio)."""
    return {"voice": TTS_VOICE, "model": TTS_MODEL, "narration": WATCH_NARRATION}


@router.get("/tts/{scene_id}")
async def watch_tts(scene_id: str):
    """Return the mp3 narration for a scene. Generated once via OpenAI TTS, then cached in Mongo."""
    text = WATCH_NARRATION.get(scene_id)
    if not text:
        raise HTTPException(404, "Unknown scene")
    key = hashlib.sha256(f"{TTS_MODEL}|{TTS_VOICE}|{text}".encode("utf-8")).hexdigest()
    doc = await _tts_cache.find_one({"key": key})
    audio = doc.get("audio") if doc else None
    if not audio:
        try:
            from emergentintegrations.llm.openai import OpenAITextToSpeech
            tts = OpenAITextToSpeech(api_key=os.getenv("EMERGENT_LLM_KEY"))
            audio = await tts.generate_speech(text=text, model=TTS_MODEL, voice=TTS_VOICE)
        except Exception as e:  # noqa: BLE001
            logger.exception("watch TTS generation failed for %s", scene_id)
            raise HTTPException(502, f"TTS generation failed: {e}")
        await _tts_cache.update_one(
            {"key": key},
            {"$set": {"key": key, "scene_id": scene_id, "audio": bytes(audio),
                      "model": TTS_MODEL, "voice": TTS_VOICE}},
            upsert=True)
    return Response(content=bytes(audio), media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000"})
