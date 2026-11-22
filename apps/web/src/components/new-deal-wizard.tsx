"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { TermInfo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Input, Label } from "@/components/ui/primitives";
import { useOrgKey, usePropertyTypes } from "@/hooks/queries";
import { api } from "@/lib/api";
import { pct, usdShort } from "@/lib/format";
import type { Property, PropertyTypeDef } from "@/lib/types";
import { cn } from "@/lib/utils";

/** One-line descriptions shown on the property-type cards. Unknown types fall back to their label. */
const TYPE_HINTS: Record<string, string> = {
  multifamily: "Apartments, priced and underwritten per unit.",
  industrial: "Warehouses and logistics, usually net-leased per SF.",
  office: "Office buildings; higher vacancy and leasing costs.",
  retail: "Shopping centers and storefronts, often net-leased.",
  mixed_use: "Several uses in one property, e.g. retail below apartments.",
  hospitality: "Hotels; income changes nightly, so expenses are high.",
  self_storage: "Storage units rented month to month.",
  student_housing: "Beds near a campus, leased by the academic year.",
  qsr: "Quick-service restaurants (e.g. Taco Bell), usually one tenant on a net lease.",
  land: "Land held for development or ground lease.",
};

const STEPS = ["Property", "Price & size", "Starter assumptions", "Review"] as const;

type Form = {
  name: string;
  property_type: string;
  address: string;
  city: string;
  state: string;
  purchase_price: string;
  hold_period_years: string;
  units: string;
  rentable_sf: string;
  noi_year1: string;
  vacancy_rate: string;
  rent_growth: string;
  exit_cap_rate: string;
};

const num = (s: string) => Number(s.replace(/[$,%\s]/g, ""));
const filled = (s: string) => s.trim() !== "" && Number.isFinite(num(s));
const pctText = (v: unknown) => (typeof v === "number" ? String(Math.round(v * 10000) / 100) : "");

function templateValues(meta: PropertyTypeDef | undefined) {
  const d = meta?.defaults ?? {};
  return { vacancy_rate: pctText(d.vacancy_rate), rent_growth: pctText(d.rent_growth), exit_cap_rate: pctText(d.exit_cap_rate) };
}

