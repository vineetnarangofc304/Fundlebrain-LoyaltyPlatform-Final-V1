import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_PALETTE } from "./_shared";
import { fmtMoney2, fmtNum, fmtDate, fmtDateTime, tierClass } from "@/lib/format";
import AIInsightStrip from "./AIInsightStrip";
import DrillDownModal from "./DrillDownModal";
import { toast } from "sonner";
import {
  ArrowLeft, Plus, Minus, Gift, MessageSquare, Sparkles, Calendar, MapPin,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
  BarChart, Bar, Cell,
} from "recharts";

const SEG_COLOR = {
  Champions: "#047857",
  Loyalists: "#0E7C7B",
  "Big Spenders": "#1E3A8A",
  Promising: "#2563EB",
  "New Customers": "#0EA5E9",
  "Potential Loyalists": "#0891B2",
  "Cant Lose Them": "#B45309",
  "At Risk": "#9F1239",
  "About to Sleep": "#A16207",
  Hibernating: "#475569",
  Lost: "#6B7280",
};

export default function CustomerDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pointsModal, setPointsModal] = useState(null);
  const [pointsAmt, setPointsAmt] = useState(0);
  const [note, setNote] = useState("");
  const [drill, setDrill] = useState(null);
  const [jumpQ, setJumpQ] = useState("");

  const jumpToCustomer = async () => {
    const q = jumpQ.trim();
    if (!q) return;
    try {
      const r = await api.get("/customers", { params: { q, limit: 1, skip: 0 } });
      const list = r.data?.items || r.data?.customers || r.data?.rows || (Array.isArray(r.data) ? r.data : []);
      const cid = list[0]?.id;
      if (cid) { setJumpQ(""); navigate(`/admin/customers/${cid}`); }
      else toast.error("No customer found for that search");
    } catch { toast.error("Search failed"); }
  };

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/dashboard/customer-360/${id}`);
      setData(r.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const doPoints = async () => {
    try {
      const path = pointsModal === "award" ? "award-points" : "deduct-points";
      await api.post(`/customers/${id}/${path}`, null, { params: { points: pointsAmt, note } });
      toast.success(`${pointsModal === "award" ? "Awarded" : "Deducted"} ${pointsAmt} points`);
      setPointsModal(null);
      setPointsAmt(0);
      setNote("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  if (loading && !data) return <div className="p-10 text-neutral-500">Loading customer 360…</div>;
  if (!data) return null;

  const c = data.customer;
  const lt = data.lifetime;
  const rfm = data.rfm;
  const segColor = SEG_COLOR[rfm.segment] || "#571326";

  const aiPayload = {
    customer: { id: c.id, name: c.name, tier: c.tier, city: c.city },
    rfm,
    lifetime: lt,
    monthly_spend_last_12: data.monthly_spend.slice(-12),
    top_categories: data.category_affinity.slice(0, 5),
    top_stores: data.store_affinity.slice(0, 3),
  };

  return (
    <div data-testid="customer-detail-page">
      <PageHeader
        title={c.name || c.mobile}
        subtitle="CUSTOMER 360 · LIVE COMPUTED"
        actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <input
                className="k-input k-input-sm !pl-8 w-56"
                placeholder="Jump to customer (mobile / name)…"
                value={jumpQ}
                onChange={(e) => setJumpQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && jumpToCustomer()}
                data-testid="cust-jump-search"
              />
              <Sparkles className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-400" />
            </div>
            <button className="k-btn kazo-bg-burgundy text-white k-btn-sm" onClick={jumpToCustomer} data-testid="cust-jump-go">Go</button>
            <Link to="/admin/customers" className="k-btn k-btn-outline k-btn-sm">
              <ArrowLeft className="w-3.5 h-3.5" /> All customers
            </Link>
          </div>
        }
      />

      <div className="p-8 space-y-6">
        {/* AI report */}
        <AIInsightStrip
          dashboardKey={`customer_360_${id}`}
          payload={aiPayload}
          title="Customer Intelligence Report"
        />

        {/* Hero — identity + RFM badge */}
        <div className="bg-white border border-black/10 grid lg:grid-cols-[2fr_3fr] gap-0">
          {/* Left: identity */}
          <div className="p-6 border-r border-black/5 relative overflow-hidden">
            <div
              className="absolute top-0 left-0 right-0 h-1"
              style={{ background: segColor }}
            />
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <span className={tierClass(c.tier)}>{c.tier?.toUpperCase()}</span>
              <span
                className="pill"
                style={{ background: `${segColor}1A`, color: segColor, borderColor: `${segColor}40` }}
                data-testid="cust-rfm-segment"
              >
                {rfm.segment}
              </span>
              <span
                className={`pill pill-${c.churn_risk === "high" ? "danger" : c.churn_risk === "medium" ? "warning" : "success"}`}
              >
                {c.churn_risk} churn risk
              </span>
            </div>
            <div className="font-display text-3xl mb-1" data-testid="cust-name">
              {c.name || c.mobile}
            </div>
            <div className="text-sm text-neutral-600 font-mono mb-4" data-testid="cust-contact">
              {c.mobile} · {c.email || "—"}
              {c.previous_mobile && (
                <span className="ml-2 text-xs text-amber-700" data-testid="cust-prev-mobile">
                  (was {c.previous_mobile})
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-y-3 gap-x-4 text-base">
              <div className="text-neutral-500 flex items-center gap-1.5"><MapPin className="w-3.5 h-3.5" /> City</div>
              <div className="font-medium">{c.city || "—"}</div>
              <div className="text-neutral-500 flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Birthday</div>
              <div className="font-medium">{c.birthday || "—"}</div>
              <div className="text-neutral-500">First purchase</div>
              <div className="font-medium">{fmtDate(lt.first_purchase)}</div>
              <div className="text-neutral-500">Last purchase</div>
              <div className="font-medium">{fmtDate(lt.last_purchase)}</div>
              <div className="text-neutral-500">Days since visit</div>
              <div className="font-mono font-medium">{rfm.recency_days}</div>
            </div>
          </div>

          {/* Right: RFM score + lifetime KPIs */}
          <div className="p-6 grid gap-4">
            <div>
              <SectionHeading eyebrow="RFM SCORE" title={`${rfm.score} · ${rfm.segment}`} accent="indigo" />
              <div className="grid grid-cols-3 gap-3">
                <RFMTile label="Recency" letter="R" score={rfm.r} value={`${rfm.recency_days}d`} color="#0E7C7B" />
                <RFMTile label="Frequency" letter="F" score={rfm.f} value={`${rfm.frequency} visits`} color="#1E3A8A" />
                <RFMTile label="Monetary" letter="M" score={rfm.m} value={fmtMoney2(rfm.monetary)} color="#B45309" />
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KPICard label="Lifetime Spend" value={fmtMoney2(lt.paid ?? lt.spend)} accent="burgundy" testid="cust-lts" />
              <KPICard label="Points Balance" value={fmtNum(c.points_balance)} accent="amber" testid="cust-points" />
              <KPICard label="Visits" value={fmtNum(lt.visits)} accent="teal" testid="cust-visits" />
              <KPICard label="Avg basket" value={fmtMoney2(lt.aov)} accent="indigo" testid="cust-aov" />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          <button className="k-btn k-btn-outline k-btn-sm" onClick={() => setPointsModal("award")} data-testid="award-points-btn">
            <Plus className="w-3.5 h-3.5" /> Award points
          </button>
          <button className="k-btn k-btn-outline k-btn-sm" onClick={() => setPointsModal("deduct")} data-testid="deduct-points-btn">
            <Minus className="w-3.5 h-3.5" /> Deduct points
          </button>
          <button className="k-btn k-btn-outline k-btn-sm" onClick={() => navigate("/admin/coupons")}>
            <Gift className="w-3.5 h-3.5" /> Issue coupon
          </button>
          <button className="k-btn k-btn-outline k-btn-sm" onClick={() => navigate("/admin/tickets")}>
            <MessageSquare className="w-3.5 h-3.5" /> Raise ticket
          </button>
          <button
            className="k-btn k-btn-outline k-btn-sm"
            onClick={() => setDrill({
              title: "All transactions",
              subtitle: "DRILLDOWN",
              collection: "transactions",
              filter: { customer_mobile: c.mobile },
              sort: [["bill_date", -1]],
              columns: [
                { key: "bill_number", label: "Bill #", mono: true },
                { key: "bill_date", label: "Date", render: (v) => fmtDate(v) },
                { key: "store_name", label: "Store", render: (v) => v || "—" },
                { key: "net_amount_before_tax", label: "Net (pre-tax)", align: "right", render: (v, r) => fmtMoney2(v ?? r.net_amount) },
                { key: "tax_amount", label: "Tax", align: "right", render: (v) => fmtMoney2(v) },
                { key: "discount_amount", label: "Discount", align: "right", render: (v) => fmtMoney2(v) },
                { key: "bill_amount", label: "Bill Amount", align: "right", render: (_v, r) => fmtMoney2(Number(r.net_amount_before_tax ?? r.net_amount ?? 0) + Number(r.tax_amount || 0)) },
                { key: "net_amount", label: "Net", align: "right", render: (v) => fmtMoney2(v) },
                { key: "points_earned", label: "Pts +", align: "right" },
                { key: "points_redeemed", label: "Pts −", align: "right" },
                { key: "coupon_code", label: "Coupon" },
              ],
            })}
            data-testid="cust-drill-all-txns"
          >
            View all {fmtNum(lt.visits)} transactions
          </button>
        </div>

        {/* Monthly spend chart */}
        <div className="chart-card p-5">
          <SectionHeading
            eyebrow="REVENUE TIMELINE"
            title="Monthly spend & visits"
            accent="burgundy"
          />
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={data.monthly_spend}>
              <defs>
                <linearGradient id="gradSpend" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#571326" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="month" stroke="#64748b" fontSize={11} />
              <YAxis yAxisId="l" stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} />
              <YAxis yAxisId="r" orientation="right" stroke="#1E3A8A" fontSize={11} />
              <Tooltip formatter={(v, n) => (n === "spend" ? fmtMoney2(v) : v)} />
              <Area yAxisId="l" type="monotone" dataKey="spend" stroke="#571326" strokeWidth={2} fill="url(#gradSpend)" name="Spend" />
              <Bar yAxisId="r" dataKey="visits" fill="#1E3A8A" opacity={0.7} name="Visits" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Affinity */}
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5" data-testid="cust-category-affinity">
            <SectionHeading eyebrow="CATEGORY AFFINITY" title="What she buys" accent="indigo" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.category_affinity} layout="vertical" margin={{ left: 30 }}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} />
                <YAxis dataKey="category" type="category" stroke="#64748b" fontSize={11} width={90} />
                <Tooltip formatter={(v) => fmtMoney2(v)} />
                <Bar dataKey="spend" fill="#1E3A8A">
                  {data.category_affinity.map((_, i) => (
                    <Cell key={i} fill={`hsl(${214 + i * 18}, 60%, ${35 + i * 4}%)`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5" data-testid="cust-store-affinity">
            <SectionHeading eyebrow="STORE AFFINITY" title="Where she shops" accent="teal" />
            <table className="data-table">
              <thead><tr><th>Store</th><th>City</th><th className="text-right">Visits</th><th className="text-right">Spend</th></tr></thead>
              <tbody>
                {data.store_affinity.map((s) => (
                  <tr key={s.store_id}>
                    <td>{s.name}</td>
                    <td>{s.city}</td>
                    <td className="text-right font-mono">{s.visits}</td>
                    <td className="text-right font-mono">{fmtMoney2(s.spend)}</td>
                  </tr>
                ))}
                {data.store_affinity.length === 0 && (
                  <tr><td colSpan={4} className="text-center py-6 text-neutral-500">No store activity</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent transactions + points ledger + NPS */}
        <div className="bg-white border border-black/10 p-5">
          <SectionHeading eyebrow="RECENT TRANSACTIONS" title="Last 10 bills" accent="burgundy" />
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Bill #</th><th>Date</th><th className="text-right">Net ₹</th><th className="text-right">Pts +</th><th>Payment</th><th>Coupon</th></tr></thead>
              <tbody>
                {data.recent_transactions.map((t) => (
                  <tr key={t.id}>
                    <td className="font-mono text-xs">{t.bill_number}</td>
                    <td className="text-xs">{fmtDate(t.bill_date)}</td>
                    <td className="text-right font-mono">{fmtMoney2(t.net_amount)}</td>
                    <td className="text-right font-mono text-emerald-700">+{t.points_earned}</td>
                    <td><span className="pill pill-neutral">{t.payment_mode}</span></td>
                    <td className="text-xs">{t.coupon_code || "—"}</td>
                  </tr>
                ))}
                {data.recent_transactions.length === 0 && (
                  <tr><td colSpan={6} className="text-center py-6 text-neutral-500">No transactions</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <SectionHeading eyebrow="POINTS LEDGER" title="Earn · burn timeline" accent="amber" />
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {data.points_ledger.map((l) => (
                <div key={l.id} className="flex items-center justify-between border-b border-black/5 pb-2 text-sm">
                  <div>
                    <div className="font-medium uppercase text-xs tracking-widest">{l.type}</div>
                    <div className="text-xs text-neutral-500">
                      {fmtDateTime(l.created_at)} · {l.note || l.reference_type || "—"}
                    </div>
                  </div>
                  <div className={`font-mono ${l.points >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                    {l.points >= 0 ? "+" : ""}{l.points}
                  </div>
                </div>
              ))}
              {data.points_ledger.length === 0 && <div className="text-sm text-neutral-500">No ledger entries</div>}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <SectionHeading eyebrow="VOICE OF CUSTOMER" title="NPS history" accent="rose" />
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {data.nps_history.length === 0 && <div className="text-sm text-neutral-500">No NPS responses yet</div>}
              {data.nps_history.map((n) => (
                <div key={n.id} className="border-b border-black/5 py-2 flex justify-between">
                  <div>
                    <div className="font-medium text-sm">
                      <span className={`pill pill-${n.sentiment === "promoter" ? "success" : n.sentiment === "detractor" ? "danger" : "warning"}`}>
                        {n.sentiment}
                      </span>
                      <span className="ml-2 font-mono text-xs">{n.score}/10</span>
                    </div>
                    <div className="text-xs text-neutral-500 mt-1">{n.feedback || "—"}</div>
                  </div>
                  <div className="text-xs text-neutral-400 font-mono">{fmtDate(n.created_at)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Points modal */}
      {pointsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setPointsModal(null)}>
          <div className="bg-white p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="points-modal">
            <h3 className="font-display text-2xl mb-4">{pointsModal === "award" ? "Award" : "Deduct"} Points</h3>
            <div className="space-y-3">
              <input type="number" placeholder="Points amount" className="k-input" value={pointsAmt} onChange={(e) => setPointsAmt(parseInt(e.target.value) || 0)} data-testid="points-amount-input" />
              <input placeholder="Note (optional)" className="k-input" value={note} onChange={(e) => setNote(e.target.value)} data-testid="points-note-input" />
              <div className="flex gap-2 justify-end">
                <button className="k-btn k-btn-ghost" onClick={() => setPointsModal(null)}>Cancel</button>
                <button className="k-btn kazo-bg-burgundy" onClick={doPoints} data-testid="points-confirm-btn">Confirm</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {drill && <DrillDownModal open={true} onClose={() => setDrill(null)} {...drill} />}
    </div>
  );
}

function RFMTile({ label, letter, score, value, color }) {
  return (
    <div
      className="border p-3 relative overflow-hidden"
      style={{ borderColor: `${color}40`, background: `${color}08` }}
    >
      <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500">{label}</div>
      <div className="flex items-end justify-between mt-1">
        <div className="font-display text-2xl" style={{ color }}>{letter}{score}</div>
        <div className="text-xs text-neutral-500 font-mono">{value}</div>
      </div>
      {/* Quintile dots */}
      <div className="flex gap-0.5 mt-2">
        {[1, 2, 3, 4, 5].map((q) => (
          <span
            key={q}
            className="h-1 flex-1 rounded-sm"
            style={{ background: q <= score ? color : "#e5e7eb" }}
          />
        ))}
      </div>
    </div>
  );
}
