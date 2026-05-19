export default function EarnPoints() {
  return (
    <div className="max-w-[1100px] mx-auto px-6 lg:px-12 py-20" data-testid="page-earn">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">EARN</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">Earn on<br /><em className="font-light">every purchase.</em></h1>
      <div className="grid md:grid-cols-2 gap-8">
        {[
          { h: "₹1 = 1 Point", b: "The default earn rate. Quote your mobile number at billing." },
          { h: "Tier multipliers", b: "Gold: 1.25x · Platinum: 1.5x · Diamond: 2x" },
          { h: "Birthday & Anniversary", b: "Bonus points credited automatically on the day." },
          { h: "Referrals", b: "Earn 250 points for every friend who shops with your code." },
          { h: "Surprise category boosts", b: "Watch for 2x or 3x category-specific events during sale season." },
          { h: "Welcome bonus", b: "100 points the moment you sign up." },
        ].map((c) => (
          <div key={c.h} className="border border-black/10 bg-white p-8">
            <h3 className="font-display text-2xl mb-2">{c.h}</h3>
            <p className="text-sm text-neutral-600 leading-relaxed">{c.b}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
