import { useState } from "react";
import { useTour } from "@/components/tour/TourProvider";
import { SECTIONS, FULL_TOUR, sectionTour } from "@/lib/demoScript";
import { BRAND } from "@/brand.config";
import {
  Play, Sparkles, Loader2, ArrowRight,
  LayoutDashboard, Radio, TrendingUp, UserRound, Award, BarChart3, Layers, Users,
  Brain, Filter, Send, Ticket, ShieldCheck, FileBarChart, UserCog, Activity,
} from "lucide-react";

const ICONS = {
  LayoutDashboard, Radio, TrendingUp, UserRound, Award, BarChart3, Layers, Users,
  Brain, Filter, Send, Ticket, ShieldCheck, FileBarChart, UserCog, Activity,
};

// Optional: drop real recorded/YouTube URLs here later, keyed by section id,
// to surface a "Watch video" button on that tutorial card.
const VIDEO_URLS = {};

export default function DemoLanding() {
  const tour = useTour();
  const [busy, setBusy] = useState(null); // 'full' | sectionId | null

  const launch = async (key, steps) => {
    if (busy) return;
    setBusy(key);
    try {
      await tour.startTour(steps);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen text-white" style={{ background: "var(--kazo-black)" }} data-testid="demo-landing">
      {/* ---- Hero ---- */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{
          background: "radial-gradient(900px 500px at 80% -10%, rgba(199,167,109,0.18), transparent 60%), radial-gradient(700px 400px at 0% 10%, var(--kazo-burgundy), transparent 55%)",
        }} />
        <div className="relative max-w-6xl mx-auto px-6 pt-12 pb-16 sm:pt-20 sm:pb-24">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.28em]" style={{ color: "var(--kazo-champagne)" }}>
            <Sparkles className="w-3.5 h-3.5" /> {BRAND.poweredBy}
          </div>

          <h1 className="font-display tracking-tight mt-5 text-4xl sm:text-5xl lg:text-6xl leading-[1.05]">
            See <span style={{ color: "var(--kazo-champagne)" }}>{BRAND.name}</span> run — live.
          </h1>
          <p className="mt-5 text-white/70 text-base sm:text-lg max-w-2xl leading-relaxed">
            A self-running, narrated walkthrough of the {BRAND.platform} loyalty &amp; customer-intelligence
            platform — dashboards, the {BRAND.aiAssistant} AI, campaigns, support and reporting — over the real product.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              onClick={() => launch("full", FULL_TOUR)}
              disabled={!!busy}
              data-testid="start-full-tour-btn"
              className="group inline-flex items-center gap-3 rounded-full px-7 py-4 text-black font-semibold transition-transform hover:scale-[1.02] disabled:opacity-60"
              style={{ background: "linear-gradient(135deg, var(--kazo-champagne), var(--kazo-champagne-light))" }}
            >
              {busy === "full" ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
              {busy === "full" ? "Starting the tour…" : "Start the 5-minute Guided Tour"}
              {!busy && <ArrowRight className="w-4 h-4 opacity-60 group-hover:translate-x-0.5 transition-transform" />}
            </button>
            <span className="text-white/45 text-sm">Auto-plays with AI voice · read-only · pause anytime</span>
          </div>
        </div>
      </section>

      {/* ---- Tutorials ---- */}
      <section className="max-w-6xl mx-auto px-6 pb-24">
        <div className="flex items-end justify-between gap-4 border-t border-white/10 pt-12">
          <div>
            <h2 className="font-display text-2xl sm:text-3xl">Section tutorials</h2>
            <p className="text-white/55 text-sm mt-1">Short, focused ~2-minute walkthroughs of each part of the platform.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-8">
          {SECTIONS.map((s) => {
            const Icon = ICONS[s.icon] || LayoutDashboard;
            const videoUrl = VIDEO_URLS[s.id];
            return (
              <div
                key={s.id}
                className="group relative rounded-2xl p-6 flex flex-col transition-all hover:-translate-y-0.5"
                style={{ background: "linear-gradient(160deg, #16090F 0%, #0E0E0E 70%)", border: "1px solid rgba(255,255,255,0.08)" }}
                data-testid={`tutorial-card-${s.id}`}
              >
                <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-4"
                  style={{ background: "rgba(199,167,109,0.12)", border: "1px solid rgba(199,167,109,0.3)" }}>
                  <Icon className="w-5 h-5" style={{ color: "var(--kazo-champagne)" }} />
                </div>
                <h3 className="font-display text-lg leading-tight">{s.title}</h3>
                <p className="text-white/55 text-sm mt-2 leading-relaxed flex-1">{s.blurb}</p>

                <div className="mt-5 flex items-center gap-3">
                  <button
                    onClick={() => launch(s.id, sectionTour(s.id))}
                    disabled={!!busy}
                    data-testid={`play-tutorial-${s.id}`}
                    className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-black transition-transform hover:scale-[1.03] disabled:opacity-60"
                    style={{ background: "linear-gradient(135deg, var(--kazo-champagne), var(--kazo-champagne-light))" }}
                  >
                    {busy === s.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    {busy === s.id ? "Starting…" : "Play demo"}
                  </button>
                  {videoUrl && (
                    <a href={videoUrl} target="_blank" rel="noreferrer"
                      className="text-sm text-white/60 hover:text-white underline-offset-2 hover:underline">
                      Watch video
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="border-t border-white/10">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-3 text-white/40 text-sm">
          <div className="font-display text-white/80 text-lg">{BRAND.name}</div>
          <div className="flex items-center gap-1.5"><Sparkles className="w-3.5 h-3.5" style={{ color: "var(--kazo-champagne)" }} /> {BRAND.poweredBy}</div>
        </div>
      </footer>
    </div>
  );
}
