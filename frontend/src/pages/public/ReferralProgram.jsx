export default function ReferralProgram() {
  return (
    <div className="max-w-[1100px] mx-auto px-6 lg:px-12 py-20" data-testid="page-referral">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">REFER & EARN</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">Share style.<br /><em className="font-light">Earn together.</em></h1>
      <div className="grid md:grid-cols-2 gap-12 items-start">
        <div className="bg-white border border-black/10 p-10">
          <div className="text-xs uppercase tracking-widest text-neutral-500 mb-2">YOU EARN</div>
          <div className="font-display text-6xl kazo-text-burgundy mb-2">250 pts</div>
          <p className="text-sm text-neutral-600 mb-8">For every friend who completes their first purchase using your code.</p>
          <div className="text-xs uppercase tracking-widest text-neutral-500 mb-2">YOUR FRIEND GETS</div>
          <div className="font-display text-6xl kazo-text-burgundy">100 pts</div>
          <p className="text-sm text-neutral-600 mt-2">Welcome bonus on sign-up using your referral.</p>
        </div>
        <div className="prose text-neutral-700">
          <h3 className="font-display text-3xl mb-4">How to share</h3>
          <ol className="space-y-2 list-decimal pl-5">
            <li>Log in to your KAZO account.</li>
            <li>Visit the Referrals page to grab your unique code.</li>
            <li>Share it via WhatsApp, SMS, or email.</li>
            <li>When your friend shops, both of you earn points.</li>
          </ol>
          <p className="mt-6 text-sm text-neutral-500">No cap on referrals. Be generous — your wardrobe will thank you.</p>
        </div>
      </div>
    </div>
  );
}
