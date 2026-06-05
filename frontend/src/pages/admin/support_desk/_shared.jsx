/* SupportDeskShared — small helpers used across all Support Desk pages. */
import { useState } from "react";

/** Mobile-input + Search bar — common pattern across audit pages. */
export function MobileSearchBar({ value, onChange, onSearch, placeholder = "Mobile number", testid }) {
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSearch?.(); }}
      className="flex items-end gap-3 flex-wrap"
      data-testid={testid}
    >
      <div className="flex-1 min-w-[240px]">
        <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">
          {placeholder}
        </label>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="9999000001"
          className="k-input w-full"
          inputMode="numeric"
          maxLength={15}
          data-testid={`${testid}-mobile-input`}
        />
      </div>
      <button type="submit" className="k-btn kazo-bg-burgundy text-white" data-testid={`${testid}-search-btn`}>
        Search
      </button>
    </form>
  );
}

/** Compact info pill, e.g. "Reversed", "Active", "Unsubscribed". */
export function Pill({ tone = "neutral", children }) {
  const tones = {
    neutral: "bg-neutral-100 text-neutral-700",
    success: "bg-emerald-100 text-emerald-800",
    warning: "bg-amber-100 text-amber-800",
    danger: "bg-rose-100 text-rose-800",
    info: "bg-sky-100 text-sky-800",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${tones[tone] || tones.neutral}`}>
      {children}
    </span>
  );
}

/** Confirm-with-reason modal used by every "destructive" support action. */
export function ConfirmReasonModal({ open, title, description, onConfirm, onCancel, confirmLabel = "Confirm" }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  if (!open) return null;
  const submit = async () => {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await onConfirm(reason.trim());
      setReason("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" data-testid="confirm-modal">
      <div className="bg-white shadow-2xl max-w-md w-full p-6 border border-black/10">
        <h3 className="font-display text-xl mb-2">{title}</h3>
        {description && <p className="text-sm text-neutral-600 mb-4">{description}</p>}
        <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          className="k-input w-full"
          placeholder="e.g. Customer complained — bill was returned"
          data-testid="confirm-reason-input"
        />
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onCancel} className="k-btn k-btn-outline" data-testid="confirm-cancel">Cancel</button>
          <button
            onClick={submit}
            disabled={!reason.trim() || busy}
            className="k-btn kazo-bg-burgundy text-white disabled:opacity-50"
            data-testid="confirm-submit"
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
