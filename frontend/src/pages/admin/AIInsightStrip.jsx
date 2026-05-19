/* AI Intelligence Report — multi-section panel (Headline, Summary, Drivers,
   Recommended Actions). Cached 1 hour at the backend (per dashboard + payload).

   Props:
     - dashboardKey: string (unique id like "command_center", "rfm_churn")
     - payload: object      (the KPI snapshot the AI should reason over)
     - autoLoad?: bool      (default true)
     - title?: string       (default "AI Intelligence Report")
*/
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Sparkles, RefreshCw, TrendingUp, Target } from "lucide-react";

export default function AIInsightStrip({
  dashboardKey,
  payload,
  autoLoad = true,
  title = "AI Intelligence Report",
}) {
  const [report, setReport] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async (force = false) => {
    if (!payload) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/dashboard/insight", {
        dashboard_key: dashboardKey,
        payload,
        force,
      });
      setReport(res.data.report);
      setMeta({ cached: res.data.cached, generated_at: res.data.generated_at });
    } catch (e) {
      setError(e?.response?.data?.detail || "AI intelligence unavailable");
    } finally {
      setLoading(false);
    }
  };

  // Stable trigger
  const payloadKey = payload ? JSON.stringify(payload) : null;
  useEffect(() => {
    if (autoLoad && payloadKey) load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardKey, payloadKey, autoLoad]);

  return (
    <div
      className="bg-white border border-black/10"
      data-testid={`ai-insight-${dashboardKey}`}
    >
      <div className="px-5 py-3 border-b border-black/5 flex items-center justify-between bg-gradient-to-r from-neutral-50 to-white">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-neutral-900 text-white flex items-center justify-center">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-neutral-500">
              FUNDLE BRAIN · LIVE COMPUTED
            </div>
            <h3 className="font-display text-lg leading-tight">{title}</h3>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          {meta?.generated_at && !loading && (
            <span className="font-mono text-[10px]">
              {meta.cached ? "cached" : "fresh"} · {new Date(meta.generated_at).toLocaleTimeString("en-IN")}
            </span>
          )}
          <button
            onClick={() => load(true)}
            className="text-neutral-600 hover:text-black flex items-center gap-1.5 text-xs"
            data-testid={`ai-insight-refresh-${dashboardKey}`}
            disabled={loading}
            title="Regenerate insight (force)"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Regenerate
          </button>
        </div>
      </div>

      <div className="p-5">
        {loading && !report && (
          <div className="text-sm text-neutral-400" data-testid={`ai-insight-loading-${dashboardKey}`}>
            Fundle Brain is analysing the live data…
          </div>
        )}
        {error && (
          <div className="text-sm text-red-600" data-testid={`ai-insight-error-${dashboardKey}`}>
            {error}
          </div>
        )}
        {!loading && !error && report && (
          <div className="space-y-4" data-testid={`ai-insight-report-${dashboardKey}`}>
            {/* Headline */}
            {report.headline && (
              <div
                className="font-display text-2xl tracking-tight text-neutral-900 leading-snug"
                data-testid="ai-insight-headline"
              >
                "{report.headline}"
              </div>
            )}

            {/* Summary */}
            {report.summary && (
              <p
                className="text-[15px] leading-relaxed text-neutral-700"
                data-testid="ai-insight-summary"
              >
                {report.summary}
              </p>
            )}

            <div className="grid md:grid-cols-2 gap-4 pt-2">
              {/* Drivers */}
              {report.drivers?.length > 0 && (
                <div className="bg-neutral-50 border border-black/5 p-4" data-testid="ai-insight-drivers">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-3">
                    <TrendingUp className="w-3.5 h-3.5" /> Key Drivers
                  </div>
                  <ul className="space-y-2">
                    {report.drivers.map((d, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-neutral-800"
                        data-testid={`ai-insight-driver-${i}`}
                      >
                        <span className="text-neutral-400 font-mono text-xs pt-0.5 shrink-0">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <span>{d}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Recommendations */}
              {report.recommendations?.length > 0 && (
                <div className="bg-[#571326]/[0.04] border border-[#571326]/15 p-4" data-testid="ai-insight-recommendations">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-[#571326] mb-3">
                    <Target className="w-3.5 h-3.5" /> Recommended Actions
                  </div>
                  <ul className="space-y-2">
                    {report.recommendations.map((r, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-neutral-900"
                        data-testid={`ai-insight-recommendation-${i}`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-[#571326] mt-2 shrink-0" />
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
        {!loading && !error && !report && (
          <div className="text-sm text-neutral-400">No intelligence yet.</div>
        )}
      </div>
    </div>
  );
}
