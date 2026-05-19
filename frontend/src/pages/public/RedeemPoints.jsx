export default function RedeemPoints() {
  return (
    <div className="max-w-[1100px] mx-auto px-6 lg:px-12 py-20" data-testid="page-redeem">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">REDEEM</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">Use them<br /><em className="font-light">your way.</em></h1>
      <div className="bg-white border border-black/10 p-12 grid md:grid-cols-3 gap-10 text-center">
        <div>
          <div className="font-display text-6xl kazo-text-burgundy mb-2">100</div>
          <div className="text-xs uppercase tracking-widest text-neutral-500">Minimum redemption</div>
        </div>
        <div>
          <div className="font-display text-6xl kazo-text-burgundy mb-2">₹0.25</div>
          <div className="text-xs uppercase tracking-widest text-neutral-500">Value per point</div>
        </div>
        <div>
          <div className="font-display text-6xl kazo-text-burgundy mb-2">365d</div>
          <div className="text-xs uppercase tracking-widest text-neutral-500">Points validity</div>
        </div>
      </div>
      <div className="mt-12 prose text-neutral-700 max-w-3xl">
        <p>Inform the store staff at billing or apply your points at checkout online. You'll receive an OTP on your registered mobile to authorise the redemption — your account, your control.</p>
        <p className="mt-4">Combine with eligible coupons during promotional periods for stacked savings.</p>
      </div>
    </div>
  );
}
