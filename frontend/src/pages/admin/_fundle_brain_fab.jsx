import { useRef, useState, useEffect, useCallback } from "react";
import { Brain, Sparkles, GripVertical } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

/**
 * Floating Fundle Brain FAB — now DRAGGABLE.
 * Drag it anywhere (mouse or touch); position is remembered across pages/reloads.
 * A plain click still opens Fundle Brain; a drag only moves it.
 * Hidden while already on the Fundle Brain chat so it doesn't overlap the input.
 */
const POS_KEY = "fundle_fab_pos";
const DRAG_THRESHOLD = 6; // px of movement before it counts as a drag (not a click)

export default function FundleBrainFAB() {
  const navigate = useNavigate();
  const location = useLocation();
  const btnRef = useRef(null);
  const drag = useRef({ active: false, moved: false, startX: 0, startY: 0, originX: 0, originY: 0 });
  const [pos, setPos] = useState(() => {
    try { const s = localStorage.getItem(POS_KEY); return s ? JSON.parse(s) : null; } catch { return null; }
  });

  const clamp = useCallback((x, y) => {
    const el = btnRef.current;
    const w = el ? el.offsetWidth : 180;
    const h = el ? el.offsetHeight : 56;
    const maxX = window.innerWidth - w - 8;
    const maxY = window.innerHeight - h - 8;
    return { x: Math.max(8, Math.min(x, maxX)), y: Math.max(8, Math.min(y, maxY)) };
  }, []);

  // Keep it on-screen if the window is resized.
  useEffect(() => {
    const onResize = () => setPos((p) => (p ? clamp(p.x, p.y) : p));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [clamp]);

  // Persist position whenever it settles.
  useEffect(() => {
    if (pos) { try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch { /* ignore */ } }
  }, [pos]);

  if (location.pathname.startsWith("/admin/ai")) return null;

  const onPointerDown = (e) => {
    const el = btnRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    drag.current = {
      active: true, moved: false,
      startX: e.clientX, startY: e.clientY,
      originX: rect.left, originY: rect.top,
    };
    try { el.setPointerCapture(e.pointerId); } catch { /* ignore */ }
  };

  const onPointerMove = (e) => {
    if (!drag.current.active) return;
    const dx = e.clientX - drag.current.startX;
    const dy = e.clientY - drag.current.startY;
    if (!drag.current.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    drag.current.moved = true;
    setPos(clamp(drag.current.originX + dx, drag.current.originY + dy));
  };

  const onPointerUp = (e) => {
    const el = btnRef.current;
    try { el?.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
    if (drag.current.active && !drag.current.moved) {
      navigate("/admin/ai");
    }
    drag.current.active = false;
  };

  return (
    <button
      ref={btnRef}
      type="button"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      data-testid="fundle-brain-fab"
      className={`fixed z-30 group flex items-center gap-2 pl-2 pr-4 py-2.5 rounded-full shadow-xl shadow-burgundy-900/30 hover:shadow-2xl transition-[box-shadow] ${pos ? "" : "bottom-5 right-5"}`}
      style={{
        background:
          "linear-gradient(135deg, var(--kazo-burgundy) 0%, var(--kazo-burgundy-deep) 60%, #2A0814 100%)",
        border: "1px solid rgba(199,167,109,0.5)",
        touchAction: "none",
        cursor: drag.current.active ? "grabbing" : "grab",
        ...(pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" } : {}),
      }}
      aria-label="Ask Fundle Brain (drag to move)"
      title="Click to ask Fundle Brain · drag to move"
    >
      <GripVertical className="w-3.5 h-3.5 kazo-text-champagne/60 -ml-0.5 shrink-0" aria-hidden="true" />
      <div className="w-9 h-9 rounded-full bg-gradient-to-br from-amber-300/40 to-amber-100/10 border border-amber-200/50 flex items-center justify-center shrink-0 group-hover:rotate-6 transition-transform">
        <Brain className="w-4 h-4 kazo-text-champagne" />
      </div>
      <div className="text-left">
        <div className="font-display text-sm tracking-tight text-white leading-none flex items-center gap-1">
          Fundle Brain
          <Sparkles className="w-3 h-3 kazo-text-champagne" />
        </div>
        <div className="text-[9px] uppercase tracking-[0.2em] kazo-text-champagne/80 leading-none mt-1">
          ASK ANYTHING
        </div>
      </div>
    </button>
  );
}
