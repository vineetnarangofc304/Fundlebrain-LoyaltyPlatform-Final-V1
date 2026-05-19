import { Link } from "react-router-dom";

export default function AboutProgram() {
  return (
    <div className="max-w-[1100px] mx-auto px-6 lg:px-12 py-20" data-testid="page-about">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">ABOUT THE PROGRAMME</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-8">A members-only<br /><em className="font-light">universe.</em></h1>
      <div className="prose max-w-3xl text-neutral-700 leading-relaxed text-lg">
        <p>KAZO Rewards is the official loyalty programme for the modern Indian woman who lives in style. We built it as a quiet thank-you — points that gather softly, privileges that arrive on the right occasion, and a private door into KAZO's most-anticipated drops.</p>
        <p className="mt-6">There are no annual fees. No fine print buried in legalese. Just a programme that rewards what you already love doing — dressing beautifully.</p>
      </div>
      <div className="grid md:grid-cols-3 gap-8 mt-16">
        {[
          { h: "Free to join", b: "No fee, no waitlist. Sign up in 30 seconds at any KAZO store or online." },
          { h: "Universally accepted", b: "Earn and redeem in any of our 25+ stores across India and on kazo.com." },
          { h: "Designed in editorial", b: "Personal style scores, look books and stylist messages — by us, for you." },
        ].map((c) => (
          <div key={c.h} className="border border-black/10 p-8 bg-white">
            <h3 className="font-display text-2xl mb-2">{c.h}</h3>
            <p className="text-sm text-neutral-600 leading-relaxed">{c.b}</p>
          </div>
        ))}
      </div>
      <Link to="/" className="mt-12 inline-block k-btn kazo-bg-burgundy text-white uppercase tracking-widest text-xs">Join now</Link>
    </div>
  );
}
