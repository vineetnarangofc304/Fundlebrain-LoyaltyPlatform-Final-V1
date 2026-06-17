import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { fmtMoney2, fmtNum, fmtDate, tierClass } from "@/lib/format";
import { LogOut, Search, Sparkles, Plus, Minus, Gift } from "lucide-react";

export default function StoreOps() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobile, setMobile] = useState("");
  const [customer, setCustomer] = useState(null);
  const [profile, setProfile] = useState(null);
  const [otp, setOtp] = useState(null);
  const [couponCode, setCouponCode] = useState("");
  const [couponResult, setCouponResult] = useState(null);
  const [pointsAmt, setPointsAmt] = useState(0);
  const [billAmt, setBillAmt] = useState(0);

  const search = async () => {
    try {
      const r = await api.get(`/customers/search/by-mobile/${mobile}`);
      setCustomer(r.data);
      const d = await api.get(`/customers/${r.data.id}`);
      setProfile(d.data);
      toast.success(`${r.data.name || mobile} loaded`);
    } catch (e) {
      setCustomer(null); setProfile(null);
      toast.error("Customer not found");
    }
  };

  const issueOtp = async () => {
    if (!customer) return;
    try {
      const r = await api.post("/pos/issue-otp", { mobile: customer.mobile, purpose: "redeem" });
      setOtp(r.data.demo_otp);
      toast.success(`OTP sent: ${r.data.demo_otp} (demo)`);
    } catch (e) { toast.error("OTP failed"); }
  };

  const validateCoupon = async () => {
    try {
      const r = await api.post(`/coupons/validate-by-code/${couponCode}`, null, { params: { customer_mobile: customer?.mobile, bill_amount: billAmt } });
      setCouponResult(r.data);
      if (r.data.valid) toast.success(`Valid · ${r.data.coupon.name}`);
      else toast.error(r.data.reason);
    } catch (e) { toast.error("Validation failed"); }
  };

  const awardPoints = async () => {
    if (!customer || pointsAmt <= 0) return;
    try {
      await api.post(`/customers/${customer.id}/award-points`, null, { params: { points: pointsAmt, note: `Store ops · ${user.email}` } });
      toast.success(`Awarded ${pointsAmt} points`);
      search();
      setPointsAmt(0);
    } catch (e) { toast.error("Failed"); }
  };

  return (
    <div className="min-h-screen kazo-bg-cream" data-testid="store-ops-page">
      <header className="kazo-bg-black text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-display text-2xl tracking-tight">KAZO</span>
          <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">Store Ops · Powered by Fundle</span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/admin" className="text-xs text-white/70 hover:text-white">Admin →</Link>
          <span className="text-xs text-white/70">{user?.name}</span>
          <button onClick={async () => { await logout(); navigate("/store/login"); }} className="text-xs text-white/70 hover:text-white flex items-center gap-1" data-testid="store-logout"><LogOut className="w-3.5 h-3.5" /> Logout</button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6 space-y-5">
        {/* Search bar */}
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CUSTOMER LOOKUP</div>
          <div className="flex gap-2">
            <input className="k-input" placeholder="Enter mobile number" value={mobile} onChange={(e) => setMobile(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} data-testid="store-search-mobile" />
            <button className="k-btn kazo-bg-burgundy" onClick={search} data-testid="store-search-btn"><Search className="w-4 h-4" /> Search</button>
          </div>
        </div>

        {customer && (
          <>
            <div className="bg-white border border-black/10 p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="font-display text-3xl mb-1">{customer.name || customer.mobile}</h2>
                  <div className="text-sm text-neutral-500 font-mono">{customer.mobile} · {customer.email}</div>
                </div>
                <span className={tierClass(customer.tier)}>{customer.tier?.toUpperCase()}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Points Balance" value={fmtNum(customer.points_balance)} />
                <Stat label="Lifetime Spend" value={fmtMoney2(customer.lifetime_spend)} />
                <Stat label="Visits" value={fmtNum(customer.visit_count)} />
                <Stat label="Last Visit" value={fmtDate(customer.last_visit_at)} />
              </div>
            </div>

            <div className="grid lg:grid-cols-2 gap-4">
              {/* OTP & Points */}
              <div className="bg-white border border-black/10 p-5">
                <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">REDEMPTION OTP</div>
                <button className="k-btn k-btn-outline w-full justify-center" onClick={issueOtp} data-testid="issue-otp-btn"><Sparkles className="w-4 h-4" /> Send OTP to {customer.mobile}</button>
                {otp && <div className="mt-3 text-center"><div className="text-[11px] uppercase text-neutral-500 mb-1">DEMO OTP</div><div className="font-mono text-3xl kazo-text-burgundy">{otp}</div></div>}
              </div>

              <div className="bg-white border border-black/10 p-5">
                <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">AWARD POINTS</div>
                <div className="flex gap-2">
                  <input type="number" className="k-input" placeholder="Points" value={pointsAmt || ""} onChange={(e) => setPointsAmt(parseInt(e.target.value) || 0)} data-testid="store-points-input" />
                  <button className="k-btn kazo-bg-burgundy" onClick={awardPoints} data-testid="store-award-btn"><Plus className="w-4 h-4" /> Award</button>
                </div>
              </div>

              {/* Coupon validate */}
              <div className="bg-white border border-black/10 p-5 lg:col-span-2">
                <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">VALIDATE COUPON</div>
                <div className="flex gap-2">
                  <input className="k-input" placeholder="Coupon code" value={couponCode} onChange={(e) => setCouponCode(e.target.value.toUpperCase())} data-testid="store-coupon-input" />
                  <input className="k-input" type="number" placeholder="Bill amount ₹" value={billAmt || ""} onChange={(e) => setBillAmt(parseFloat(e.target.value) || 0)} data-testid="store-bill-input" />
                  <button className="k-btn kazo-bg-burgundy" onClick={validateCoupon} data-testid="store-validate-btn"><Gift className="w-4 h-4" /> Validate</button>
                </div>
                {couponResult && (
                  <div className={`mt-3 p-3 ${couponResult.valid ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"} text-sm`}>
                    {couponResult.valid ? <>✓ Valid · {couponResult.coupon.name} · {couponResult.coupon.coupon_type === "percentage" ? `${couponResult.coupon.discount_value}% off` : `₹${couponResult.coupon.discount_value} off`}</> : <>✗ {couponResult.reason}</>}
                  </div>
                )}
              </div>

              {/* Recent transactions */}
              {profile && (
                <div className="bg-white border border-black/10 p-5 lg:col-span-2">
                  <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">RECENT TRANSACTIONS</div>
                  <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                    <table className="data-table">
                      <thead><tr><th>Bill #</th><th>Date</th><th className="text-right">Net</th><th className="text-right">Points</th></tr></thead>
                      <tbody>
                        {profile.transactions.slice(0, 10).map((t) => (
                          <tr key={t.id}>
                            <td className="font-mono text-xs">{t.bill_number}</td>
                            <td className="text-xs">{fmtDate(t.bill_date)}</td>
                            <td className="text-right font-mono">{fmtMoney2(t.net_amount)}</td>
                            <td className="text-right font-mono">+{t.points_earned}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="border border-black/10 p-3">
      <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">{label}</div>
      <div className="font-mono text-xl">{value}</div>
    </div>
  );
}
