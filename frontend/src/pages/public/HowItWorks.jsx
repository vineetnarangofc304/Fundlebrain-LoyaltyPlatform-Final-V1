export default function HowItWorks() {
  const steps = [
    { n: "01", h: "Sign up free", b: "Register at any KAZO store with your mobile number — or online at kazo.com. Instant 100-point welcome bonus." },
    { n: "02", h: "Quote at checkout", b: "Simply share your mobile number when billing. Points accrue automatically based on your tier multiplier." },
    { n: "03", h: "Receive an OTP", b: "For privacy, you'll receive an OTP whenever points are redeemed against your account." },
    { n: "04", h: "Climb the tiers", b: "Cross spend thresholds and your tier upgrades automatically. Larger birthday bonuses, faster earn rates." },
    { n: "05", h: "Redeem your way", b: "1 point = ₹0.25. Use 100 or more points to discount your next purchase, online or in-store." },
  ];
  return (
    <div className="max-w-[1300px] mx-auto px-6 lg:px-12 py-20" data-testid="page-how">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">HOW IT WORKS</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-16">Simple, by<br /><em className="font-light">design.</em></h1>
      <div className="space-y-12">
        {steps.map((s) => (
          <div key={s.n} className="grid lg:grid-cols-[140px_1fr] gap-6 border-b border-black/10 pb-12 last:border-0">
            <div className="font-display text-6xl kazo-text-champagne" style={{ fontWeight: 300 }}>{s.n}</div>
            <div>
              <h3 className="font-display text-3xl mb-3">{s.h}</h3>
              <p className="text-neutral-600 leading-relaxed text-lg max-w-2xl">{s.b}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
