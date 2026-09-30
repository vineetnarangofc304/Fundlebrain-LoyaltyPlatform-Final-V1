import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { fmtMoney2, fmtNum } from "@/lib/format";
import { X, Loader2, TrendingUp, Users, Store, Ticket, Package, IndianRupee, Coins } from "lucide-react";
import { WINDOWS } from "./CampaignObjective";

function Stat({ label, value, sub, testid, accent }) {
  return (
    <div className="border border-black/10 rounded p-3 bg-white" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div className={`text-2xl font-display mt-1 ${accent || ""}`}>{value}</div>
      {sub && <div className="text-[11px] text-neutral-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function CampaignRoiModal({ campaign, onClose }) {
  const [window, setWindow] = useState(campaign.roi_window || "7d");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const r = await api.get(`/campaigns/${campaign.id}/roi`, { params: { window } });
      setData(r.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Failed to load ROI");
      setData(null);
    } finally { setLoading(false); }
  }, [campaign.id, window]);

  useEffect(() => { load(); }, [load]);

  const u = data?.universal || {};

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-neutral-50 w-full max-w-4xl max-h-[92vh] overflow-y-auto rounded" onClick={(e) => e.stopPropagation()} data-testid="campaign-roi-modal">
        <div className="flex items-center justify-between p-5 border-b border-black/10 bg-white sticky top-0 z-10">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-neutral-500">Campaign ROI · {(data?.objective || campaign.objective || "generic")}</div>
            <h3 className="font-display text-xl">{campaign.name}</h3>
          </div>
          <button onClick={onClose} className="k-btn k-btn-ghost" data-testid="roi-close"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-5 space-y-5">
          {/* window selector */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] uppercase tracking-widest text-neutral-500">Attribution window</span>
            {WINDOWS.map((w) => (
              <button key={w.k} type="button" onClick={() => setWindow(w.k)} data-testid={`roi-window-${w.k}`}
                className={`pill ${window === w.k ? "kazo-bg-burgundy text-white" : "pill-neutral"}`}>{w.label}</button>
            ))}
          </div>

          {loading && <div className="flex items-center gap-2 text-neutral-500 py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /> Computing real attribution…</div>}
          {err && <div className="text-rose-600 text-sm py-6 text-center" data-testid="roi-error">{err}</div>}

          {!loading && !err && data && (
            <>
              {/* universal */}
              <div>
                <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 flex items-center gap-1"><TrendingUp className="w-3.5 h-3.5" /> Universal ROI — came back &amp; shopped</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Stat label="Targeted" value={fmtNum(data.dataset_size)} sub={`${fmtNum(data.sent)} sent`} testid="roi-targeted" />
                  <Stat label="Converters" value={fmtNum(u.converters)} sub={`${u.conversion_rate_pct}% conversion`} accent="text-emerald-700" testid="roi-converters" />
                  <Stat label="Attributed net sales" value={fmtMoney2(u.attributed_net_revenue)} sub={`${fmtNum(u.attributed_bills)} bills`} testid="roi-revenue" />
                  <Stat label="Revenue / recipient" value={fmtMoney2(u.revenue_per_recipient)} testid="roi-rpr" />
                </div>
                {(u.cost != null) && (
                  <div className="mt-3">
                    <Stat label="ROI vs spend" value={u.roi_pct != null ? `${u.roi_pct}%` : "—"} sub={`Spend ${fmtMoney2(u.cost)}`} accent={u.roi_pct >= 0 ? "text-emerald-700" : "text-rose-600"} testid="roi-pct" />
                  </div>
                )}
              </div>

              {/* store */}
              {(data.store || data.store_breakdown) && (
                <div data-testid="roi-store">
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 flex items-center gap-1"><Store className="w-3.5 h-3.5" /> Store-wise{data.store ? " (target highlighted)" : " breakdown (top 10)"}</div>
                  {data.store && (
                    <div className="grid grid-cols-2 gap-3 mb-2">
                      <Stat label="Target-store converters" value={fmtNum(data.store.target_converters)} testid="roi-store-target-conv" />
                      <Stat label="Target-store net sales" value={fmtMoney2(data.store.target_revenue)} accent="text-emerald-700" testid="roi-store-target-rev" />
                    </div>
                  )}
                  <div className="bg-white border border-black/10 rounded overflow-hidden">
                    <table className="data-table">
                      <thead><tr><th>Store</th><th className="text-right">Converters</th><th className="text-right">Net sales</th></tr></thead>
                      <tbody>
                        {(data.store?.breakdown || data.store_breakdown || []).map((s) => {
                          const isTarget = data.store && (data.store.target_store_codes || []).includes(s.store_code);
                          return (
                            <tr key={s.store_code} className={isTarget ? "bg-amber-50" : ""}>
                              <td>{s.store_name || s.store_code} {isTarget && <span className="pill pill-warning ml-1">target</span>}</td>
                              <td className="text-right font-mono">{fmtNum(s.converters)}</td>
                              <td className="text-right font-mono">{fmtMoney2(s.revenue)}</td>
                            </tr>
                          );
                        })}
                        {((data.store?.breakdown || data.store_breakdown || []).length === 0) && <tr><td colSpan={3} className="text-center text-neutral-400 py-4">No attributed bills in window</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* coupon */}
              {data.coupon && (
                <div data-testid="roi-coupon">
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 flex items-center gap-1"><Ticket className="w-3.5 h-3.5" /> Coupon redemptions · {(data.coupon.coupon_codes || []).join(", ")}</div>
                  <div className="grid grid-cols-3 gap-3">
                    <Stat label="Redemptions" value={fmtNum(data.coupon.redemptions)} testid="roi-coupon-redemptions" />
                    <Stat label="Unique redeemers" value={fmtNum(data.coupon.redeemers)} testid="roi-coupon-redeemers" />
                    <Stat label="Discount given" value={fmtMoney2(data.coupon.discount_given)} testid="roi-coupon-discount" />
                  </div>
                </div>
              )}

              {/* sku */}
              {data.sku && (
                <div data-testid="roi-sku">
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 flex items-center gap-1"><Package className="w-3.5 h-3.5" /> Target products sold {data.sku.categories?.length ? `· ${data.sku.categories.join(", ")}` : ""}</div>
                  <div className="grid grid-cols-3 gap-3">
                    <Stat label="Units sold" value={fmtNum(data.sku.units_sold)} sub={`${fmtNum(data.sku.target_sku_count)} SKUs targeted`} testid="roi-sku-units" />
                    <Stat label="Value sold" value={fmtMoney2(data.sku.value_sold)} accent="text-emerald-700" testid="roi-sku-value" />
                    <Stat label="Buyers" value={fmtNum(data.sku.buyers)} testid="roi-sku-buyers" />
                  </div>
                </div>
              )}

              {/* points */}
              {data.points && (
                <div data-testid="roi-points">
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 flex items-center gap-1"><Coins className="w-3.5 h-3.5" /> Points redeemed by this audience</div>
                  <div className="grid grid-cols-3 gap-3">
                    <Stat label="Points redeemed" value={fmtNum(data.points.points_redeemed)} accent="text-emerald-700" testid="roi-points-redeemed" />
                    <Stat label="Redemption events" value={fmtNum(data.points.redemption_events)} testid="roi-points-events" />
                    <Stat label="Unique redeemers" value={fmtNum(data.points.redeemers)} testid="roi-points-redeemers" />
                  </div>
                </div>
              )}

              <div className="text-[10px] text-neutral-400 pt-2 border-t border-black/5">
                Measured against {fmtNum(data.dataset_size)} shoppers frozen at launch · window {data.t0?.slice(0, 10)} → {data.window_end?.slice(0, 10)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
