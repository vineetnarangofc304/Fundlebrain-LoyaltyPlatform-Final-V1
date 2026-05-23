import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  X, Loader2, MapPin, Phone, Mail, Calendar, Coins, TrendingUp,
  Store as StoreIcon, Award, MessageSquare, Activity, Cake, ShoppingBag, Clock,
} from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip as ChartTooltip, BarChart, Bar } from "recharts";

const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN");
const fmtINR = (v) => v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const fmtDate = (s) => !s ? "—" : new Date(s).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });
const fmtDateTime = (s) => !s ? "—" : new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

const TIER_COLOR = {
  platinum: "bg-indigo-100 text-indigo-800 border-indigo-300",
  gold: "bg-amber-100 text-amber-800 border-amber-300",
  silver: "bg-neutral-200 text-neutral-700 border-neutral-300",
  bronze: "bg-orange-100 text-orange-800 border-orange-300",
};

const SECTION_HEAD = (label) => (
  <div className="text-[10px] uppercase tracking-[0.18em] text-neutral-500 mb-2 mt-5 first:mt-0">{label}</div>
);

const FieldRow = ({ icon: Icon, label, value }) => (
  <div className="flex items-start gap-2 text-sm py-1">
    {Icon && <Icon className="w-3.5 h-3.5 text-neutral-400 mt-1 shrink-0" />}
    <div className="flex-1 min-w-0">
      <div className="text-[10px] uppercase tracking-widest text-neutral-400">{label}</div>
      <div className="text-sm truncate">{value || <span className="text-neutral-400">—</span>}</div>
    </div>
  </div>
);

const MetricChip = ({ label, value, accent = "neutral" }) => {
  const colors = {
    neutral: "bg-neutral-50 border-neutral-200",
    amber: "bg-amber-50 border-amber-200",
    indigo: "bg-indigo-50 border-indigo-200",
    teal: "bg-teal-50 border-teal-200",
    burgundy: "bg-rose-50 border-rose-200",
  };
  return (
    <div className={`rounded border px-3 py-2 ${colors[accent]}`}>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div className="font-display text-lg leading-tight">{value}</div>
    </div>
  );
};

