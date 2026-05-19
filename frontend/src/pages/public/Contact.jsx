import { Mail, Phone, MapPin } from "lucide-react";

export default function Contact() {
  return (
    <div className="max-w-[1100px] mx-auto px-6 lg:px-12 py-20" data-testid="page-contact">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">CUSTOMER SUPPORT</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">We're<br /><em className="font-light">here for you.</em></h1>
      <div className="grid md:grid-cols-3 gap-6">
        <div className="bg-white border border-black/10 p-8">
          <Mail className="w-5 h-5 kazo-text-burgundy mb-4" />
          <h3 className="font-display text-xl mb-2">Email</h3>
          <a href="mailto:rewards@kazo.com" className="text-sm text-neutral-700 hover:kazo-text-burgundy">rewards@kazo.com</a>
        </div>
        <div className="bg-white border border-black/10 p-8">
          <Phone className="w-5 h-5 kazo-text-burgundy mb-4" />
          <h3 className="font-display text-xl mb-2">Phone</h3>
          <a href="tel:+911800123456" className="text-sm text-neutral-700">1800 123 456 · Mon–Sat, 10AM–8PM</a>
        </div>
        <div className="bg-white border border-black/10 p-8">
          <MapPin className="w-5 h-5 kazo-text-burgundy mb-4" />
          <h3 className="font-display text-xl mb-2">Head Office</h3>
          <p className="text-sm text-neutral-700">KAZO Fashion Pvt. Ltd.<br />New Delhi, India</p>
        </div>
      </div>
    </div>
  );
}
