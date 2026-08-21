import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play, Loader2, Check, Sparkles, Cpu, ShieldCheck, ArrowRight, Upload,
  Brain, Zap, AlertTriangle, Download,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { CLIPS, CLIP_META, CLIP_ORDER } from "./reelScenes";
import "./reel.css";

const API = process.env.REACT_APP_BACKEND_URL;
const TOOLTIP = { background: "#0F172A", border: "1px solid rgba(255,255,255,.12)", borderRadius: 8, color: "#F9F8F6", fontSize: 20 };

/* ── beat renderers ─────────────────────────────────────────── */
function ToolPill({ beat }) {
  const [done, setDone] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDone(true), 1300); return () => clearTimeout(t); }, []);
  return (
    <div className={`reel-pill ${done ? "done" : ""}`} data-testid="reel-tool-pill">
      {done ? <Check className="w-6 h-6" /> : <Loader2 className="w-6 h-6 animate-spin" />}
      <span>{beat.label}</span>
      {done && beat.result && <span className="res">{beat.result}</span>}
    </div>
  );
}

function Kpis({ beat }) {
  return (
    <div className="reel-kpis">
      {beat.items.map((it, i) => (
        <motion.div key={i} className="reel-kpi" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.12 }}>
          <div className="k">{it.label}</div>
          <div className="v">{it.value}</div>
        </motion.div>
      ))}
    </div>
  );
}