/** Guided four-step New Deal flow with property-type starter assumptions. */
export function NewDealWizard({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const org = useOrgKey();
  const types = usePropertyTypes();
  const [step, setStep] = useState(0);
  const [f, setF] = useState<Form>({
    name: "",
    property_type: "multifamily",
    address: "",
    city: "",
    state: "",
    purchase_price: "",
    hold_period_years: "10",
    units: "",
    rentable_sf: "",
    noi_year1: "",
    vacancy_rate: "",
    rent_growth: "",
    exit_cap_rate: "",
  });
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  const meta = types.data?.find((t) => t.key === f.property_type);
  const template = templateValues(meta);
  const usesUnits = meta?.revenue_mode === "unit_mix";
  // Empty starter fields mean "use the template value".
  const effective = {
    vacancy_rate: f.vacancy_rate || template.vacancy_rate,
    rent_growth: f.rent_growth || template.rent_growth,
    exit_cap_rate: f.exit_cap_rate || template.exit_cap_rate,
  };
  const changedFromTemplate = (k: keyof typeof effective) => f[k] !== "" && num(f[k]) !== num(template[k]);

  const chooseType = (key: string) => setF({ ...f, property_type: key, vacancy_rate: "", rent_growth: "", exit_cap_rate: "" });

  const reset = () => {
    setStep(0);
    setF((prev) => ({ ...prev, name: "", address: "", city: "", state: "", purchase_price: "", units: "", rentable_sf: "", noi_year1: "", vacancy_rate: "", rent_growth: "", exit_cap_rate: "" }));
  };
  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) reset();
  };

  const create = useMutation({
    mutationFn: () => {
      const starter: Record<string, number> = {};
      if (filled(f.noi_year1)) starter.noi_year1 = num(f.noi_year1);
      (["vacancy_rate", "rent_growth", "exit_cap_rate"] as const).forEach((k) => {
        if (changedFromTemplate(k)) starter[k] = num(f[k]) / 100;
      });
      return api<Property>("/api/properties", {
        body: {
          name: f.name.trim(),
          property_type: f.property_type,
          address: f.address || null,
          city: f.city || null,
          state: f.state || null,
          purchase_price: num(f.purchase_price),
          hold_period_years: Number(f.hold_period_years),
          units: usesUnits && f.units ? num(f.units) : null,
          rentable_sf: !usesUnits && f.rentable_sf ? num(f.rentable_sf) : null,
          ...(Object.keys(starter).length ? { starter } : {}),
        },
      });
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success("Deal created. Upload the OM, T12 or rent roll to replace starter values with verified data.");
      close(false);
      router.push(`/deals/${p.id}/documents`);
    },
    onError: (e) => toast.error(e.message),
  });

  const sizeValue = usesUnits ? f.units : f.rentable_sf;
  const priceOk = filled(f.purchase_price) && num(f.purchase_price) > 0;
  const holdOk = Number(f.hold_period_years) >= 1 && Number(f.hold_period_years) <= 30;
  const pctOk = (["vacancy_rate", "rent_growth", "exit_cap_rate"] as const).every((k) => filled(f[k]));
  const canNext = [f.name.trim() !== "", priceOk && holdOk && (f.noi_year1 === "" || filled(f.noi_year1)), pctOk, true][step];

  const provided = [
    { label: "Location", ok: Boolean(f.city || f.state || f.address) },
    { label: usesUnits ? "Number of units" : "Rentable SF", ok: filled(sizeValue) },
    { label: "Year-1 NOI", ok: filled(f.noi_year1) },
    { label: "Your own assumptions", ok: (["vacancy_rate", "rent_growth", "exit_cap_rate"] as const).some(changedFromTemplate) },
  ];
  const providedCount = provided.filter((p) => p.ok).length;
  const impliedCap = filled(f.noi_year1) && priceOk ? num(f.noi_year1) / num(f.purchase_price) : null;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent title="New deal" description="Four short steps. Everything can be changed later." className="max-w-2xl">
        <ol className="flex gap-1" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s} className="flex-1">
              <div className={cn("h-1 rounded-full", i <= step ? "bg-accent" : "bg-muted")} />
              <div className={cn("mt-1 text-[11px]", i === step ? "font-medium text-foreground" : "text-muted-foreground")} aria-current={i === step ? "step" : undefined}>
                {i + 1}. {s}
              </div>
            </li>
          ))}
        </ol>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!canNext) return;
            if (step === 1) {
              // Pre-fill the starter fields with the template so they can be edited normally.
              setF({
                ...f,
                vacancy_rate: f.vacancy_rate || template.vacancy_rate,
                rent_growth: f.rent_growth || template.rent_growth,
                exit_cap_rate: f.exit_cap_rate || template.exit_cap_rate,
              });
            }
            if (step < STEPS.length - 1) setStep(step + 1);
            else create.mutate();
          }}
          className="space-y-4"
        >
          {step === 0 && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="nd-name">Deal name</Label>
                <Input id="nd-name" required autoFocus value={f.name} onChange={set("name")} placeholder="e.g. Parkside Apartments" />
              </div>
              <fieldset className="space-y-1.5">
                <legend className="mb-1.5 text-sm font-medium">Property type</legend>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup">
                  {(types.data ?? []).map((t) => (
                    <button
                      key={t.key}
                      type="button"
                      role="radio"
                      aria-checked={f.property_type === t.key}
                      onClick={() => chooseType(t.key)}
                      className={cn(
                        "rounded-md border p-2.5 text-left text-sm transition-colors hover:bg-muted/60",
                        f.property_type === t.key && "border-accent bg-accent/5 ring-1 ring-accent",
                      )}
                    >
                      <div className="font-medium">{t.label}</div>
                      <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{TYPE_HINTS[t.key] ?? t.label}</div>
                    </button>
                  ))}
                </div>
              </fieldset>
              <div className="grid grid-cols-6 gap-3">
                <div className="col-span-6 space-y-1.5">
                  <Label htmlFor="nd-address">Address (optional)</Label>
                  <Input id="nd-address" value={f.address} onChange={set("address")} />
                </div>
                <div className="col-span-4 space-y-1.5">
                  <Label htmlFor="nd-city">City</Label>
                  <Input id="nd-city" value={f.city} onChange={set("city")} />
                </div>
                <div className="col-span-2 space-y-1.5">
                  <Label htmlFor="nd-state">State</Label>
                  <Input id="nd-state" value={f.state} onChange={set("state")} maxLength={2} placeholder="TX" />
                </div>
              </div>
            </>
          )}

          {step === 1 && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="nd-price">Purchase / asking price ($)</Label>
                <Input id="nd-price" required autoFocus inputMode="numeric" value={f.purchase_price} onChange={set("purchase_price")} placeholder="25,000,000" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nd-size">{usesUnits ? "Number of units" : "Rentable SF"}</Label>
                <Input id="nd-size" inputMode="numeric" value={sizeValue} onChange={set(usesUnits ? "units" : "rentable_sf")} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nd-hold">Hold period (years)</Label>
                <Input id="nd-hold" type="number" min={1} max={30} value={f.hold_period_years} onChange={set("hold_period_years")} />
                <p className="text-[11px] text-muted-foreground">How long you plan to own it before selling.</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nd-noi" className="flex items-center gap-1">
                  Year-1 NOI ($, optional) <TermInfo term="noi" />
                </Label>
                <Input id="nd-noi" inputMode="numeric" value={f.noi_year1} onChange={set("noi_year1")} placeholder="From the OM or T12" />
                <p className="text-[11px] text-muted-foreground">
                  {impliedCap !== null
                    ? `That is a ${pct(impliedCap)} going-in cap rate on this price.`
                    : "Leave blank to start from an estimate based on the price."}
                </p>
              </div>
            </div>
          )}

          {step === 2 && (
            <>
              <p className="rounded-md border bg-muted/40 p-3 text-sm">
                These are <span className="font-medium">starter assumptions for {meta?.label ?? "this property type"}</span>, not market data. Change any
                you have better information for; the rest can be replaced later with verified document data.
              </p>
              <div className="grid grid-cols-3 gap-3">
                {(
                  [
                    ["vacancy_rate", "Vacancy", "vacancy", "Share of rent lost to empty units."],
                    ["rent_growth", "Rent growth / yr", "gpr", "How fast rents rise each year."],
                    ["exit_cap_rate", "Exit cap rate", "exit-cap", "Sets the sale price at the end."],
                  ] as const
                ).map(([k, label, term, help]) => (
                  <div key={k} className="space-y-1.5">
                    <Label htmlFor={`nd-${k}`} className="flex items-center gap-1">
                      {label} <TermInfo term={term} />
                    </Label>
                    <div className="relative">
                      <Input id={`nd-${k}`} inputMode="decimal" required value={f[k]} onChange={set(k)} className="pr-7" />
                      <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {help} {changedFromTemplate(k) ? `Template: ${template[k]}%.` : "Template value."}
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-md border p-3 text-sm">
                <dt className="text-muted-foreground">Deal</dt>
                <dd className="font-medium">{f.name}</dd>
                <dt className="text-muted-foreground">Type</dt>
                <dd>{meta?.label}</dd>
                <dt className="text-muted-foreground">Location</dt>
                <dd>{[f.address, f.city, f.state].filter(Boolean).join(", ") || "—"}</dd>
                <dt className="text-muted-foreground">Price</dt>
                <dd>{usdShort(num(f.purchase_price))}</dd>
                <dt className="text-muted-foreground">{usesUnits ? "Units" : "Rentable SF"}</dt>
                <dd>{filled(sizeValue) ? num(sizeValue).toLocaleString() : "Template default"}</dd>
                <dt className="text-muted-foreground">Hold</dt>
                <dd>{f.hold_period_years} years</dd>
                <dt className="text-muted-foreground">Year-1 NOI</dt>
                <dd>{filled(f.noi_year1) ? usdShort(num(f.noi_year1)) : "Estimated from price"}</dd>
                <dt className="text-muted-foreground">Vacancy · growth · exit cap</dt>
                <dd>
                  {effective.vacancy_rate}% · {effective.rent_growth}% · {effective.exit_cap_rate}%
                </dd>
              </dl>
              <div className="rounded-md border p-3">
                <div className="text-sm font-medium">
                  Inputs you provided: {providedCount} of {provided.length}
                </div>
                <ul className="mt-1.5 grid grid-cols-2 gap-1 text-xs">
                  {provided.map((p) => (
                    <li key={p.label} className={cn("flex items-center gap-1.5", p.ok ? "text-foreground" : "text-muted-foreground")}>
                      {p.ok ? <Check className="size-3.5 text-success" /> : <span className="inline-block size-3.5 text-center">–</span>}
                      {p.label}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">
                  Everything else starts from the {meta?.label ?? ""} template. Next you&apos;ll land on Documents: uploading the OM, T12 or rent roll is the
                  fastest way to replace starter values with verified ones.
                </p>
              </div>
            </div>
          )}

          <div className="flex justify-between gap-2 pt-1">
            <Button type="button" variant="outline" onClick={() => (step === 0 ? close(false) : setStep(step - 1))}>
              {step === 0 ? (
                "Cancel"
              ) : (
                <>
                  <ArrowLeft /> Back
                </>
              )}
            </Button>
            <Button type="submit" disabled={!canNext} loading={create.isPending}>
              {step < STEPS.length - 1 ? (
                <>
                  Next <ArrowRight />
                </>
              ) : (
                "Create deal"
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
