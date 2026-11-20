"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Maximize, Minimize, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { BrandStyle, useBranding } from "@/components/branding";
import { AXIS_PROPS, BAR_RADIUS, ChartTooltip, GRID_PROPS, Legend, SERIES } from "@/components/charts";
import { ErrorBlock } from "@/components/common";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { useOrgKey, useProperty, useScenarioResult, useScenarios } from "@/hooks/queries";
import { api, rawFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { mult, pct, stripDemo, TYPE_LABELS, usd, usdShort } from "@/lib/format";
import type { Property, StoredResult } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Waterfall {
  saved: boolean;
  config: { lp_share: number; pref_rate: number };
  result: {
    lp: { contributed: number; distributed: number; irr: number | null; multiple: number | null };
    gp: { contributed: number; distributed: number; irr: number | null; multiple: number | null; promote: number };
  };
}

function useFullscreen() {
  const on = useSyncExternalStore(
    (cb) => {
      document.addEventListener("fullscreenchange", cb);
      return () => document.removeEventListener("fullscreenchange", cb);
    },
    () => !!document.fullscreenElement,
    () => false,
  );
  const toggle = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen?.().catch(() => {});
  }, []);
  return { on, toggle };
}

function useLogoUrl(version: number | null | undefined, enabled: boolean) {
  const org = useOrgKey();
  const q = useQuery({
    queryKey: [org, "branding-logo", version],
    queryFn: async () => {
      const r = await rawFetch("/api/org/branding/logo");
      return r.ok ? URL.createObjectURL(await r.blob()) : null;
    },
    enabled,
    staleTime: Infinity,
  });
  return enabled ? (q.data ?? null) : null;
}

function Big({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border bg-card p-6">
      <div className="text-sm font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-2 text-4xl font-semibold tabular tracking-tight xl:text-5xl">{value}</div>
      {sub && <div className="mt-1 text-base text-muted-foreground">{sub}</div>}
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-6 border-b py-3 text-xl last:border-0", strong && "font-semibold")}>
      <span className={strong ? "" : "text-muted-foreground"}>{label}</span>
      <span className="tabular">{value}</span>
    </div>
  );
}

function SlideTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-8">
      <h2 className="text-4xl font-semibold tracking-tight">{children}</h2>
      {sub && <p className="mt-2 text-lg text-muted-foreground">{sub}</p>}
    </div>
  );
}

