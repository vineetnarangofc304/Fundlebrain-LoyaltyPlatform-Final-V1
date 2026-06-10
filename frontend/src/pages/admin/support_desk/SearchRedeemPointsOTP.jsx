/* Search Redeem Points OTP — audit search.
   Lets support agents look up OTP sessions for redeem-points by mobile / bill / otp_id / date range.
   Mirrors newu.fundlezone.com /supportdesk/searchrdmptsdtl */
import { useState } from "react";
import api from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { PageHeader } from "../_shared";
import { MobileSearchBar, Pill } from "./_shared";
import { Search, Calendar } from "lucide-react";
import { toast } from "sonner";

export default function SearchRedeemPointsOTP() {
  const [mobile, setMobile] = useState("");
  const [otpId, setOtpId] = useState("");
  const [billNumber, setBillNumber] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    setLoading(true);
    try {
      const params = {};
      if (mobile) params.mobile = mobile;
      if (otpId) params.otp_id = otpId;
      if (billNumber) params.bill_number = billNumber;
      if (startDate && endDate) { params.start_date = startDate; params.end_date = endDate; }
      const r = await api.get("/support-desk/redeem-points-otp", { params });
      setRows(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Search failed");
    } finally { setLoading(false); }
  };

  return (
    <div data-testid="sd-redeem-points-otp-page">
      <PageHeader title="Search Redeem Points OTP" subtitle="SUPPORT DESK · AUDIT" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Mobile</label>
              <input value={mobile} onChange={(e) => setMobile(e.target.value)} className="k-input w-full" placeholder="9999000001" data-testid="sd-rpo-mobile" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">OTP ID</label>
              <input value={otpId} onChange={(e) => setOtpId(e.target.value)} className="k-input w-full" data-testid="sd-rpo-otpid" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Bill Number</label>
              <input value={billNumber} onChange={(e) => setBillNumber(e.target.value)} className="k-input w-full" data-testid="sd-rpo-bill" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Start date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="k-input w-full" data-testid="sd-rpo-start" />
            </div>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">End date</label>
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="k-input w-full" data-testid="sd-rpo-end" />
              </div>
              <button onClick={search} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="sd-rpo-search">
                <Search className="w-3.5 h-3.5" /> {loading ? "…" : "Search"}
              </button>
            </div>
          </div>
        </div>

        {rows !== null && (
          <div className="chart-card p-5 overflow-x-auto" data-accent="indigo">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-xl">Results · {rows.length}</h3>
            </div>
            {rows.length === 0 ? (
              <div className="text-sm text-neutral-500 py-8 text-center">No OTP sessions matched.</div>
            ) : (
              <table className="w-full text-sm" data-testid="sd-rpo-results">
                <thead className="border-b border-black/10 text-left">
                  <tr>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">When</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">OTP</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Bill</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Points</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.otp_id || i} className="border-b border-black/5 hover:bg-amber-50/40">
                      <td className="py-2 px-2 text-xs text-neutral-600">{fmtDateTime(r.created_at)}</td>
                      <td className="py-2 px-2 font-mono">{r.mobile}</td>
                      <td className="py-2 px-2 font-mono text-base font-bold kazo-text-burgundy tracking-widest" data-testid="sd-rpo-otp">{r.otp || "—"}</td>
                      <td className="py-2 px-2 font-mono">{r.bill_number || "—"}</td>
                      <td className="py-2 px-2 font-mono text-right">{r.points ?? "—"}</td>
                      <td className="py-2 px-2">
                        {r.verified ? <Pill tone="success">Verified</Pill> : <Pill tone="warning">Pending</Pill>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
