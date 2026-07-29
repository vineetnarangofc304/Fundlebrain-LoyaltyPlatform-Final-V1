import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Play, Pause, Volume2, VolumeX, RotateCcw, Share2, Loader2, Check,
  Sparkles, Cpu, ShieldCheck, ArrowRight, Upload, Brain, Zap, AlertTriangle,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { SCENES } from "./watchScenes";
import "./watch.css";

const API = process.env.REACT_APP_BACKEND_URL;
const FABRIC = "https://images.pexels.com/photos/30263578/pexels-photo-30263578.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";
const TOOLTIP = { background: "#0F172A", border: "1px solid rgba(255,255,255,.12)", borderRadius: 8, color: "#F9F8F6", fontSize: 12 };

/* ── typography-level reveals ───────────────────────────── */
function Typewriter({ text, speed = 16 }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
    let i = 0;
    const id = setInterval(() => { i += 1; setN(i); if (i >= text.length) clearInterval(id); }, speed);
    return () => clearInterval(id);
  }, [text, speed]);
  return <span>{text.slice(0, n)}{n < text.length && <span className="watch-caret">▍</span>}</span>;
}

function WordStream({ text, className }) {
  const words = text.split(" ");
  return (
    <motion.p className={className} initial="hidden" animate="show"
      variants={{ show: { transition: { staggerChildren: 0.028 } } }}>
      {words.map((w, i) => (
        <motion.span key={i} variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0 } }}
          style={{ display: "inline-block", marginRight: "0.28em" }}>{w}</motion.span>
      ))}
    </motion.p>
  );
}

/* ── chat beat renderers ────────────────────────────────── */
function UserBubble({ beat }) {
  return (
    <div className="bg-[#F9F8F6] text-[#0A0A0A] rounded-2xl rounded-tr-sm px-4 py-2.5 font-medium text-[15px] shadow-md">
      {beat.file && (
        <div className="flex items-center gap-2 mb-1.5 text-xs text-[#571326] font-semibold">
          <Upload className="w-3.5 h-3.5" />{beat.file}
        </div>
      )}
      <Typewriter text={beat.text} />
    </div>
  );
}

function AssistantText({ beat }) {
  const warn = beat.tone === "warn";
  return (
    <div className="flex gap-3">
      <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-[#571326]/40 border border-[#C7A76D]/40 flex items-center justify-center">
        {warn ? <AlertTriangle className="w-3.5 h-3.5 text-[#C7A76D]" /> : <Sparkles className="w-3.5 h-3.5 text-[#C7A76D]" />}
      </div>
      <WordStream text={beat.text} className={`text-[15px] leading-relaxed ${warn ? "text-[#F4D9A6]" : "text-[#F9F8F6]"}`} />
    </div>
  );
}

function ToolPill({ beat }) {
  const [done, setDone] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDone(true), 1300); return () => clearTimeout(t); }, []);
  return (
    <motion.div layout className={`watch-pill ${done ? "done" : "running"}`} data-testid="tool-pill-status" data-status={done ? "done" : "running"}>
      {done ? <Check className="w-3.5 h-3.5" /> : <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      <span>{beat.label}</span>
      {done && beat.result && <span className="watch-pill-result">{beat.result}</span>}
    </motion.div>
  );
}

function Insight({ beat }) {
  return (
    <div className="bg-[#C7A76D]/10 border-l-2 border-[#C7A76D] rounded-r-lg p-4 pl-5">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-[#C7A76D] font-semibold mb-1.5">
        <Brain className="w-3.5 h-3.5" /> Insight
      </div>
      <WordStream text={beat.text} className="text-[14px] leading-relaxed text-[#F9F8F6]" />
    </div>
  );
}

function Kpis({ beat }) {
  return (
    <div className="grid grid-cols-3 gap-3 w-full">
      {beat.items.map((it, i) => (
        <motion.div key={i} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: i * 0.12, type: "spring", stiffness: 200, damping: 18 }}
          className="bg-[#0F172A]/60 border border-white/10 rounded-xl p-4">
          <div className="text-[10px] uppercase tracking-[0.15em] text-[#94A3B8] mb-1.5">{it.label}</div>
          <div className="watch-display text-3xl text-[#C7A76D] font-medium">{it.value}</div>
        </motion.div>
      ))}
    </div>
  );
}