export default function CustomerDetailDrawer({ mobile, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("overview");

  useEffect(() => {
    if (!mobile) return;
    setLoading(true);
    setData(null);
    api.get(`/dashboard/customer-by-mobile/${mobile}`)
      .then((r) => setData(r.data))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load customer"))
      .finally(() => setLoading(false));
  }, [mobile]);

  if (!mobile) return null;

  const c = data?.customer || {};
  const lt = data?.lifetime || {};
  const rfm = data?.rfm || {};
  const home = data?.home_store;
  const patterns = data?.patterns;
  const tx = data?.recent_transactions || [];
  const ledger = data?.points_ledger || [];
  const nps = data?.nps_history || [];
  const monthly = data?.monthly_spend || [];
  const cats = data?.category_affinity || [];
  const stores = data?.store_affinity || [];

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-sm"
      onClick={onClose}
      data-testid="customer-drawer"
    >
      <div
        className="bg-white w-full md:w-[680px] lg:w-[820px] h-full overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Sticky header */}
        <div className="sticky top-0 z-10 bg-white border-b border-neutral-200 px-5 py-4 flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-[0.18em] text-neutral-400 mb-1">Customer 360</div>
            <div className="font-display text-2xl leading-tight flex items-center gap-2">
              {c.name || <span className="text-neutral-400">Unnamed</span>}
              {c.tier && (
                <span className={`text-[10px] uppercase tracking-widest border rounded px-2 py-0.5 ${TIER_COLOR[c.tier] || "bg-neutral-100 border-neutral-300"}`}>
                  {c.tier}
                </span>
              )}
              {rfm.segment && (
                <span className="text-[10px] uppercase tracking-widest border border-indigo-300 bg-indigo-50 text-indigo-700 rounded px-2 py-0.5">
                  {rfm.segment}
                </span>
              )}
            </div>
            <div className="text-xs text-neutral-500 mt-1 flex items-center gap-2 flex-wrap">
              <span className="font-mono">{c.mobile}</span>
              {c.email && <span>· {c.email}</span>}
              {c.city && <span>· {c.city}</span>}
            </div>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-900 p-1" data-testid="drawer-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading && (
          <div className="p-10 text-center text-neutral-500 flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading customer details…
          </div>
        )}

        {data && (
          <div className="p-5">
            {/* TOP-LEVEL METRIC ROW */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-5">
              <MetricChip label="Lifetime Spend" value={fmtINR(lt.spend)} accent="burgundy" />
              <MetricChip label="Bills" value={fmtNum(lt.visits)} accent="indigo" />
              <MetricChip label="AOV" value={fmtINR(lt.aov)} accent="amber" />
              <MetricChip label="Points Balance" value={fmtNum(c.points_balance)} accent="teal" />
              <MetricChip label="Lifetime Earned" value={fmtNum(c.lifetime_points_earned)} accent="neutral" />
              <MetricChip label="Lifetime Redeemed" value={fmtNum(c.lifetime_points_redeemed)} accent="neutral" />
              <MetricChip label="Recency" value={`${rfm.recency_days}d`} accent="neutral" />
              <MetricChip label="RFM Score" value={rfm.score || "—"} accent="neutral" />
            </div>

            {/* TABS */}
            <div className="border-b border-neutral-200 mb-4 flex items-center gap-1 overflow-x-auto" data-testid="drawer-tabs">
              {["overview", "transactions", "points", "stores", "nps"].map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`text-xs px-3 py-2 border-b-2 -mb-px capitalize whitespace-nowrap ${tab === t ? "border-neutral-900 text-neutral-900 font-medium" : "border-transparent text-neutral-500 hover:text-neutral-800"}`}
                  data-testid={`tab-${t}`}
                >
                  {t === "overview" && "Overview"}
                  {t === "transactions" && `Transactions (${tx.length})`}
                  {t === "points" && `Points Ledger (${ledger.length})`}
                  {t === "stores" && "Stores & Categories"}
                  {t === "nps" && `NPS (${nps.length})`}
                </button>
              ))}
            </div>

            {tab === "overview" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
                <div>
                  {SECTION_HEAD("Identity")}
                  <FieldRow icon={Phone} label="Mobile" value={c.mobile} />
                  <FieldRow icon={Mail} label="Email" value={c.email} />
                  <FieldRow icon={Cake} label="Birthday" value={fmtDate(c.birthday)} />
                  <FieldRow icon={Calendar} label="Anniversary" value={fmtDate(c.anniversary)} />
                  <FieldRow icon={MapPin} label="City / State" value={[c.city, c.state].filter(Boolean).join(", ")} />
                  <FieldRow label="Gender" value={c.gender} />
                  <FieldRow label="Source" value={c.source} />
                  <FieldRow label="Preferred Language" value={c.preferred_language} />
                </div>
                <div>
                  {SECTION_HEAD("Loyalty Journey")}
                  <FieldRow icon={Calendar} label="First purchase (R1)" value={fmtDateTime(lt.first_purchase || c.first_purchase_at)} />
                  <FieldRow icon={Clock} label="Last visit" value={fmtDateTime(lt.last_purchase || c.last_visit_at)} />
                  <FieldRow icon={StoreIcon} label="Home store (R2)" value={home ? `${home.name} · ${home.code || ""} · ${home.city || ""}` : "—"} />
                  <FieldRow icon={Activity} label="Churn risk" value={c.churn_risk} />
                  <FieldRow label="Card validity" value={c.card_validity} />
                  {patterns && (
                    <>
                      <FieldRow icon={Calendar} label="Day-of-week pattern" value={patterns.day_pattern} />
                      <FieldRow icon={Clock} label="Dominant time-of-day" value={patterns.dominant_time_of_day} />
                    </>
                  )}
                </div>

                {/* Monthly spend trend */}
                {monthly.length > 1 && (
                  <div className="md:col-span-2 mt-5">
                    {SECTION_HEAD("Monthly Spend Trend")}
                    <div className="h-32">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={monthly}>
                          <defs>
                            <linearGradient id="g_spend" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="#9b2c2c" stopOpacity={0.5} />
                              <stop offset="100%" stopColor="#9b2c2c" stopOpacity={0.04} />
                            </linearGradient>
                          </defs>
                          <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
                          <ChartTooltip formatter={(v) => fmtINR(v)} contentStyle={{ fontSize: 12 }} />
                          <Area type="monotone" dataKey="spend" stroke="#9b2c2c" fill="url(#g_spend)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === "transactions" && (
              <div className="text-xs">
                {tx.length === 0 && <div className="text-neutral-400 py-6 text-center">No transactions yet</div>}
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-widest text-neutral-400 border-b border-neutral-200">
                        <th className="text-left py-1.5 pr-2">Bill</th>
                        <th className="text-left py-1.5 pr-2">Date</th>
                        <th className="text-left py-1.5 pr-2">Store</th>
                        <th className="text-right py-1.5 pr-2">Amount</th>
                        <th className="text-right py-1.5 pr-2">Disc</th>
                        <th className="text-right py-1.5 pr-2">Earned</th>
                        <th className="text-right py-1.5">Redeem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tx.map((t, i) => (
                        <tr key={i} className="border-b border-neutral-100">
                          <td className="py-1.5 pr-2 font-mono text-[11px]">{t.bill_number}</td>
                          <td className="py-1.5 pr-2 text-neutral-600">{fmtDate(t.bill_date)}</td>
                          <td className="py-1.5 pr-2 text-neutral-600 truncate max-w-[140px]" title={t.store_name}>{t.store_name || "—"}</td>
                          <td className="py-1.5 pr-2 text-right font-medium">{fmtINR(t.net_amount)}</td>
                          <td className="py-1.5 pr-2 text-right text-neutral-500">{fmtINR(t.discount_amount)}</td>
                          <td className="py-1.5 pr-2 text-right text-teal-700">{fmtNum(t.points_earned)}</td>
                          <td className="py-1.5 text-right text-rose-700">{fmtNum(t.points_redeemed)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {tab === "points" && (
              <div className="text-xs">
                {ledger.length === 0 && <div className="text-neutral-400 py-6 text-center">No points ledger entries</div>}
                <div className="space-y-1">
                  {ledger.map((l, i) => (
                    <div key={i} className="flex items-center justify-between gap-2 p-2 border border-neutral-100 rounded">
                      <div className="flex-1 min-w-0">
                        <div className={`text-[10px] uppercase tracking-widest font-medium ${l.type === "earn" ? "text-teal-700" : l.type === "redeem" ? "text-rose-700" : "text-amber-700"}`}>{l.type}</div>
                        <div className="text-sm">{l.reason || "—"}</div>
                        <div className="text-[10px] text-neutral-400 mt-0.5">
                          {l.bill_number && <span className="font-mono mr-2">{l.bill_number}</span>}
                          {fmtDateTime(l.bill_date || l.created_at)}
                        </div>
                      </div>
                      <div className={`font-mono text-sm font-medium ${l.points >= 0 ? "text-teal-700" : "text-rose-700"}`}>
                        {l.points >= 0 ? "+" : ""}{fmtNum(l.points)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {tab === "stores" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  {SECTION_HEAD("Store Affinity")}
                  {stores.length === 0 && <div className="text-xs text-neutral-400">No store data</div>}
                  <div className="space-y-1">
                    {stores.map((s) => (
                      <div key={s.store_id} className="flex items-center justify-between p-2 border border-neutral-100 rounded text-xs">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{s.name}</div>
                          <div className="text-[10px] text-neutral-500">{s.code || ""} · {s.city || "—"}</div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className="font-mono">{fmtINR(s.spend)}</div>
                          <div className="text-[10px] text-neutral-400">{s.visits} visits</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  {SECTION_HEAD("Category Affinity")}
                  {cats.length === 0 && <div className="text-xs text-neutral-400">No item-level data on bills</div>}
                  {cats.length > 0 && (
                    <div className="h-44">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={cats} layout="vertical" margin={{ left: 10 }}>
                          <XAxis type="number" tick={{ fontSize: 10 }} hide />
                          <YAxis type="category" dataKey="category" tick={{ fontSize: 10 }} width={90} />
                          <ChartTooltip formatter={(v) => fmtINR(v)} contentStyle={{ fontSize: 12 }} />
                          <Bar dataKey="spend" fill="#525e88" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              </div>
            )}

            {tab === "nps" && (
              <div className="text-xs space-y-2">
                {nps.length === 0 && <div className="text-neutral-400 py-6 text-center">No NPS responses</div>}
                {nps.map((n, i) => {
                  const band = n.score >= 9 ? "promoter" : n.score >= 7 ? "passive" : "detractor";
                  const bandColor = band === "promoter" ? "text-teal-700 bg-teal-50 border-teal-200" : band === "passive" ? "text-amber-700 bg-amber-50 border-amber-200" : "text-rose-700 bg-rose-50 border-rose-200";
                  return (
                    <div key={i} className="border border-neutral-100 rounded p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-[10px] uppercase tracking-widest font-medium border rounded px-2 py-0.5 ${bandColor}`}>{band}</span>
                        <span className="font-display text-2xl">{n.score}</span>
                      </div>
                      {n.comment && <div className="text-neutral-700">"{n.comment}"</div>}
                      <div className="text-[10px] text-neutral-400 mt-1">{fmtDateTime(n.created_at)}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
