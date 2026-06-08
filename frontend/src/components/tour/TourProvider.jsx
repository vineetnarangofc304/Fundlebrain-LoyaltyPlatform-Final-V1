import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Play, Pause, SkipForward, SkipBack, X, Volume2, VolumeX, Sparkles, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DEFAULT_VOICE } from "@/lib/demoScript";

const TourCtx = createContext(null);
export const useTour = () => useContext(TourCtx);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rectOf = (el) => {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
};

async function waitForSelector(selector, timeout = 6000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const el = document.querySelector(selector);
    if (el && el.getBoundingClientRect().width > 0) return el;
    await sleep(120);
  }
  return null;
}

export function TourProvider({ children }) {
  const navigate = useNavigate();
  const { applySession } = useAuth();

  const [active, setActive] = useState(false);
  const [steps, setSteps] = useState([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [muted, setMuted] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [navRect, setNavRect] = useState(null);
  const [starting, setStarting] = useState(false);

  const audioRef = useRef(null);
  const audioCache = useRef(new Map());
  const fallbackTimer = useRef(null);
  const trackEl = useRef(null);
  const playingRef = useRef(true);
  const mutedRef = useRef(false);
  const stepsRef = useRef([]);
  const indexRef = useRef(0);
  const activeRef = useRef(false);

  useEffect(() => { playingRef.current = playing; }, [playing]);
  useEffect(() => { mutedRef.current = muted; }, [muted]);
  useEffect(() => { stepsRef.current = steps; }, [steps]);
  useEffect(() => { indexRef.current = index; }, [index]);
  useEffect(() => { activeRef.current = active; }, [active]);

  const ensureAudio = () => {
    if (audioRef.current == null) {
      audioRef.current = typeof Audio !== "undefined" ? new Audio() : null;
    }
    return audioRef.current;
  };

  const clearFallback = () => { if (fallbackTimer.current) { clearTimeout(fallbackTimer.current); fallbackTimer.current = null; } };
  const stopAudio = useCallback(() => {
    clearFallback();
    const a = ensureAudio();
    if (a) { try { a.pause(); a.onended = null; a.src = ""; } catch (e) { /* noop */ } }
    setSpeaking(false);
  }, []);

  const goNext = useCallback(() => {
    const last = stepsRef.current.length - 1;
    if (indexRef.current >= last) { finishTour(); return; }
    setIndex((i) => Math.min(i + 1, last));
  }, []);

  const goPrev = useCallback(() => {
    setIndex((i) => Math.max(i - 1, 0));
  }, []);

  const finishTour = useCallback(() => {
    stopAudio();
    setActive(false);
    setNavRect(null);
    trackEl.current = null;
    navigate("/demo");
  }, [navigate, stopAudio]);

  const stopTour = finishTour;

  const scheduleFallback = useCallback((text) => {
    clearFallback();
    const words = (text || "").split(/\s+/).filter(Boolean).length;
    const ms = Math.max(7000, Math.round(words * 380));
    fallbackTimer.current = setTimeout(() => { if (playingRef.current && activeRef.current) goNext(); }, ms);
  }, [goNext]);

  const speak = useCallback(async (text) => {
    if (mutedRef.current) { scheduleFallback(text); return; }
    setAudioLoading(true);
    try {
      let url = audioCache.current.get(text);
      if (!url) {
        const resp = await api.post("/demo/tts", { text, voice: DEFAULT_VOICE }, { responseType: "blob" });
        url = URL.createObjectURL(resp.data);
        audioCache.current.set(text, url);
      }
      const a = ensureAudio();
      a.src = url;
      a.onended = () => { setSpeaking(false); if (playingRef.current && activeRef.current) goNext(); };
      a.onerror = () => { setSpeaking(false); scheduleFallback(text); };
      await a.play();
      setSpeaking(true);
    } catch (e) {
      scheduleFallback(text);
    } finally {
      setAudioLoading(false);
    }
  }, [goNext, scheduleFallback]);

  // Drive each step: navigate → spotlight nav → narrate
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const step = stepsRef.current[index];
    if (!step) return;
    stopAudio();
    setNavRect(null);
    trackEl.current = null;
    navigate(step.route);
    (async () => {
      if (step.nav) {
        const el = await waitForSelector(`[data-testid="${step.nav}"]`, 6000);
        if (cancelled) return;
        if (el) {
          try { el.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) { /* noop */ }
          await sleep(350);
          if (cancelled) return;
          trackEl.current = el;
          setNavRect(rectOf(el));
        }
      } else {
        await sleep(600);
      }
      if (cancelled) return;
      if (playingRef.current) speak(step.say);
    })();
    return () => { cancelled = true; };
  }, [active, index]);

  // Keep the spotlight ring glued to its element on scroll / resize
  useEffect(() => {
    if (!active) return;
    const update = () => {
      const el = trackEl.current;
      if (el && document.body.contains(el)) setNavRect(rectOf(el));
    };
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [active]);

  const togglePlay = useCallback(() => {
    const a = ensureAudio();
    if (playingRef.current) {
      setPlaying(false);
      clearFallback();
      if (a) { try { a.pause(); } catch (e) { /* noop */ } }
    } else {
      setPlaying(true);
      const step = stepsRef.current[indexRef.current];
      if (a && a.src && !mutedRef.current && a.paused && a.currentTime > 0 && !a.ended) {
        a.play().catch(() => scheduleFallback(step?.say));
      } else if (step) {
        speak(step.say);
      }
    }
  }, [speak, scheduleFallback]);

  const startTour = useCallback(async (tourSteps) => {
    if (!Array.isArray(tourSteps) || tourSteps.length === 0) return;
    setStarting(true);
    try {
      if (!localStorage.getItem("kazo_token")) {
        const r = await api.post("/demo/session");
        applySession(r.data.token, r.data.user, "crm");
        await sleep(150);
      }
      setSteps(tourSteps);
      setIndex(0);
      setMuted(false);
      setPlaying(true);
      setActive(true);
    } catch (e) {
      // surface minimal — provider stays inactive
      console.error("Could not start demo tour", e);
    } finally {
      setStarting(false);
    }
  }, [applySession]);

  // Cleanup object URLs on unmount
  useEffect(() => () => {
    audioCache.current.forEach((u) => { try { URL.revokeObjectURL(u); } catch (e) { /* noop */ } });
  }, []);

  const step = steps[index];
  const total = steps.length;
  const progress = total ? ((index + 1) / total) * 100 : 0;

  return (
    <TourCtx.Provider value={{ startTour, stopTour, active, starting }}>
      {children}
      {active && step && (
        <TourOverlay
          step={step}
          index={index}
          total={total}
          progress={progress}
          navRect={navRect}
          playing={playing}
          muted={muted}
          audioLoading={audioLoading}
          speaking={speaking}
          onPlayPause={togglePlay}
          onNext={goNext}
          onPrev={goPrev}
          onExit={finishTour}
          onToggleMute={() => {
            setMuted((m) => {
              const next = !m;
              if (next) { const a = ensureAudio(); if (a) { try { a.pause(); } catch (e) { /* noop */ } } setSpeaking(false); }
              else if (playingRef.current && step) { speak(step.say); }
              return next;
            });
          }}
        />
      )}
    </TourCtx.Provider>
  );
}

function TourOverlay({ step, index, total, progress, navRect, playing, muted, audioLoading, speaking,
  onPlayPause, onNext, onPrev, onExit, onToggleMute }) {
  return (
    <div className="fixed inset-0 z-[9997]" data-testid="demo-tour-overlay">
      {/* click-blocker + light scrim (keeps the live screen clearly visible) */}
      <div className="absolute inset-0" style={{ background: "rgba(10,8,12,0.30)", backdropFilter: "blur(0.5px)" }} />

      {/* spotlight ring around the highlighted nav item */}
      {navRect && (
        <div
          className="absolute pointer-events-none rounded-md tour-ring"
          style={{
            top: navRect.top - 6, left: navRect.left - 6,
            width: navRect.width + 12, height: navRect.height + 12,
          }}
        />
      )}

      {/* caption / control card — bottom centre, Fundle-branded */}
      <div
        className="absolute left-1/2 -translate-x-1/2 bottom-6 w-[min(720px,92vw)] z-[9999] rounded-2xl shadow-2xl overflow-hidden"
        style={{ background: "linear-gradient(160deg,#150810 0%, #0A0A0A 60%, #100308 100%)", border: "1px solid rgba(199,167,109,0.35)" }}
        data-testid="demo-caption-card"
      >
        {/* progress bar */}
        <div className="h-1 w-full" style={{ background: "rgba(255,255,255,0.08)" }}>
          <div className="h-full transition-all duration-500" style={{ width: `${progress}%`, background: "linear-gradient(90deg, var(--kazo-champagne), var(--kazo-champagne-light))" }} />
        </div>

        <div className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em]" style={{ color: "var(--kazo-champagne)" }}>
                <Sparkles className="w-3 h-3" /> Powered by Fundle · Guided Demo
              </div>
              <h3 className="font-display text-white text-xl sm:text-2xl mt-1 leading-tight truncate">{step.title}</h3>
            </div>
            <button onClick={onExit} data-testid="demo-exit-btn"
              className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>

          <p className="text-white/80 text-sm sm:text-[15px] leading-relaxed mt-3" data-testid="demo-caption-text">
            {step.say}
          </p>

          <div className="flex items-center justify-between gap-3 mt-5">
            <div className="flex items-center gap-2 text-xs text-white/50 tabular-nums">
              <span data-testid="demo-step-indicator">{index + 1} / {total}</span>
              {audioLoading ? (
                <span className="flex items-center gap-1 text-white/60"><Loader2 className="w-3.5 h-3.5 animate-spin" /> loading voice…</span>
              ) : speaking ? (
                <span className="flex items-center gap-1" style={{ color: "var(--kazo-champagne)" }}>
                  <span className="tour-eq"><i /><i /><i /></span> narrating
                </span>
              ) : null}
            </div>

            <div className="flex items-center gap-2">
              <button onClick={onToggleMute} data-testid="demo-mute-btn" title={muted ? "Unmute" : "Mute"}
                className="w-9 h-9 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors">
                {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
              </button>
              <button onClick={onPrev} disabled={index === 0} data-testid="demo-prev-btn"
                className="w-9 h-9 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-30">
                <SkipBack className="w-4 h-4" />
              </button>
              <button onClick={onPlayPause} data-testid="demo-playpause-btn"
                className="w-11 h-11 rounded-full flex items-center justify-center text-black font-semibold transition-transform hover:scale-105"
                style={{ background: "linear-gradient(135deg, var(--kazo-champagne), var(--kazo-champagne-light))" }}>
                {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </button>
              <button onClick={onNext} data-testid="demo-next-btn"
                className="w-9 h-9 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors">
                <SkipForward className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
