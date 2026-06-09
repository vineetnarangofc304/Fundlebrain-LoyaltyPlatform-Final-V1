/* Search Redeem Coupon OTP — same pattern as SearchRedeemPointsOTP. */
import { useState } from "react";
import api from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { PageHeader } from "../_shared";
import { Pill } from "./_shared";
import { Search } from "lucide-react";
import { toast } from "sonner";

export default function SearchRedeemCouponOTP() {
  const [mobile, setMobile] = useState("");
  const [otpId, setOtpId] = useState("");
  const [couponCode, setCouponCode] = useState("");
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
      if (couponCode) params.coupon_code = couponCode;
      if (startDate && endDate) { params.start_date = startDate; params.end_date = endDate; }
      const r = await api.get("/support-desk/redeem-coupon-otp", { params });
      setRows(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Search failed");
    } finally { setLoading(false); }
  };

  return (
    <div data-testid="sd-redeem-coupon-otp-page">
      <PageHeader title="Search Redeem Coupon OTP" subtitle="SUPPORT DESK · AUDIT" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Mobile</label>
              <input value={mobile} onChange={(e) => setMobile(e.target.value)} className="k-input w-full" data-testid="sd-rco-mobile" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">OTP ID</label>
              <input value={otpId} onChange={(e) => setOtpId(e.target.value)} className="k-input w-full" data-testid="sd-rco-otpid" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Coupon Code</label>
              <input value={couponCode} onChange={(e) => setCouponCode(e.target.value)} className="k-input w-full" data-testid="sd-rco-code" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Start date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="k-input w-full" data-testid="sd-rco-start" />
            </div>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">End date</label>
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="k-input w-full" data-testid="sd-rco-end" />
              </div>
              <button onClick={search} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="sd-rco-search">
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
              <table className="w-full text-sm" data-testid="sd-rco-results">
                <thead className="border-b border-black/10 text-left">
                  <tr>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">When</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">OTP ID</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Coupon</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.otp_id || i} className="border-b border-black/5 hover:bg-amber-50/40">
                      <td className="py-2 px-2 text-xs text-neutral-600">{fmtDateTime(r.created_at)}</td>
                      <td className="py-2 px-2 font-mono">{r.mobile}</td>
                      <td className="py-2 px-2 font-mono text-xs">{r.otp_id}</td>
                      <td className="py-2 px-2 font-mono">{r.coupon_code || "—"}</td>
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
