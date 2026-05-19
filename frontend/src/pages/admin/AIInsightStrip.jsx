/* AI Insight Strip — generates a 2-sentence executive insight, cached 1 hour.

   Props:
     - dashboardKey: string (unique id like "command_center", "rfm_churn")
     - payload: object      (the KPI snapshot the AI should reason over)
     - autoLoad?: bool      (default true)
*/
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Sparkles, RefreshCw } from "lucide-react";

export default function AIInsightStrip({ dashboardKey, payload, autoLoad = true }) {
  const [insight, setInsight] = useState(null);
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
      setInsight(res.data.insight);
      setMeta({ cached: res.data.cached, generated_at: res.data.generated_at });
    } catch (e) {
      setError(e?.response?.data?.detail || "AI insight unavailable");
    } finally {
      setLoading(false);
    }
  };

  // Stringify-stable trigger so we don't refetch on every parent rerender
  const payloadKey = payload ? JSON.stringify(payload) : null;
  useEffect(() => {
    if (autoLoad && payloadKey) load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardKey, payloadKey, autoLoad]);

  return (
    <div
      className="bg-white border border-black/10 p-5 flex items-start gap-4"
      data-testid={`ai-insight-${dashboardKey}`}
    >
      <div className="w-9 h-9 rounded-full bg-neutral-900 text-white flex items-center justify-center shrink-0">
        <Sparkles className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500">
            AI INSIGHT · Fundle Brain
          </div>
          <button
            onClick={() => load(true)}
            className="text-xs text-neutral-500 hover:text-black flex items-center gap-1"
            data-testid={`ai-insight-refresh-${dashboardKey}`}
            disabled={loading}
            title="Regenerate insight"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            {meta?.cached ? "cached" : "live"}
          </button>
        </div>
        <div className="text-[15px] leading-relaxed text-neutral-900">
          {loading && !insight && <span className="text-neutral-400">Generating insight…</span>}
          {error && <span className="text-red-600 text-sm">{error}</span>}
          {!loading && !error && insight && <span>{insight}</span>}
          {!loading && !error && !insight && (
            <span className="text-neutral-400">No insight yet.</span>
          )}
        </div>
      </div>
    </div>
  );
}
