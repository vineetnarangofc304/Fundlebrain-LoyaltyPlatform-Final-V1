/* Update Mobile Number — fully migrate a customer's history to a new mobile number.
   Re-keys every bill / points ledger / coupon / OTP / message / NPS / ticket from the
   old number to the new one (so all lifetime analytics follow the customer), while the
   OLD number is preserved on the record for display/audit. */
import { useState } from "react";
import api from "@/lib/api";
import { fmtMoney2, fmtNum } from "@/lib/format";
import { PageHeader } from "../_shared";
import { Pill } from "./_shared";
import { Search, Smartphone, ArrowRight, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function UpdateMobile() {
  const [oldMobile, setOldMobile] = useState("");
  const [customer, setCustomer] = useState(null);   // matched customer for old number
  const [searched, setSearched] = useState(false);
  const [newMobile, setNewMobile] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);        // migration result summary

  const onlyDigits = (s) => String(s || "").replace(/\D/g, "");

  const search = async (e) => {
    e?.preventDefault?.();
    const q = onlyDigits(oldMobile);
    if (!q) return;
    setResult(null);
    setCustomer(null);
    try {
      const r = await api.get(`/customers`, { params: { q, limit: 5 } });
      const items = r.data?.items || [];
      // Prefer an exact last-10-digit match.
      const exact = items.find((c) => onlyDigits(c.mobile).slice(-10) === q.slice(-10));
      const picked = exact || items[0] || null;
      setCustomer(picked);
      setSearched(true);
    } catch {
      toast.error("Search failed");
    }
  };

  const migrate = async () => {
    const oldM = onlyDigits(customer?.mobile || oldMobile);
    const newM = onlyDigits(newMobile);
    if (!oldM || !newM) { toast.error("Enter both old and new mobile numbers"); return; }
    if (oldM.slice(-10) === newM.slice(-10)) { toast.error("Old and new numbers are identical"); return; }
    if (!reason.trim()) { toast.error("A reason is required"); return; }
    setBusy(true);
    try {
      const r = await api.post("/support-desk/update-mobile", {
        old_mobile: oldM, new_mobile: newM, reason: reason.trim(),
      });
      setResult(r.data);
      toast.success(`Mobile updated → ${r.data.new_mobile}`);
      // Reset the editable inputs but keep the result on screen.
      setNewMobile("");
      setReason("");
      setCustomer(null);
      setOldMobile("");
      setSearched(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Update failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="sd-update-mobile-page">
      <PageHeader title="Update Mobile Number" subtitle="SUPPORT DESK · IDENTITY" />
      <div className="p-8 space-y-6">
        {/* Step 1 — find the customer by current mobile */}
        <div className="chart-card p-5" data-accent="indigo">
          <form onSubmit={search} className="flex items-end gap-3 flex-wrap">
            <div className="flex-1 min-w-[260px]">
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Current (old) mobile number</label>
              <input
                value={oldMobile}
                onChange={(e) => setOldMobile(e.target.value)}
                className="k-input w-full"
                inputMode="numeric"
                placeholder="9999000001"
                data-testid="sd-mobile-old-search-input"
              />
            </div>
            <button type="submit" className="k-btn kazo-bg-burgundy text-white" data-testid="sd-mobile-search-btn">
              <Search className="w-3.5 h-3.5" /> Find customer
            </button>
          </form>

          {searched && !customer && (
            <div className="text-sm text-rose-700 mt-4" data-testid="sd-mobile-not-found">
              No customer found for that mobile number.
            </div>
          )}

          {customer && (
            <div className="mt-5 border border-black/10 bg-neutral-50 p-4" data-testid="sd-mobile-customer">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="font-display text-xl">{customer.name || "Unnamed"}</span>
                <span className="font-mono text-sm text-neutral-700">{customer.mobile}</span>
                {customer.tier && <Pill tone="info">{String(customer.tier).toUpperCase()}</Pill>}
                {customer.is_active === false && <Pill tone="danger">Deactivated</Pill>}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500">Lifetime Spend</div>
                  <div className="font-mono">{fmtMoney2(customer.lifetime_spend)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500">Visits</div>
                  <div className="font-mono">{fmtNum(customer.visit_count || 0)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500">Points</div>
                  <div className="font-mono">{fmtNum(customer.points_balance || 0)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500">City</div>
                  <div>{customer.city || "—"}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Step 2 — enter the new mobile + reason and migrate */}
        {customer && (
          <div className="chart-card p-5" data-accent="burgundy" data-testid="sd-mobile-migrate-form">
            <h3 className="font-display text-xl mb-1">Migrate to a new number</h3>
            <p className="text-sm text-neutral-600 mb-4">
              All bills, points, coupons and history will move to the new number. The old
              number ({customer.mobile}) is kept on the record for reference.
            </p>
            <div className="grid md:grid-cols-2 gap-4 items-end">
              <div>
                <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">New mobile number</label>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-neutral-500 whitespace-nowrap">{customer.mobile}</span>
                  <ArrowRight className="w-4 h-4 text-neutral-400 shrink-0" />
                  <input
                    value={newMobile}
                    onChange={(e) => setNewMobile(e.target.value)}
                    className="k-input w-full"
                    inputMode="numeric"
                    placeholder="New 10-digit mobile"
                    data-testid="sd-mobile-new-input"
                  />
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Reason (required)</label>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="k-input w-full"
                  placeholder="e.g. Customer changed number"
                  data-testid="sd-mobile-reason-input"
                />
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button
                onClick={migrate}
                disabled={busy || !newMobile.trim() || !reason.trim()}
                className="k-btn kazo-bg-burgundy text-white disabled:opacity-50"
                data-testid="sd-mobile-migrate-btn"
              >
                <Smartphone className="w-3.5 h-3.5" /> {busy ? "Migrating…" : "Update & migrate history"}
              </button>
            </div>
          </div>
        )}

        {/* Result summary */}
        {result && (
          <div className="chart-card p-5" data-accent="teal" data-testid="sd-mobile-result">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              <h3 className="font-display text-xl">Migration complete</h3>
            </div>
            <div className="text-sm mb-4">
              <span className="font-mono">{result.old_mobile}</span>
              <ArrowRight className="w-4 h-4 inline mx-2 text-neutral-400" />
              <span className="font-mono font-medium">{result.new_mobile}</span>
              {result.customer_name && <span className="text-neutral-500 ml-2">· {result.customer_name}</span>}
            </div>
            <table className="w-full text-sm max-w-md">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-1.5 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Record type</th>
                  <th className="py-1.5 px-2 text-[10px] uppercase tracking-widest text-neutral-500 text-right">Rows re-keyed</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.rekeyed || {}).map(([k, v]) => (
                  <tr key={k} className="border-b border-black/5">
                    <td className="py-1.5 px-2 capitalize">{k.replace(/_/g, " ")}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{v < 0 ? "—" : fmtNum(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
