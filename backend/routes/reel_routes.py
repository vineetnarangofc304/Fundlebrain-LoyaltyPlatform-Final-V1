"""Public /reel marketing reels: 3 vertical (9:16) product films in the ElevenLabs
"agents" style — Platform overview, Fundle Brain (analyst) and Master Brain (executor),
positioned as loyalty AI agents trained by fundle.ai.

Narration text is the single source of truth (voices the OpenAI-TTS audio AND the on-screen
captions the frontend fetches). Audio is generated once via OpenAI TTS (male voice "onyx",
Emergent LLM key) and CACHED in Mongo keyed by content hash so repeat plays never regenerate.
The finished .mp4s are rendered offline by scripts/render_reels_mp4.py and served here.
"""
import os
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from database import db

load_dotenv()

logger = logging.getLogger("kazo-fundle.reel")
router = APIRouter(prefix="/reel", tags=["reel"])
_tts_cache = db["demo_tts_cache"]

GEN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated")

TTS_MODEL = "tts-1-hd"    # HD quality — generated once then cached
TTS_VOICE = "onyx"        # deep, confident MALE brand narrator (per user)

# clip -> ordered scene ids (must match the frontend reelScenes.js scene order)
CLIP_ORDER = {
    "platform": ["p_hook", "p_what", "p_fundle", "p_master", "p_scale", "p_close"],
    "fundle": ["f_hook", "f_intro", "f_stores", "f_churn", "f_upload", "f_close"],
    "master": ["m_hook", "m_intro", "m_topup", "m_campaign", "m_safe", "m_close"],
}

CLIP_META = {
    "platform": {"title": "Fundle — The Platform", "subtitle": "Loyalty, run by two AI agents"},
    "fundle": {"title": "Fundle Brain", "subtitle": "Your loyalty analyst"},
    "master": {"title": "Master Brain", "subtitle": "Your loyalty executor"},
}

# scene_id -> narration line (voiceover + captions). Kept ~30-38 words so each scene
# runs ~12-15s and each clip lands in the 60-90s target.
REEL_NARRATION = {
    # ── CLIP 1 · PLATFORM ────────────────────────────────────────────────
    "p_hook": ("Eight hundred thousand shoppers. Over one and a half million bills. Sixty-four stores. "
               "And a loyalty program that used to need a whole team — now running itself, in plain English."),
    "p_what": ("Fundle turns your entire loyalty operation into two AI agents. Trained on your data, working "
               "around the clock, and taking their orders straight from you — in plain English. No agency, "
               "no analysts, no waiting."),
    "p_fundle": ("This is Fundle Brain, your analyst. Ask it anything about your customers, your stores, or your "
                 "points — and in seconds it gives you the answer, the reason behind it, and exactly what to do next."),
    "p_master": ("And this is Master Brain, your executor. Whatever you would wait days on a team to do, it does "
                 "the moment you ask. Every change is previewed first, applied only on your yes, and reversible "
                 "in a single click."),
    "p_scale": ("It plugs straight into your point of sale, your messaging, and your rewards — reconciling millions "
                "of transactions in real time, catching errors before they spread, with no spreadsheets and no engineering."),
    "p_close": ("This is Fundle. Loyalty, run by intelligence — lower cost, higher profit, and fully in your control. "
                "Trained by fundle dot A-I. Ready when you are."),

    # ── CLIP 2 · FUNDLE BRAIN ────────────────────────────────────────────
    "f_hook": ("What if you could just ask your loyalty data anything — in plain English — and it answered you "
               "instantly, like the sharpest analyst you have ever hired?"),
    "f_intro": ("Meet Fundle Brain, your loyalty analyst, trained by fundle dot A-I. It never sleeps, it reads your "
                "live data the moment you ask, and it works only for you — completely privately."),
    "f_stores": ("Which stores are slipping this quarter? Just ask. Fundle Brain reads sixty-four stores of live sales "
                 "and tells you not only what happened, but why it happened — and the exact move to turn it around."),
    "f_churn": ("Who is about to leave you? It scores every customer, finds the ones sliding toward churn, values what "
                "they are worth in rupees, and hands you the win-back play — before they are gone for good."),
    "f_upload": ("Have a spreadsheet? Just drop it in. Fundle Brain analyses your own files instantly and privately. "
                 "Your data always stays yours — and the more you use it, the sharper its answers get."),
    "f_close": ("That is Fundle Brain — your analyst, on demand, at any hour of the day. Trained by fundle dot A-I."),

    # ── CLIP 3 · MASTER BRAIN ────────────────────────────────────────────
    "m_hook": ("What if every change to your loyalty program — every top-up, every campaign, every fix — was just "
               "one plain-English sentence away?"),
    "m_intro": ("Meet Master Brain, your loyalty executor, trained by fundle dot A-I. Say what you want in plain "
                "English, and it is done — safely, transparently, and completely under your control."),
    "m_topup": ("Top up points for the customers who matter most. Master Brain previews the exact impact, waits for "
                "your yes, then applies it to thousands of customers in seconds — and if you change your mind, you "
                "undo it in one click."),
    "m_campaign": ("Win them back with a single line. It builds the audience, drafts the message, and launches the whole "
                   "campaign — texting your lapsed customers automatically, while you watch it go out live, in real time."),
    "m_safe": ("And it never does the same thing twice. Master Brain remembers what has already happened, catches the "
               "duplicate, and applies only the exact fix that is needed — so a mistake can never quietly compound across your data."),
    "m_close": ("That is Master Brain — your executor, on command, whenever you need it. Trained by fundle dot A-I."),
}


