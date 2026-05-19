import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "../_shared";
import { fmtNum, fmtINR } from "@/lib/format";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend, Area, AreaChart } from "recharts";

const TIER_ACCENT = {
  silver: "slate",
  gold: "amber",
  platinum: "indigo",
  diamond: "burgundy",
};

export default function LoyaltyDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/loyalty-dashboard").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  return (
    <div data-testid="loyalty-dashboard">
      <PageHeader title="Loyalty Dashboard" subtitle="POINTS & TIERS HEALTH · LIVE" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.tiers.map((t) => (
            <KPICard
              key={t.tier}
              label={`${t.tier?.toUpperCase()} TIER`}
              value={fmtNum(t.count)}
              hint={`avg ${fmtINR(t.avg_spend)} · ${fmtNum(t.total_points)} pts`}
              accent={TIER_ACCENT[t.tier?.toLowerCase()] || "slate"}
              testid={`tier-${t.tier}`}
            />
          ))}
        </div>

        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="POINTS FLOW" title="Issued vs Redeemed · last 30 days" accent="burgundy" />
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={data.points_trend}>
              <defs>
                <linearGradient id="issuedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#571326" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="redeemedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#C7A76D" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#C7A76D" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="bonusGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1E3A8A" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#1E3A8A" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="issued" stroke="#571326" strokeWidth={2.5} fill="url(#issuedGrad)" name="Issued" />
              <Area type="monotone" dataKey="redeemed" stroke="#C7A76D" strokeWidth={2.5} fill="url(#redeemedGrad)" name="Redeemed" />
              <Area type="monotone" dataKey="bonus" stroke="#1E3A8A" strokeWidth={2} fill="url(#bonusGrad)" name="Bonus" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
