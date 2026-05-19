import { useEffect, useState } from "react";
import api from "@/lib/api";
import { ChevronDown } from "lucide-react";

export default function FAQs() {
  const [faqs, setFaqs] = useState([]);
  const [open, setOpen] = useState(0);
  useEffect(() => { api.get("/public/faqs").then((r) => setFaqs(r.data)); }, []);
  return (
    <div className="max-w-[1000px] mx-auto px-6 lg:px-12 py-20" data-testid="page-faqs">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">FAQs</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">We've got<br /><em className="font-light">your answers.</em></h1>
      <div className="border-t border-black/10">
        {faqs.map((f, i) => (
          <div key={i} className="border-b border-black/10">
            <button className="w-full flex items-center justify-between text-left py-6" onClick={() => setOpen(open === i ? -1 : i)} data-testid={`faq-toggle-${i}`}>
              <span className="font-display text-xl pr-6">{f.q}</span>
              <ChevronDown className={`w-5 h-5 transition-transform ${open === i ? "rotate-180" : ""}`} />
            </button>
            {open === i && <div className="pb-6 text-neutral-700 leading-relaxed text-base">{f.a}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