def _clip_or_404(clip: str):
    if clip not in CLIP_ORDER:
        raise HTTPException(404, "Unknown reel clip")


@router.get("/clips")
async def reel_clips():
    """Metadata + generated-status for the reel picker page."""
    out = []
    for clip in CLIP_ORDER:
        path = os.path.join(GEN_DIR, f"reel_{clip}.mp4")
        out.append({
            "clip": clip,
            **CLIP_META.get(clip, {}),
            "scenes": len(CLIP_ORDER[clip]),
            "ready": os.path.exists(path),
        })
    return {"voice": TTS_VOICE, "clips": out}


@router.get("/script/{clip}")
async def reel_script(clip: str):
    """Ordered narration for a clip (captions come from the same text that voices the audio)."""
    _clip_or_404(clip)
    order = CLIP_ORDER[clip]
    return {
        "voice": TTS_VOICE, "model": TTS_MODEL, "clip": clip,
        "order": order,
        "narration": {sid: REEL_NARRATION[sid] for sid in order},
    }


@router.get("/film/{clip}.mp4")
async def reel_film(clip: str):
    """Serve a pre-rendered vertical reel (mp4) as a download, if generated."""
    _clip_or_404(clip)
    path = os.path.join(GEN_DIR, f"reel_{clip}.mp4")
    if not os.path.exists(path):
        raise HTTPException(404, "Reel not generated yet")
    return FileResponse(path, media_type="video/mp4", filename=f"fundle_reel_{clip}.mp4")


@router.get("/tts/{clip}/{scene_id}")
async def reel_tts(clip: str, scene_id: str):
    """Return the mp3 narration for a scene. Generated once via OpenAI TTS, then cached in Mongo."""
    _clip_or_404(clip)
    text = REEL_NARRATION.get(scene_id)
    if not text or scene_id not in CLIP_ORDER[clip]:
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
            logger.exception("reel TTS generation failed for %s/%s", clip, scene_id)
            raise HTTPException(502, f"TTS generation failed: {e}")
        await _tts_cache.update_one(
            {"key": key},
            {"$set": {"key": key, "scene_id": scene_id, "clip": clip, "audio": bytes(audio),
                      "model": TTS_MODEL, "voice": TTS_VOICE}},
            upsert=True)
    return Response(content=bytes(audio), media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000"})
