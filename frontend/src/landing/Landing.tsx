import { AudioLines, BadgeCheck, Clock, MapPin, ShieldCheck, Truck } from "lucide-react";

import coastal from "../assets/coastal-drive.jpg";
import mia from "../assets/mia-avatar.jpg";
import { Button } from "../ui/button";
import { BUSINESS } from "./business";
import { copyrightYear } from "./calendar";
import { Disclosure } from "./Disclosure";

const APP = "#/call";

const STEPS = [
  {
    n: "01",
    title: "Call Mia",
    body: "Tap the button and tell Mia where your car is going. No forms, no account.",
  },
  {
    n: "02",
    title: "Get your quote",
    body: "Mia checks both cities and prices open transport for your exact vehicle in seconds.",
  },
  {
    n: "03",
    title: "Transfer to an agent",
    body: "Ask Mia to try the transfer-to-agent demonstration. No real agent or booking service is available.",
  },
];
const FEATURES = [
  {
    icon: Truck,
    title: "Door-to-door open transport",
    body: "The most common, most affordable way to move a car across the country.",
  },
  {
    icon: Clock,
    title: "Quotes in under 3 minutes",
    body: "Mia answers instantly, any hour, so you never wait on hold for a price.",
  },
  {
    icon: ShieldCheck,
    title: "Real marketplace pricing",
    body: "Quotes use current rates from a nationwide car-carrier marketplace.",
  },
  {
    icon: MapPin,
    title: BUSINESS.serviceArea,
    body: "City-to-city routes from coast to coast, sedans to pickups.",
  },
];
const FAQ = [
  {
    q: "How much does it cost to ship a car?",
    a: "It depends on distance, vehicle size and season. Mia gives you an open-transport estimate for your route during the call.",
  },
  { q: "Is the quote binding?", a: "No. Mia gives an estimate, not a binding quote." },
  {
    q: "Do I need to create an account?",
    a: "No. Just call Mia from your browser. Your microphone is only used during the call.",
  },
  {
    q: "How long does a call take?",
    a: "Most quotes take two to three minutes. Calls end automatically after six minutes.",
  },
];

function CallCta({ label = "Get a quote from Mia" }: { label?: string }) {
  return (
    <Button
      asChild
      variant="action"
      size="lg"
      className="h-12 rounded-full px-6 font-mono text-xs font-semibold tracking-wider uppercase"
    >
      <a href={APP}>
        <AudioLines className="size-4" /> {label}
      </a>
    </Button>
  );
}

/** The customer-facing home page (from the Lovable redesign). The app itself is at #/call. */
export function Landing() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <header className="mia-hero">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <span className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Truck className="size-5 text-accent" /> {BUSINESS.name}
          </span>
          <div className="flex items-center gap-5 text-sm">
            <a href="#how" className="hidden opacity-75 hover:opacity-100 sm:inline">
              How it works
            </a>
            <a href="#faq" className="hidden opacity-75 hover:opacity-100 sm:inline">
              FAQ
            </a>
            <Button
              asChild
              variant="action"
              className="h-11 rounded-full px-5 font-mono text-xs font-semibold uppercase"
            >
              <a href={APP}>
                <AudioLines className="size-4" />
                Talk to Mia
              </a>
            </Button>
          </div>
        </nav>
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 pt-10 pb-20 lg:grid-cols-[1.1fr_1fr] lg:pt-16">
          <div>
            <p className="eyebrow text-accent">Nationwide auto transport</p>
            <h1 className="font-display mt-4 text-5xl leading-[1.02] font-semibold tracking-tight md:text-6xl">
              Ship your car anywhere in the US. Get the price in one call.
            </h1>
            <p className="mt-5 max-w-xl text-lg opacity-75">
              Mia, our AI voice assistant, estimates open transport for your vehicle and route in
              minutes. Explore a natural conversation in this academic demonstration.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <CallCta />
              <span className="flex items-center gap-2 text-sm opacity-70">
                <BadgeCheck className="size-4 text-accent" /> Free · No account needed
              </span>
            </div>
          </div>
          <div className="relative">
            <img
              src={coastal}
              alt="Car driving along a coastal highway"
              width={1600}
              height={900}
              className="aspect-[4/3] w-full rounded-2xl object-cover"
            />
            <div className="mia-voice-card absolute -bottom-6 left-4 flex items-center gap-3 rounded-2xl p-3 pr-5 sm:left-6">
              <img src={mia} alt="Mia" width={48} height={48} className="size-12 rounded-full object-cover" />
              <div>
                <p className="text-sm font-semibold">“Boston to Miami, 2020 Camry?”</p>
                <p className="mia-voice-muted font-mono text-[11px] uppercase">Mia · quoting live</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main>
        <section id="how" className="mx-auto max-w-6xl scroll-mt-4 px-6 py-20">
          <p className="eyebrow text-muted">How it works</p>
          <h2 className="font-display mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
            From conversation to estimate in three steps.
          </h2>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="rounded-2xl border border-line bg-surface p-6">
                <span className="font-mono text-xs text-accent">{s.n}</span>
                <h3 className="mt-4 text-lg font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm text-muted">{s.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-y border-line bg-surface">
          <div className="mx-auto grid max-w-6xl gap-8 px-6 py-16 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title}>
                <Icon className="size-6 text-accent" />
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm text-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="faq" className="mx-auto max-w-3xl scroll-mt-4 px-6 py-20">
          <p className="eyebrow text-muted">FAQ</p>
          <h2 className="font-display mt-3 text-3xl font-semibold tracking-tight">
            Questions, answered.
          </h2>
          <div className="mt-8 divide-y divide-line border-y border-line">
            {FAQ.map((f) => (
              <details key={f.q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                  {f.q}
                  <span className="text-muted transition group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 text-sm text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 pb-20">
          <div className="mia-hero flex flex-col items-start justify-between gap-6 rounded-2xl p-10 md:flex-row md:items-center">
            <div>
              <h2 className="font-display text-3xl font-semibold tracking-tight">
                Ready to move your car?
              </h2>
              <p className="mt-2 opacity-70">Get your price now. It takes about three minutes.</p>
            </div>
            <CallCta label="Call Mia now" />
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-6 px-6 py-10 text-sm text-muted md:grid-cols-[1fr_2fr]">
          <div>
            <p className="font-semibold text-ink">{BUSINESS.name}</p>
            <p className="mt-1">{BUSINESS.serviceArea}</p>
          </div>
          <Disclosure />
          <p className="border-t border-line pt-5 md:col-span-2">
            © {copyrightYear()} {BUSINESS.name}
          </p>
        </div>
      </footer>
    </div>
  );
}