function ChartBeat({ beat }) {
  return (
    <div className="reel-chartwrap">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={beat.data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" vertical={false} />
          <XAxis dataKey={beat.xKey} tick={{ fill: "#94A3B8", fontSize: 20 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#94A3B8", fontSize: 20 }} axisLine={false} tickLine={false} width={44} />
          <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(199,167,109,.08)" }} />
          {beat.series.map((s) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TableBeat({ beat }) {
  return (
    <div className="reel-tablewrap">
      <table>
        <thead><tr>{beat.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
        <tbody>
          {beat.rows.map((r, ri) => (
            <motion.tr key={ri} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: ri * 0.1 }}>
              {r.map((cell, ci) => <td key={ci}>{cell}</td>)}
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
    const t1 = setTimeout(() => setStage("confirming"), 2200);
    const t2 = setTimeout(() => setStage("executed"), 3600);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);
  const warn = beat.tone === "warn";
  return (
    <div className={`reel-confirm ${warn ? "warn" : ""}`} data-testid="reel-confirm">
      <div className="ttl">{warn ? <AlertTriangle className="w-7 h-7" style={{ color: "#C7A76D" }} /> : <Zap className="w-7 h-7" style={{ color: "#C7A76D" }} />} {beat.title}</div>
      <div className="body">
        {beat.rows.map((r, i) => (
          <div key={i} className="row"><span className="a">{r[0]}</span><span className="b">{r[1]}</span></div>
        ))}
      </div>
      <div className="foot">
        <AnimatePresence mode="wait">
          {stage !== "executed" ? (
            <motion.div key="btn" exit={{ opacity: 0 }} className={`reel-btn ${stage === "confirming" ? "busy" : ""}`}>
              {stage === "confirming" ? <Loader2 className="w-6 h-6 animate-spin" /> : <ArrowRight className="w-6 h-6" />}
              {stage === "confirming" ? "Applying…" : beat.confirmLabel}
            </motion.div>
          ) : (
            <motion.div key="done" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="reel-done">
              <span className="ck"><Check className="w-6 h-6" /></span>{beat.executed}
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
    let raf; const t0 = performance.now(); const dur = 2800;
    const tick = (now) => { const x = Math.min(1, (now - t0) / dur); setP(x); if (x < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, []);
  const sent = Math.round(p * beat.total);
  return (
    <div className="reel-progress">
      <div className="top"><span className="a">{beat.label}</span><span className="b">{sent.toLocaleString("en-IN")} / {beat.total.toLocaleString("en-IN")}</span></div>
      <div className="bar"><i style={{ width: `${p * 100}%` }} /></div>
    </div>
  );
}

function Insight({ beat }) {
  return (
    <div className="reel-insight">
      <div className="lbl"><Brain className="w-5 h-5" /> Insight</div>
      <p>{beat.text}</p>
    </div>
  );
}

function Beat({ beat }) {
  switch (beat.k) {
    case "user":
      return (
        <div className="reel-user">
          {beat.file && <div className="file"><Upload className="w-6 h-6" />{beat.file}</div>}
          {beat.text}
        </div>
      );
    case "assistant":
      return (
        <div className={`reel-assist ${beat.tone === "warn" ? "warn" : ""}`}>
          <div className="av">{beat.tone === "warn" ? <AlertTriangle className="w-6 h-6" style={{ color: "#C7A76D" }} /> : <Sparkles className="w-6 h-6" style={{ color: "#C7A76D" }} />}</div>
          <p>{beat.text}</p>
        </div>
      );
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

/* ── scene renderers ────────────────────────────────────────── */
function HookScene({ scene }) {
  return (
    <div className={`reel-hook ${scene.tone === "statement" ? "statement" : ""}`}>
      {scene.lines.map((l, i) => (
        <motion.div key={i} className={`line ${i === scene.lines.length - 1 ? "accent" : ""}`}
          initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.28, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
          {l}
        </motion.div>
      ))}
      {scene.sub && <motion.div className="sub" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: scene.lines.length * 0.28 + 0.2, duration: 0.7 }}>{scene.sub}</motion.div>}
    </div>
  );
}

function AgentScene({ scene }) {
  return (
    <div className="reel-agent">
      <div className="reel-orb" data-testid="reel-orb"><span className="ring" /><span className="ring r2" /><span className="ring r3" /></div>
      <motion.div className="name" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }}>{scene.name}</motion.div>
      <motion.div className="role" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4, duration: 0.7 }}>{scene.role}</motion.div>
      <motion.div className="tag" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }}>{scene.tagline}</motion.div>
    </div>
  );
}

function StatsScene({ scene }) {
  return (
    <div className="reel-stats">
      <div className="grid">
        {scene.items.map((s, i) => (
          <motion.div key={i} className="stat" initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.18, duration: 0.6 }}>
            <div className="v">{s.value}</div><div className="l">{s.label}</div>
          </motion.div>
        ))}
      </div>
      <div className="reel-pills">
        {scene.pills.map((p, i) => (
          <motion.span key={i} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.6 + i * 0.08 }}>{p}</motion.span>
        ))}
      </div>
    </div>
  );
}

function CtaScene({ scene }) {
  return (
    <div className="reel-cta">
      <motion.div className="mark" initial={{ opacity: 0, letterSpacing: "0.2em" }} animate={{ opacity: 1, letterSpacing: "0.02em" }} transition={{ duration: 1 }}>fund<b>le</b></motion.div>
      <motion.div className="tagline" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>{scene.tagline}</motion.div>
      <motion.div className="sub" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 }}>{scene.sub}</motion.div>
    </div>
  );
}

function ChatScene({ scene, shown }) {
  const isMaster = scene.brain === "master";
  const beats = scene.beats.slice(0, shown);
  return (
    <div className="reel-chat" data-testid="reel-chat">
      <div className="reel-chat-head">
        <div className="who"><span className="dot" />{isMaster ? "Master Brain" : "Fundle Brain"}
          <span className="reel-eq">{[0, 1, 2, 3].map((i) => <i key={i} />)}</span>
        </div>
        <div className="priv"><ShieldCheck className="w-5 h-5 inline mr-1" style={{ color: "#C7A76D" }} /> Private</div>
      </div>
      <div className="reel-scroll">
        {beats.map((b, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            style={{ alignSelf: b.k === "user" ? "flex-end" : "flex-start", width: b.k === "user" ? "auto" : "100%", maxWidth: b.k === "user" ? "82%" : "100%" }}>
            <Beat beat={b} />
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ── cover / picker (non-rec) ───────────────────────────────── */
function Picker({ onPlay }) {
  const [clips, setClips] = useState([]);
  useEffect(() => { fetch(`${API}/api/reel/clips`).then((r) => r.json()).then((d) => setClips(d.clips || [])).catch(() => {}); }, []);
  const meta = (c) => clips.find((x) => x.clip === c) || {};
  return (
    <div className="reel-cover" data-testid="reel-cover">
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "72px 32px 96px" }}>
        <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 40 }}>fund<b style={{ color: "#C7A76D" }}>le</b> <span style={{ color: "#8A8F9C", fontSize: 22, fontWeight: 600 }}>· Reels</span></div>
        <h1 style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 56, fontWeight: 700, marginTop: 20, lineHeight: 1.1 }}>Loyalty, run by two AI agents.</h1>
        <p style={{ color: "#A9AEBA", fontSize: 22, marginTop: 14, maxWidth: 720 }}>Three short films — the platform, and the two agents (Fundle Brain & Master Brain) that analyse and execute your loyalty program. Trained by fundle.ai.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 24, marginTop: 48 }}>
          {CLIP_ORDER.map((c) => (
            <div key={c} style={{ border: "1px solid rgba(255,255,255,.12)", borderRadius: 24, overflow: "hidden", background: "rgba(255,255,255,.03)" }}>
              <div style={{ aspectRatio: "9/16", position: "relative", display: "flex", alignItems: "center", justifyContent: "center",
                background: "radial-gradient(120% 60% at 50% 0%, rgba(199,167,109,.2), transparent 60%), #0B0D12" }}>
                <button onClick={() => onPlay(c)} data-testid={`reel-play-${c}`}
                  style={{ width: 96, height: 96, borderRadius: "50%", background: "rgba(255,255,255,.06)", border: "1px solid rgba(255,255,255,.25)", color: "#F5F4F1", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
                  <Play className="w-9 h-9" style={{ marginLeft: 6 }} />
                </button>
                <div style={{ position: "absolute", top: 18, left: 20, fontSize: 13, letterSpacing: "0.3em", textTransform: "uppercase", color: "#8A8F9C", fontWeight: 600 }}>{CLIP_META[c].label}</div>
              </div>
              <div style={{ padding: "22px 24px" }}>
                <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 26, fontWeight: 700 }}>{CLIP_META[c].title}</div>
                <div style={{ color: "#A9AEBA", fontSize: 17, marginTop: 6 }}>{CLIP_META[c].subtitle}</div>
                <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
                  <button onClick={() => onPlay(c)} className="reel-play-inline" data-testid={`reel-playbtn-${c}`}
                    style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 99, padding: "12px 18px", background: "#C7A76D", color: "#0A0A0A", fontWeight: 700, cursor: "pointer", border: "none", fontSize: 16 }}>
                    <Play className="w-4 h-4" /> Play
                  </button>
                  <a href={meta(c).ready ? `${API}/api/reel/film/${c}.mp4` : undefined} data-testid={`reel-download-${c}`}
                    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 99, padding: "12px 18px", border: "1px solid rgba(255,255,255,.25)", color: meta(c).ready ? "#F5F4F1" : "#5b606c", fontWeight: 600, fontSize: 16, pointerEvents: meta(c).ready ? "auto" : "none", textDecoration: "none" }}>
                    <Download className="w-4 h-4" /> {meta(c).ready ? "MP4" : "Rendering…"}
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── main player ────────────────────────────────────────────── */
export default function Reel() {
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const REC = sp.get("rec") === "1";
  const urlClip = CLIPS[sp.get("clip")] ? sp.get("clip") : "platform";

  const [clip, setClip] = useState(urlClip);
  const [phase, setPhase] = useState(REC ? "playing" : "cover"); // cover | playing | done
  const [idx, setIdx] = useState(0);
  const [progress, setProgress] = useState(0);
  const [nonce, setNonce] = useState(0);
  const [narration, setNarration] = useState({});
  const [scale, setScale] = useState(1);

  const audioRef = useRef(null);
  const narrationRef = useRef({});
  const scenes = CLIPS[clip];

  useEffect(() => { narrationRef.current = narration; }, [narration]);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / 1080, window.innerHeight / 1920));
    fit(); window.addEventListener("resize", fit); return () => window.removeEventListener("resize", fit);
  }, []);
  useEffect(() => {
    fetch(`${API}/api/reel/script/${clip}`).then((r) => r.json()).then((d) => setNarration(d.narration || {})).catch(() => {});
  }, [clip]);

  const estimateDur = (text) => {
    const words = (text || "").split(/\s+/).filter(Boolean).length;
    return Math.max(4, words * 0.4 + 1.2);
  };

  const goNext = useCallback(() => {
    setIdx((prev) => { if (prev + 1 >= scenes.length) { setPhase("done"); return prev; } return prev + 1; });
  }, [scenes.length]);

  useEffect(() => {
    if (phase !== "playing") return undefined;
    const scene = scenes[idx];
    let cancelled = false;
    setProgress(0);

    const nxt = scenes[idx + 1];
    if (nxt) { try { fetch(`${API}/api/reel/tts/${clip}/${nxt.id}`).catch(() => {}); } catch (e) { /* noop */ } }

    const a = audioRef.current;
    const forcedDur = (REC && Array.isArray(window.__REC_DUR__)) ? window.__REC_DUR__[idx] : null;
    const estDur = forcedDur != null ? forcedDur : estimateDur(narrationRef.current[scene.id]);
    let usingFallback = false;
    let raf; let last = 0; let acc = 0;

    const finish = () => { if (!cancelled) goNext(); };
    const runFallback = () => {
      usingFallback = true;
      const step = (now) => {
        if (cancelled) return;
        if (last === 0) last = now;
        acc += now - last; last = now;
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
      a.pause(); a.muted = false;
      a.src = `${API}/api/reel/tts/${clip}/${scene.id}`;
      try { a.currentTime = 0; } catch (e) { /* noop */ }
      a.addEventListener("timeupdate", onTime);
      a.addEventListener("ended", onEnd);
      a.addEventListener("error", onErr);
      a.play().catch(() => { cleanupAudio(); runFallback(); });
    } else {
      runFallback();
    }
    return () => { cancelled = true; cleanupAudio(); if (raf) cancelAnimationFrame(raf); if (a) a.pause(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, idx, nonce, clip, goNext]);

  const start = useCallback(async (c) => {
    const target = c || clip;
    setClip(target);
    try { await fetch(`${API}/api/reel/tts/${target}/${CLIPS[target][0].id}`); } catch (e) { /* noop */ }
    setNonce((n) => n + 1); setIdx(0); setPhase("playing");
  }, [clip]);

  // Recording harness (only when ?rec=1)
  useEffect(() => {
    if (!REC) return;
    window.__REC__ = true;
    window.__REC_START__ = () => { setNonce((n) => n + 1); setIdx(0); setPhase("playing"); };
  }, [REC]);
  useEffect(() => { if (REC && phase === "done") window.__REC_DONE__ = true; }, [REC, phase]);

  const scene = scenes[idx];
  const nBeats = scene && scene.kind === "chat" ? scene.beats.length : 0;
  const shown = nBeats ? Math.min(nBeats, Math.floor(progress * nBeats) + 1) : 0;

  const capText = useMemo(() => {
    const full = narration[scene?.id] || "";
    const sentences = full.match(/[^.!?]+[.!?]+/g) || (full ? [full] : []);
    if (!sentences.length) return "";
    const i = Math.min(sentences.length - 1, Math.floor(progress * sentences.length));
    return sentences[i].trim();
  }, [narration, scene, progress]);

  if (phase === "cover") {
    return <Picker onPlay={(c) => start(c)} />;
  }

  return (
    <div className="reel-viewport">
      <audio ref={audioRef} preload="auto" />
      <div className="reel-stage" style={{ transform: `scale(${scale})` }} data-testid="reel-stage">
        {/* top brand + segmented progress */}
        <div className="reel-topbar">
          <div className="reel-segs">
            {scenes.map((s, i) => (
              <div key={i} className="reel-seg"><i style={{ width: `${i < idx ? 100 : i === idx ? progress * 100 : 0}%` }} /></div>
            ))}
          </div>
          <div className="reel-brandrow">
            <div className="reel-wordmark">fund<b>le</b></div>
            <div className="reel-clip-label">{CLIP_META[clip].label}</div>
          </div>
        </div>

        {/* content */}
        <div className="reel-content">
          <AnimatePresence mode="wait">
            <motion.div key={`${clip}-${idx}-${nonce}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }} style={{ width: "100%" }}>
              {scene.kind === "hook" && <HookScene scene={scene} />}
              {scene.kind === "agent" && <AgentScene scene={scene} />}
              {scene.kind === "stats" && <StatsScene scene={scene} />}
              {scene.kind === "cta" && <CtaScene scene={scene} />}
              {scene.kind === "chat" && <ChatScene scene={scene} shown={shown} />}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* caption */}
        {capText && (
          <div className="reel-caption">
            <AnimatePresence mode="wait">
              <motion.span key={capText} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }} data-testid="reel-caption">{capText}</motion.span>
            </AnimatePresence>
          </div>
        )}
        <div className="reel-cc">Trained by fundle.ai</div>
      </div>

      {/* done overlay (non-rec) */}
      {!REC && phase === "done" && (
        <div style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(5,6,9,.86)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 20 }} data-testid="reel-done-overlay">
          <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 40, fontWeight: 700 }}>fund<b style={{ color: "#C7A76D" }}>le</b></div>
          <div style={{ display: "flex", gap: 12 }}>
            <button onClick={() => start(clip)} className="reel-btn" style={{ cursor: "pointer", border: "none" }} data-testid="reel-replay">Replay</button>
            <a href={`${API}/api/reel/film/${clip}.mp4`} className="reel-btn" style={{ textDecoration: "none" }} data-testid="reel-download-done"><Download className="w-5 h-5" /> Download</a>
            <button onClick={() => setPhase("cover")} style={{ borderRadius: 99, padding: "18px 34px", border: "1px solid rgba(255,255,255,.25)", color: "#F5F4F1", background: "transparent", cursor: "pointer", fontWeight: 600, fontSize: 20 }} data-testid="reel-more">More reels</button>
          </div>
          <button onClick={() => navigate("/contact")} style={{ marginTop: 8, color: "#C7A76D", background: "none", border: "none", cursor: "pointer", fontSize: 18 }}>Book a demo →</button>
        </div>
      )}
    </div>
  );
}
