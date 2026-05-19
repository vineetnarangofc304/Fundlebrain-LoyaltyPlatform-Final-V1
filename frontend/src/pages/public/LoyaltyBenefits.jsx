const rows = [
  { feature: "Earn rate", silver: "1x", gold: "1.25x", platinum: "1.5x", diamond: "2x" },
  { feature: "Welcome bonus", silver: "100 pts", gold: "200 pts", platinum: "300 pts", diamond: "500 pts" },
  { feature: "Birthday bonus", silver: "200 pts", gold: "500 pts", platinum: "1000 pts", diamond: "2000 pts" },
  { feature: "Anniversary bonus", silver: "200 pts", gold: "500 pts", platinum: "1000 pts", diamond: "2000 pts" },
  { feature: "Tier qualification", silver: "₹0", gold: "₹25,000+", platinum: "₹75,000+", diamond: "₹1,50,000+" },
  { feature: "Free alterations", silver: "—", gold: "—", platinum: "✓", diamond: "✓" },
  { feature: "Early collection access", silver: "—", gold: "24h", platinum: "48h", diamond: "72h" },
  { feature: "Private VIP previews", silver: "—", gold: "—", platinum: "✓", diamond: "✓" },
  { feature: "Personal stylist", silver: "—", gold: "—", platinum: "—", diamond: "✓" },
  { feature: "Festive hampers", silver: "—", gold: "—", platinum: "✓", diamond: "✓ Premium" },
];

export default function LoyaltyBenefits() {
  return (
    <div className="max-w-[1300px] mx-auto px-6 lg:px-12 py-20" data-testid="page-benefits">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">THE BENEFITS</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">Compare<br /><em className="font-light">your tier.</em></h1>
      <div className="overflow-x-auto bg-white border border-black/10">
        <table className="data-table min-w-[800px]">
          <thead>
            <tr>
              <th className="!bg-black !text-white">FEATURE</th>
              <th className="!bg-black !text-white text-center">SILVER</th>
              <th className="!bg-black !text-white text-center">GOLD</th>
              <th className="!bg-black !text-white text-center">PLATINUM</th>
              <th className="!bg-black !text-white text-center">DIAMOND</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.feature}>
                <td className="font-medium">{r.feature}</td>
                <td className="text-center">{r.silver}</td>
                <td className="text-center">{r.gold}</td>
                <td className="text-center">{r.platinum}</td>
                <td className="text-center font-semibold kazo-text-burgundy">{r.diamond}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
