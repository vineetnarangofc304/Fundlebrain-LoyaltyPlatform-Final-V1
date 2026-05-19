import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, StatusPill, SectionHeading, CHART_SERIES } from "../_shared";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from "recharts";

export default function CampaignDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/campaign-dashboard").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;

  const totalRev = data.all.reduce((s, c) => s + c.revenue_generated, 0);
  const totalSent = data.all.reduce((s, c) => s + c.sent, 0);
  const totalRedeemed = data.all.reduce((s, c) => s + c.redeemed, 0);
  const overallROI = totalRev > 0 && totalSent > 0 ? (totalRev / (totalSent * 0.5)).toFixed(1) : "N/A";

  return (
    <div data-testid="campaign-dashboard">
      <PageHeader title="Campaign Performance" subtitle="CHANNEL & ROI ANALYTICS · LIVE" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Campaigns" value={fmtNum(data.all.length)} accent="indigo" testid="kpi-camp-total" />
          <KPICard label="Total Sent" value={fmtNum(totalSent)} accent="teal" testid="kpi-camp-sent" />
          <KPICard label="Redeemed" value={fmtNum(totalRedeemed)} accent="emerald" testid="kpi-camp-redeemed" />
          <KPICard label="Revenue Generated" value={fmtINR(totalRev)} hint={`ROI ~${overallROI}x`} accent="burgundy" testid="kpi-camp-rev" />
        </div>

        <div className="chart-card p-5" data-accent="indigo">
          <SectionHeading eyebrow="BY CHANNEL" title="Channel performance breakdown" accent="indigo" />
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.by_channel}>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="channel" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
              <Tooltip formatter={(v) => fmtINR(v)} />
              <Bar dataKey="revenue" radius={[3, 3, 0, 0]}>
                {data.by_channel.map((_, i) => <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <table className="data-table mt-4">
            <thead><tr><th>Channel</th><th className="text-right">Campaigns</th><th className="text-right">Sent</th><th className="text-right">Delivered</th><th className="text-right">Redeemed</th><th className="text-right">Revenue</th></tr></thead>
            <tbody>
              {data.by_channel.map((r, i) => (
                <tr key={r.channel}>
                  <td>
                    <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: CHART_SERIES[i % CHART_SERIES.length] }} />
                    {r.channel}
                  </td>
                  <td className="text-right font-mono">{r.campaigns}</td>
                  <td className="text-right font-mono">{fmtNum(r.sent)}</td>
                  <td className="text-right font-mono">{fmtNum(r.delivered)}</td>
                  <td className="text-right font-mono">{fmtNum(r.redeemed)}</td>
                  <td className="text-right font-mono">{fmtINR(r.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="ALL CAMPAIGNS" title="Sorted by revenue" accent="burgundy" />
          <table className="data-table">
            <thead><tr><th>Name</th><th>Channels</th><th>Status</th><th>Launched</th><th className="text-right">Sent</th><th className="text-right">CTR</th><th className="text-right">Redeem Rate</th><th className="text-right">Revenue</th></tr></thead>
            <tbody>
              {data.all.map((c) => {
                const ctr = c.delivered ? ((c.clicked / c.delivered) * 100).toFixed(1) : "0";
                const rr = c.sent ? ((c.redeemed / c.sent) * 100).toFixed(2) : "0";
                return (
                  <tr key={c.id}>
                    <td className="font-medium">{c.name}</td>
                    <td className="text-xs">{(c.channels || []).join(", ")}</td>
                    <td><StatusPill status={c.status} /></td>
                    <td className="text-xs">{fmtDate(c.launched_at)}</td>
                    <td className="text-right font-mono">{fmtNum(c.sent)}</td>
                    <td className="text-right font-mono">{ctr}%</td>
                    <td className="text-right font-mono">{rr}%</td>
                    <td className="text-right font-mono">{fmtINR(c.revenue_generated)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
