import { Brain, Sparkles } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

/**
 * Floating Fundle Brain FAB.
 * Appears on every admin page (mounted in AdminLayout). Hides when the user
 * is already ON the Fundle Brain chat so it doesn't overlap the input box.
 */
export default function FundleBrainFAB() {
  const navigate = useNavigate();
  const location = useLocation();
  if (location.pathname.startsWith("/admin/ai")) return null;
  return (
    <button
      type="button"
      onClick={() => navigate("/admin/ai")}
      data-testid="fundle-brain-fab"
      className="fixed bottom-5 right-5 z-30 group flex items-center gap-2.5 pl-2.5 pr-4 py-2.5 rounded-full shadow-xl shadow-burgundy-900/30 hover:shadow-2xl hover:scale-[1.03] transition-all"
      style={{
        background:
          "linear-gradient(135deg, var(--kazo-burgundy) 0%, var(--kazo-burgundy-deep) 60%, #2A0814 100%)",
        border: "1px solid rgba(199,167,109,0.5)",
      }}
      aria-label="Ask Fundle Brain"
      title="Ask Fundle Brain anything about your data"
    >
      <div
        className="w-9 h-9 rounded-full bg-gradient-to-br from-amber-300/40 to-amber-100/10 border border-amber-200/50 flex items-center justify-center shrink-0 group-hover:rotate-6 transition-transform"
      >
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
