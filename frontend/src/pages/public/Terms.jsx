export default function Terms() {
  return (
    <div className="max-w-[900px] mx-auto px-6 lg:px-12 py-20" data-testid="page-terms">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">TERMS & CONDITIONS</div>
      <h1 className="editorial-headline text-5xl mb-10">Programme terms.</h1>
      <div className="prose text-neutral-700 leading-relaxed space-y-4">
        <ol className="space-y-3 list-decimal pl-5">
          <li>Membership is free and open to anyone aged 18 or above, residing in India.</li>
          <li>Points earned have no cash equivalent and are non-transferable.</li>
          <li>Points expire 365 days from the date earned.</li>
          <li>1 point = ₹0.25; minimum redemption is 100 points.</li>
          <li>KAZO reserves the right to modify the programme rules with advance notice.</li>
          <li>Fraud, misuse or abuse will lead to immediate termination of membership and forfeiture of points.</li>
          <li>Tier qualification is based on rolling 12-month spend.</li>
          <li>Programme communications via WhatsApp/SMS/Email constitute consented marketing under the Indian DPDP Act 2023.</li>
        </ol>
        <p className="text-sm text-neutral-500 mt-12">Last updated: January 2026</p>
      </div>
    </div>
  );
}
