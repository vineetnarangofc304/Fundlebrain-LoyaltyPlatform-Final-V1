export default function Rewards() {
  const rewards = [
    { h: "Welcome 100 Points", b: "Instantly credited on sign-up." },
    { h: "Birthday Bonanza", b: "Up to 2000 points on your special day." },
    { h: "Anniversary Surprise", b: "Bonus points on your KAZO anniversary." },
    { h: "Festive Hampers", b: "Curated boxes for Platinum and Diamond members." },
    { h: "Private Previews", b: "First look at new collections — 72 hours early." },
    { h: "Personal Stylist", b: "Diamond-tier dedicated stylist sessions." },
    { h: "Free Alterations", b: "Complimentary at all stores for Platinum & Diamond." },
    { h: "Surprise Drops", b: "Curated exclusive coupons throughout the year." },
  ];
  return (
    <div className="max-w-[1300px] mx-auto px-6 lg:px-12 py-20" data-testid="page-rewards">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">REWARDS</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-16">Beyond<br /><em className="font-light">the points.</em></h1>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {rewards.map((r) => (
          <div key={r.h} className="border border-black/10 bg-white p-7">
            <h3 className="font-display text-xl mb-2">{r.h}</h3>
            <p className="text-sm text-neutral-600 leading-relaxed">{r.b}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
