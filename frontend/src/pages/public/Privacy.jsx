export default function Privacy() {
  return (
    <div className="max-w-[900px] mx-auto px-6 lg:px-12 py-20" data-testid="page-privacy">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">PRIVACY POLICY</div>
      <h1 className="editorial-headline text-5xl mb-10">Your privacy, our principle.</h1>
      <div className="prose text-neutral-700 leading-relaxed space-y-4">
        <p>This Privacy Policy explains how KAZO collects, uses, stores, and protects information about you when you join the KAZO Rewards programme. By signing up, you agree to the practices described here.</p>
        <h3 className="font-display text-2xl mt-8">What we collect</h3>
        <p>Mobile number, email (optional), name, city, birthday, anniversary, and transaction details from your purchases at KAZO stores or kazo.com.</p>
        <h3 className="font-display text-2xl mt-8">How we use it</h3>
        <p>To credit and redeem points, send programme communications (offers, birthday wishes, tier upgrades), analyse aggregated trends to improve our offering, and provide customer support.</p>
        <h3 className="font-display text-2xl mt-8">Your rights</h3>
        <p>You can request access, correction, or deletion of your data at any time by writing to <a href="mailto:privacy@kazo.com" className="kazo-text-burgundy">privacy@kazo.com</a>.</p>
        <p className="text-sm text-neutral-500 mt-12">Last updated: January 2026</p>
      </div>
    </div>
  );
}