function ChartBeat({ beat }) {
  return (
    <div className="w-full h-56 mt-1 bg-[#0F172A]/40 border border-white/10 rounded-xl p-3">
      <ResponsiveContainer width="100%" height="100%">
        {beat.kind === "bar" ? (
          <BarChart data={beat.data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" vertical={false} />
            <XAxis dataKey={beat.xKey} tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(199,167,109,.08)" }} />
            {beat.series.map((s) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[3, 3, 0, 0]} />)}
          </BarChart>
        ) : (
          <LineChart data={beat.data} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" vertical={false} />
            <XAxis dataKey={beat.xKey} tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={TOOLTIP} />
            {beat.series.map((s) => <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2.5} dot={{ r: 3, fill: s.color }} />)}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function TableBeat({ beat }) {
  return (
    <div className="w-full rounded-xl border border-white/10 overflow-hidden bg-[#0F172A]/40">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[#94A3B8] text-[11px] uppercase tracking-wider">
            {beat.columns.map((c, i) => <th key={i} className={`px-4 py-2.5 font-medium ${i === 0 ? "text-left" : "text-right"}`}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {beat.rows.map((r, ri) => (
            <motion.tr key={ri} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: ri * 0.1 }} className="border-t border-white/5">
              {r.map((cell, ci) => (
                <td key={ci} className={`px-4 py-2.5 ${ci === 0 ? "text-left font-mono text-[#F9F8F6]" : "text-right font-semibold " + (ci === beat.columns.length - 1 ? "text-[#C7A76D]" : "text-[#94A3B8]")}`}>{cell}</td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfirmBlock({ beat }) {
  const [stage, setStage] = useState("preview");
  useEffect(() => {
    const t1 = setTimeout(() => setStage("confirming"), 1900);
    const t2 = setTimeout(() => setStage("executed"), 3100);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);
  const warn = beat.tone === "warn";
  return (
    <div className={`w-full rounded-xl border ${warn ? "border-[#C7A76D]/40" : "border-white/10"} bg-[#0F172A]/60 overflow-hidden`}>
      <div className="px-4 py-2.5 border-b border-white/10 flex items-center gap-2 text-sm font-semibold">
        {warn ? <AlertTriangle className="w-4 h-4 text-[#C7A76D]" /> : <Zap className="w-4 h-4 text-[#C7A76D]" />} {beat.title}
      </div>
      <div className="px-4 py-3 flex flex-col gap-2">
        {beat.rows.map((r, i) => (
          <div key={i} className="flex items-center justify-between text-sm gap-4">
            <span className="text-[#94A3B8] shrink-0">{r[0]}</span>
            <span className="font-semibold text-[#F9F8F6] text-right">{r[1]}</span>
          </div>
        ))}
      </div>
      <div className="px-4 py-3 border-t border-white/10">
        <AnimatePresence mode="wait">
          {stage !== "executed" ? (
            <motion.div key="btn" exit={{ opacity: 0 }} className={`inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold ${stage === "confirming" ? "bg-[#C7A76D]/70 text-[#0A0A0A]" : "bg-[#C7A76D] text-[#0A0A0A]"}`}>
              {stage === "confirming" ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
              {stage === "confirming" ? "Applying…" : beat.confirmLabel}
            </motion.div>
          ) : (
            <motion.div key="done" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-2 text-sm text-emerald-300 font-semibold">
              <span className="w-6 h-6 rounded-full bg-emerald-400/20 flex items-center justify-center"><Check className="w-4 h-4" /></span>
              {beat.executed}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function ProgressBeat({ beat }) {
  const [p, setP] = useState(0);
  useEffect(() => {
    let raf; const t0 = performance.now(); const dur = 2600;
    const tick = (now) => { const x = Math.min(1, (now - t0) / dur); setP(x); if (x < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  const sent = Math.round(p * beat.total);
  return (
    <div className="w-full rounded-xl border border-white/10 bg-[#0F172A]/50 p-4">
      <div className="flex items-center justify-between text-sm mb-2">
        <span className="text-[#94A3B8]">{beat.label}</span>
        <span className="font-semibold text-[#C7A76D]">{sent.toLocaleString("en-IN")} / {beat.total.toLocaleString("en-IN")}</span>
      </div>
      <div className="h-2 rounded-full bg-[#0A0A0A] overflow-hidden">
        <div className="h-full bg-[#C7A76D]" style={{ width: `${p * 100}%`, transition: "width .1s linear" }} />
      </div>
    </div>
  );
}

function Beat({ beat }) {
  switch (beat.k) {
    case "user": return <UserBubble beat={beat} />;
    case "assistant": return <AssistantText beat={beat} />;
    case "tool": return <ToolPill beat={beat} />;
    case "insight": return <Insight beat={beat} />;
    case "kpis": return <Kpis beat={beat} />;
    case "chart": return <ChartBeat beat={beat} />;
    case "table": return <TableBeat beat={beat} />;
    case "confirm": return <ConfirmBlock beat={beat} />;
    case "progress": return <ProgressBeat beat={beat} />;
    default: return null;
  }
}

function BrainChat({ scene, shown }) {
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [shown]);
  const isMaster = scene.brain === "master";
  const beats = scene.beats.slice(0, shown);
  return (
    <div className="w-full max-w-3xl mx-auto" data-testid="chat-ui-container">
      <div className="watch-chat rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            {isMaster ? <Cpu className="w-4 h-4 text-[#C7A76D]" /> : <Sparkles className="w-4 h-4 text-[#C7A76D]" />}
            <span className="text-sm font-semibold tracking-wide">{isMaster ? "Master Brain" : "Fundle Brain"}</span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-[#94A3B8]">
            <ShieldCheck className="w-3.5 h-3.5 text-[#C7A76D]" /> Private · your data
          </div>
        </div>
        <div className="watch-scroll px-5 md:px-6 py-5 flex flex-col gap-4 h-[430px] overflow-y-auto" aria-live="polite">
          {beats.map((b, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className={b.k === "user" ? "self-end max-w-[85%]" : "self-start w-full"}>
              <Beat beat={b} />
            </motion.div>
          ))}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}

function TitleScene({ scene, onReplay, onBook }) {
  const isCta = scene.variant === "cta";
  return (
    <div className="text-center px-6 max-w-3xl mx-auto">
      {scene.eyebrow && <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="text-xs uppercase tracking-[0.4em] text-[#C7A76D] mb-5">{scene.eyebrow}</motion.div>}
      {scene.brandLine && <motion.h1 initial={{ opacity: 0, letterSpacing: "0.32em" }} animate={{ opacity: 1, letterSpacing: "0.12em" }} transition={{ duration: 1.1, ease: "easeOut" }} className="watch-display text-6xl md:text-8xl font-light text-[#F9F8F6]">{scene.brandLine}</motion.h1>}
      {scene.title && <motion.h1 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9 }} className="watch-display text-6xl md:text-7xl font-light tracking-tight text-[#F9F8F6]">{scene.title}</motion.h1>}
      {scene.subtitle && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 1 }} className="mt-5 text-xl md:text-2xl watch-display italic text-[#C7A76D]">{scene.subtitle}</motion.p>}
      {scene.tagline && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 }} className="mt-3 text-sm uppercase tracking-[0.25em] text-[#94A3B8]">{scene.tagline}</motion.p>}
      {scene.kicker && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.1 }} className="mt-8 text-xs uppercase tracking-[0.3em] text-[#94A3B8]">{scene.kicker}</motion.p>}
      {isCta && (
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.0 }} className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <button onClick={onBook} data-testid="book-demo-cta" className="watch-cta-btn inline-flex items-center gap-2 rounded-full bg-[#F9F8F6] text-[#0A0A0A] px-7 py-3.5 font-semibold">Book a demo <ArrowRight className="w-4 h-4" /></button>
          <button onClick={onReplay} data-testid="watch-replay" className="watch-cta-btn inline-flex items-center gap-2 rounded-full border border-white/25 text-[#F9F8F6] px-6 py-3.5 font-medium hover:bg-white/5"><RotateCcw className="w-4 h-4" /> Replay</button>
        </motion.div>
      )}
    </div>
  );
}

function Cover({ onPlay, preparing, onShare }) {
  return (
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0" style={{ backgroundImage: `url(${FABRIC})`, backgroundSize: "cover", backgroundPosition: "center", filter: "brightness(.35) saturate(.9)" }} />
      <div className="absolute inset-0 bg-black/70" />
      <div className="watch-vignette" />
      <div className="absolute top-6 right-6 z-20">
        <button onClick={onShare} className="text-[#94A3B8] hover:text-white flex items-center gap-1.5 text-sm" data-testid="watch-share"><Share2 className="w-4 h-4" /> Share</button>
      </div>
      <div className="relative z-10 text-center px-6">
        <div className="text-xs uppercase tracking-[0.4em] text-[#C7A76D] mb-6">Fundle · Product Film</div>
        <h1 className="watch-display text-5xl md:text-7xl font-light text-[#F9F8F6] leading-[1.05]">Two minds behind<br />your loyalty program</h1>
        <p className="mt-6 text-[#94A3B8] text-lg max-w-xl mx-auto">Watch Fundle Brain and Master Brain analyse, decide and execute — in plain English.</p>
        <button onClick={onPlay} disabled={preparing} data-testid="play-reel-button"
          className="watch-cta-btn group mt-12 mx-auto w-28 h-28 rounded-full bg-white/5 border border-white/25 backdrop-blur-xl flex items-center justify-center hover:border-[#C7A76D] disabled:opacity-60">
          {preparing ? <Loader2 className="w-10 h-10 animate-spin text-[#C7A76D]" /> : <Play className="w-10 h-10 text-[#F9F8F6] ml-1.5 group-hover:text-[#C7A76D]" />}
        </button>
        <div className="mt-6 text-xs uppercase tracking-[0.25em] text-[#94A3B8]">{preparing ? "Preparing the film…" : "Play · about 3 minutes · sound on"}</div>
      </div>
    </div>
  );
}

function PlayerChrome({ idx, total, sceneProgress, paused, muted, onToggle, onMute, onRestart, onSeek }) {
  const overall = (idx + sceneProgress) / total;
  return (
    <div className="absolute bottom-7 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 px-5 py-3 rounded-full bg-[#0A0A0A]/80 backdrop-blur-xl border border-white/10">
      <button onClick={onToggle} data-testid="watch-playpause" className="text-[#F9F8F6] hover:text-[#C7A76D]">{paused ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}</button>
      <div className="relative h-1.5 w-56 md:w-80 rounded-full bg-[#0F172A] cursor-pointer" data-testid="timeline-progress" onClick={onSeek}>
        <div className="absolute inset-y-0 left-0 rounded-full bg-[#C7A76D]" style={{ width: `${overall * 100}%` }} />
        {Array.from({ length: total - 1 }).map((_, i) => (
          <div key={i} className="absolute top-0 h-full w-[2px] bg-black/50" style={{ left: `${((i + 1) / total) * 100}%` }} />
        ))}
      </div>
      <button onClick={onMute} data-testid="watch-mute" className="text-[#F9F8F6] hover:text-[#C7A76D]">{muted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}</button>
      <button onClick={onRestart} data-testid="watch-restart" className="text-[#F9F8F6] hover:text-[#C7A76D]"><RotateCcw className="w-5 h-5" /></button>
    </div>
  );
}

function CaptionBand({ text }) {
  if (!text) return null;
  return (
    <div className="absolute bottom-24 left-0 right-0 z-40 flex justify-center px-6 pointer-events-none">
      <AnimatePresence mode="wait">
        <motion.div key={text} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }}
          className="bg-black/60 backdrop-blur-md px-6 py-2.5 rounded-lg max-w-3xl text-center" data-testid="caption-text">
          <span className="text-lg md:text-xl font-medium tracking-wide text-[#F9F8F6]">{text}</span>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/* ── main player ────────────────────────────────────────── */
export default function Watch() {
  const navigate = useNavigate();
  const REC = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("rec") === "1";
  const [phase, setPhase] = useState("cover");   // cover | loading | playing | done
  const [idx, setIdx] = useState(0);
  const [progress, setProgress] = useState(0);
  const [paused, setPaused] = useState(false);
  const [muted, setMuted] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [narration, setNarration] = useState({});

  const audioRef = useRef(null);
  const pausedRef = useRef(false);
  const narrationRef = useRef({});

  useEffect(() => { pausedRef.current = paused; }, [paused]);
  useEffect(() => { narrationRef.current = narration; }, [narration]);
  useEffect(() => { if (audioRef.current) audioRef.current.muted = muted; }, [muted]);

  useEffect(() => {
    fetch(`${API}/api/watch/script`).then((r) => r.json()).then((d) => setNarration(d.narration || {})).catch(() => {});
  }, []);

  const estimateDur = (text) => {
    const words = (text || "").split(/\s+/).filter(Boolean).length;
    return Math.max(4, words * 0.4 + 1.2);
  };

  const goNext = useCallback(() => {
    setIdx((prev) => {
      if (prev + 1 >= SCENES.length) { setPhase("done"); return prev; }
      return prev + 1;
    });
  }, []);

  // scene clock — audio is the master clock, with a rAF fallback if audio can't load
  useEffect(() => {
    if (phase !== "playing") return undefined;
    const scene = SCENES[idx];
    let cancelled = false;
    setProgress(0);

    const nxt = SCENES[idx + 1];
    if (nxt) { try { fetch(`${API}/api/watch/tts/${nxt.id}`).catch(() => {}); } catch (e) { /* noop */ } }

    const a = audioRef.current;
    const forcedDur = (REC && typeof window !== "undefined" && Array.isArray(window.__REC_DUR__)) ? window.__REC_DUR__[idx] : null;
    const estDur = forcedDur != null ? forcedDur : estimateDur(narrationRef.current[scene.id]);
    let usingFallback = false;
    let raf; let last = 0; let acc = 0;

    const finish = () => { if (!cancelled) goNext(); };
    const runFallback = () => {
      usingFallback = true;
      const step = (now) => {
        if (cancelled) return;
        if (last === 0) last = now;
        if (!pausedRef.current) acc += now - last;
        last = now;
        const p = Math.min(1, acc / (estDur * 1000));
        setProgress(p);
        if (p >= 1) { finish(); return; }
        raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    };

    const onTime = () => { if (a && a.duration && !usingFallback) setProgress(Math.min(1, a.currentTime / a.duration)); };
    const onEnd = () => { if (!usingFallback) finish(); };
    const cleanupAudio = () => { if (a) { a.removeEventListener("timeupdate", onTime); a.removeEventListener("ended", onEnd); a.removeEventListener("error", onErr); } };
    function onErr() { if (!usingFallback) { cleanupAudio(); runFallback(); } }

    if (a && !REC) {
      a.pause();
      a.muted = muted;
      a.src = `${API}/api/watch/tts/${scene.id}`;
      try { a.currentTime = 0; } catch (e) { /* noop */ }
      a.addEventListener("timeupdate", onTime);
      a.addEventListener("ended", onEnd);
      a.addEventListener("error", onErr);
      a.play().catch(() => { cleanupAudio(); runFallback(); });
    } else {
      runFallback();
    }

    return () => {
      cancelled = true;
      cleanupAudio();
      if (raf) cancelAnimationFrame(raf);
      if (a) a.pause();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, idx, nonce, goNext]);

  const start = async () => {
    setPhase("loading");
    try { await fetch(`${API}/api/watch/tts/${SCENES[0].id}`); } catch (e) { /* noop */ }
    setPaused(false); setNonce((n) => n + 1); setIdx(0); setPhase("playing");
  };

  const gotoScene = (i) => { setPaused(false); setNonce((n) => n + 1); setIdx(i); setPhase("playing"); };
  const restart = () => gotoScene(0);

  // Recording harness (only when ?rec=1): expose start + a done flag so an offline
  // renderer can drive the reel deterministically. No effect for normal visitors.
  useEffect(() => {
    if (!REC || typeof window === "undefined") return;
    window.__REC__ = true;
    window.__REC_START__ = () => { setMuted(true); start(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [REC]);
  useEffect(() => {
    if (REC && typeof window !== "undefined" && phase === "done") window.__REC_DONE__ = true;
  }, [REC, phase]);

  const togglePause = () => {
    setPaused((p) => {
      const np = !p;
      const a = audioRef.current;
      if (a && a.src) { if (np) a.pause(); else a.play().catch(() => {}); }
      return np;
    });
  };

  const onSeek = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    gotoScene(Math.min(SCENES.length - 1, Math.floor(frac * SCENES.length)));
  };

  const share = () => {
    try { navigator.clipboard.writeText(window.location.href); } catch (e) { /* noop */ }
    toast.success("Link copied — share it with anyone.");
  };
  const book = () => navigate("/contact");

  const scene = SCENES[idx];
  const nBeats = scene.kind === "chat" ? scene.beats.length : 0;
  const shown = nBeats ? Math.min(nBeats, Math.floor(progress * nBeats) + 1) : 0;

  const capText = useMemo(() => {
    const full = narration[scene.id] || "";
    const sentences = full.match(/[^.!?]+[.!?]+/g) || (full ? [full] : []);
    if (!sentences.length) return "";
    const i = Math.min(sentences.length - 1, Math.floor(progress * sentences.length));
    return sentences[i].trim();
  }, [narration, scene.id, progress]);

  if (phase === "cover" || phase === "loading") {
    return (
      <div className="watch-root watch-grain min-h-screen">
        <Cover onPlay={start} preparing={phase === "loading"} onShare={share} />
      </div>
    );
  }

  return (
    <div className="watch-root watch-grain relative min-h-screen h-screen overflow-hidden">
      <div className="absolute inset-0" style={{ backgroundImage: `url(${FABRIC})`, backgroundSize: "cover", backgroundPosition: "center", filter: "brightness(.26) saturate(.9)" }} />
      <div className="absolute inset-0 bg-black/70" />
      <div className="watch-vignette" />
      <audio ref={audioRef} preload="auto" />

      <div className="absolute top-6 right-6 z-50">
        {!REC && <button onClick={share} className="text-[#94A3B8] hover:text-white flex items-center gap-1.5 text-sm" data-testid="watch-share"><Share2 className="w-4 h-4" /> Share</button>}
      </div>

      <div className="relative z-10 min-h-screen flex items-center justify-center px-4">
        <AnimatePresence mode="wait">
          <motion.div key={`${idx}-${nonce}-${phase}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.6 }} className="w-full">
            {scene.kind === "title"
              ? <TitleScene scene={scene} onReplay={restart} onBook={book} />
              : <BrainChat scene={scene} shown={shown} />}
          </motion.div>
        </AnimatePresence>
      </div>

      {scene.kind === "chat" && <CaptionBand text={capText} />}
      {phase === "playing" && !REC && (
        <PlayerChrome idx={idx} total={SCENES.length} sceneProgress={progress} paused={paused} muted={muted}
          onToggle={togglePause} onMute={() => setMuted((m) => !m)} onRestart={restart} onSeek={onSeek} />
      )}
    </div>
  );
}