function buildSlides(p: Property, r: StoredResult, presenter: string, brand: { name: string | null; logo: string | null }, wf: Waterfall | undefined, showRisk: boolean) {
  const m = r.metrics;
  const su = r.sources_and_uses;
  const where = [p.address, p.city, p.state].filter(Boolean).join(", ");
  const size = [p.units ? `${p.units.toLocaleString()} units` : null, p.rentable_sf ? `${p.rentable_sf.toLocaleString()} SF` : null].filter(Boolean).join(" · ");
  const cash = r.annual.map((y) => ({ label: `Yr ${y.year}`, noi: y.noi, cash: y.btcf }));
  const slides: { key: string; title: string; body: React.ReactNode }[] = [];

  slides.push({
    key: "cover",
    title: "Cover",
    body: (
      <div className="flex h-full flex-col justify-center">
        <div className="mb-10 flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element -- blob URL */}
          {brand.logo && <img src={brand.logo} alt="" className="max-h-14 max-w-56 object-contain" />}
          {brand.name ? <span className="text-2xl font-semibold">{brand.name}</span> : !brand.logo && <Logo />}
        </div>
        <div className="flex items-center gap-3 text-lg font-medium uppercase tracking-[0.2em] text-muted-foreground">
          <span className="h-1 w-10 rounded-full bg-accent" aria-hidden />
          {TYPE_LABELS[p.property_type] ?? p.property_type} investment
        </div>
        <h1 className="mt-3 max-w-5xl text-6xl font-semibold leading-tight tracking-tight xl:text-7xl">{stripDemo(p.name)}</h1>
        <p className="mt-5 text-2xl text-muted-foreground">{[where, size].filter(Boolean).join(" · ")}</p>
        <div className="mt-12 flex flex-wrap gap-x-12 gap-y-4 text-xl">
          <div>
            <div className="text-sm uppercase tracking-wide text-muted-foreground">Purchase price</div>
            <div className="mt-1 text-3xl font-semibold tabular">{usdShort(su.purchase_price)}</div>
          </div>
          <div>
            <div className="text-sm uppercase tracking-wide text-muted-foreground">Levered IRR</div>
            <div className="mt-1 text-3xl font-semibold tabular">{pct(m.irr_levered, 1)}</div>
          </div>
          <div>
            <div className="text-sm uppercase tracking-wide text-muted-foreground">Equity multiple</div>
            <div className="mt-1 text-3xl font-semibold tabular">{mult(m.equity_multiple_levered)}</div>
          </div>
        </div>
        <p className="mt-16 text-base text-muted-foreground">Presented by {presenter} · {new Date().toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}</p>
      </div>
    ),
  });

  slides.push({
    key: "summary",
    title: "Investment summary",
    body: (
      <>
        <SlideTitle sub="Base case, calculated by the Axiom engine from the stated assumptions.">Investment summary</SlideTitle>
        <div className="grid grid-cols-2 gap-5 lg:grid-cols-3">
          <Big label="Purchase price" value={usdShort(su.purchase_price)} sub={m.price_per_unit ? `${usd(m.price_per_unit)} per unit` : m.price_per_sf ? `${usd(m.price_per_sf)} per SF` : undefined} />
          <Big label="Going-in cap rate" value={pct(m.going_in_cap_rate)} sub={`Exit cap ${pct(m.exit_cap_rate)}`} />
          <Big label="Year-1 NOI" value={usdShort(m.noi_year1)} sub={m.expense_ratio_year1 !== null ? `Expense ratio ${pct(m.expense_ratio_year1, 1)}` : undefined} />
          <Big label="Levered IRR" value={pct(m.irr_levered, 1)} sub={`Unlevered ${pct(m.irr_unlevered, 1)}`} />
          <Big label="Equity multiple" value={mult(m.equity_multiple_levered)} sub={`Profit ${usdShort(m.profit_levered)}`} />
          <Big label="Year-1 DSCR" value={m.dscr_year1 === null ? "All cash" : mult(m.dscr_year1)} sub={m.ltv !== null ? `LTV ${pct(m.ltv, 1)}` : undefined} />
        </div>
      </>
    ),
  });

  slides.push({
    key: "cash",
    title: "Cash flow",
    body: (
      <>
        <SlideTitle sub={`${r.annual.length}-year hold. Hover a bar for exact figures.`}>Income and cash flow</SlideTitle>
        <div className="mb-3">
          <Legend
            items={[
              { label: "Net operating income", color: SERIES[0] },
              { label: "Cash flow to equity", color: SERIES[1] },
            ]}
          />
        </div>
        <div className="h-[52vh]">
          <ResponsiveContainer>
            <BarChart data={cash} barCategoryGap="22%" barGap={2}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey="label" {...AXIS_PROPS} tick={{ ...AXIS_PROPS.tick, fontSize: 15 }} />
              <YAxis {...AXIS_PROPS} tick={{ ...AXIS_PROPS.tick, fontSize: 14 }} tickFormatter={(v) => usdShort(v)} width={80} axisLine={false} />
              <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={usd} />} />
              <Bar dataKey="noi" name="Net operating income" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={56} />
              <Bar dataKey="cash" name="Cash flow to equity" fill={SERIES[1]} radius={BAR_RADIUS} maxBarSize={56} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </>
    ),
  });

  slides.push({
    key: "capital",
    title: "Capital and exit",
    body: (
      <>
        <SlideTitle>Capital stack and exit</SlideTitle>
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xl font-semibold">Sources</h3>
            {su.senior_loan > 0 && <Row label="Senior loan" value={usd(su.senior_loan)} />}
            {su.preferred_equity > 0 && <Row label="Preferred equity" value={usd(su.preferred_equity)} />}
            <Row label="Common equity" value={usd(su.common_equity)} />
            <Row label="Total" value={usd(su.total_sources)} strong />
          </div>
          <div>
            <h3 className="mb-2 text-xl font-semibold">Exit in year {r.exit.exit_year}</h3>
            <Row label={`Sale price at a ${pct(r.exit.exit_cap_rate)} cap`} value={usd(r.exit.gross_sale_price)} />
            <Row label="Selling costs" value={usd(-r.exit.selling_costs)} />
            {r.exit.loan_payoff > 0 && <Row label="Loan payoff" value={usd(-r.exit.loan_payoff)} />}
            <Row label="Net proceeds to equity" value={usd(r.exit.net_proceeds_to_equity)} strong />
          </div>
        </div>
      </>
    ),
  });

  if (wf?.saved) {
    slides.push({
      key: "split",
      title: "Investor returns",
      body: (
        <>
          <SlideTitle sub={`${pct(wf.config.pref_rate, 0)} preferred return, then promote tiers. Investors (LP) contribute ${pct(wf.config.lp_share, 0)} of the equity.`}>
            Investor and sponsor returns
          </SlideTitle>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {(["lp", "gp"] as const).map((k) => {
              const s = wf.result[k];
              return (
                <div key={k} className="rounded-xl border bg-card p-8">
                  <div className="text-lg font-medium text-muted-foreground">{k === "lp" ? "Investors (LP)" : "Sponsor (GP)"}</div>
                  <div className="mt-3 text-5xl font-semibold tabular">{pct(s.irr, 1)} IRR</div>
                  <div className="mt-2 text-2xl tabular">{mult(s.multiple)} equity multiple</div>
                  <div className="mt-6 text-lg text-muted-foreground tabular">
                    Put in {usdShort(s.contributed)} · get back {usdShort(s.distributed)}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ),
    });
  }

  if (showRisk) {
    const factors = r.risk?.factors ?? [];
    const flags = r.warnings ?? [];
    slides.push({
      key: "risk",
      title: "Key considerations",
      body: (
        <>
          <SlideTitle sub="From Axiom's risk screen and assumption checks.">Key considerations</SlideTitle>
          <ul className="space-y-4 text-2xl leading-snug">
            {factors.length + flags.length === 0 && <li>No screening flags were triggered by the base case.</li>}
            {factors.map((f) => (
              <li key={f.factor} className="flex gap-3">
                <span className="mt-3 size-2 shrink-0 rounded-full bg-accent" aria-hidden />
                {f.message}
              </li>
            ))}
            {flags.map((f) => (
              <li key={f.field + f.message} className="flex gap-3">
                <span className="mt-3 size-2 shrink-0 rounded-full bg-muted-foreground" aria-hidden />
                Assumption to note: {f.message}
              </li>
            ))}
          </ul>
        </>
      ),
    });
  }
  return slides;
}

export default function PresentPage() {
  const router = useRouter();
  const { status } = useAuth();
  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);
  // Wait for the session before asking for data (a direct link or refresh starts signed-out for a moment).
  if (status !== "authenticated")
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        <span className="mr-3 size-2 animate-ping rounded-full bg-accent" /> Preparing presentation…
      </div>
    );
  return <Presentation />;
}

function Presentation() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me } = useAuth();
  const org = useOrgKey();
  const property = useProperty(id);
  const scenarios = useScenarios(id);
  const base = scenarios.data?.find((s) => s.is_base) ?? scenarios.data?.[0];
  const result = useScenarioResult(base?.id);
  const wf = useQuery({ queryKey: [org, "waterfall", id], queryFn: () => api<Waterfall>(`/api/properties/${id}/waterfall`), retry: false });
  const branding = useBranding();
  const logo = useLogoUrl(branding.data?.logo_version, !!branding.data?.has_logo);
  const fs = useFullscreen();
  const [index, setIndex] = useState(0);
  const [showRisk, setShowRisk] = useState(true);

  const slides =
    property.data && result.data && me
      ? buildSlides(property.data, result.data, me.user.name, { name: branding.data?.brand_name ?? null, logo }, wf.data, showRisk)
      : [];
  const count = slides.length;
  const current = Math.min(index, Math.max(count - 1, 0));
  const exit = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    router.push(`/deals/${id}`);
  }, [router, id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (["ArrowRight", "PageDown", " ", "Enter"].includes(e.key)) {
        e.preventDefault();
        setIndex((i) => Math.min(i + 1, count - 1));
      } else if (["ArrowLeft", "PageUp", "Backspace"].includes(e.key)) {
        e.preventDefault();
        setIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Home") setIndex(0);
      else if (e.key === "End") setIndex(count - 1);
      else if (e.key.toLowerCase() === "f") fs.toggle();
      else if (e.key === "Escape" && !document.fullscreenElement) exit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, fs, exit]);

  const error = property.error ?? scenarios.error ?? result.error;
  if (error)
    return (
      <div className="mx-auto max-w-xl p-10">
        <ErrorBlock error={error} />
        <Button asChild variant="outline" className="mt-4">
          <Link href="/deals">Back to deals</Link>
        </Button>
      </div>
    );
  if (!count)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        <span className="mr-3 size-2 animate-ping rounded-full bg-accent" /> Preparing presentation…
      </div>
    );

  const slide = slides[current];
  const demo = property.data?.is_demo;
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <BrandStyle />
      <main className="relative flex-1 overflow-y-auto px-[6vw] py-[6vh]" aria-roledescription="slide" aria-label={`${slide.title}, slide ${current + 1} of ${count}`}>
        {slide.body}
        {demo && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-hidden>
            <span className="-rotate-[20deg] whitespace-nowrap text-5xl font-bold tracking-widest text-destructive/10 xl:text-7xl">FOR DEMONSTRATION ONLY</span>
          </div>
        )}
      </main>
      <footer className="flex items-center gap-3 border-t px-4 py-2 text-sm text-muted-foreground">
        <Button size="icon-sm" variant="ghost" onClick={exit} aria-label="Exit presentation" title="Exit (Esc)">
          <X />
        </Button>
        <span className="hidden truncate sm:inline">{stripDemo(property.data?.name ?? "")}</span>
        <div className="mx-auto flex items-center gap-2">
          <Button size="icon-sm" variant="ghost" onClick={() => setIndex(Math.max(current - 1, 0))} disabled={current === 0} aria-label="Previous slide">
            <ChevronLeft />
          </Button>
          <div className="flex gap-1.5" role="tablist" aria-label="Slides">
            {slides.map((s, i) => (
              <button
                key={s.key}
                type="button"
                role="tab"
                aria-selected={i === current}
                aria-label={s.title}
                title={s.title}
                onClick={() => setIndex(i)}
                className={cn("h-2 rounded-full transition-all", i === current ? "w-6 bg-accent" : "w-2 bg-muted-foreground/30 hover:bg-muted-foreground/60")}
              />
            ))}
          </div>
          <Button size="icon-sm" variant="ghost" onClick={() => setIndex(Math.min(current + 1, count - 1))} disabled={current === count - 1} aria-label="Next slide">
            <ChevronRight />
          </Button>
          <span className="w-12 text-center tabular">
            {current + 1} / {count}
          </span>
        </div>
        <label className="hidden items-center gap-1.5 md:flex">
          <input type="checkbox" checked={showRisk} onChange={(e) => setShowRisk(e.target.checked)} /> Risk slide
        </label>
        <Button size="sm" variant="ghost" onClick={fs.toggle} title="Full screen (F)">
          {fs.on ? <Minimize /> : <Maximize />} <span className="hidden sm:inline">{fs.on ? "Exit full screen" : "Full screen"}</span>
        </Button>
      </footer>
    </div>
  );
}
