"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock, TermInfo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { mult, pct, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Tier {
  hurdle: number | null;
  gp_share: number;
}
interface Config {
  lp_share: number;
  pref_rate: number;
  tiers: Tier[];
}
interface Side {
  contributed: number;
  distributed: number;
  profit: number;
  irr: number | null;
  multiple: number | null;
  promote?: number;
}
interface Result {
  scenario: { id: string; name: string };
  lp: Side;
  gp: Side & { promote: number };
  tiers: { name: string; gp_share: number; lp: number; gp: number }[];
  deal_irr: number | null;
}
interface Resp {
  config: Config;
  saved: boolean;
  result: Result;
}

// Inputs are edited as percent strings.
type Draft = { lp: string; pref: string; tiers: { hurdle: string; gp: string }[] };
const toDraft = (c: Config): Draft => ({
  lp: String(+(c.lp_share * 100).toFixed(2)),
  pref: String(+(c.pref_rate * 100).toFixed(2)),
  tiers: c.tiers.map((t) => ({ hurdle: t.hurdle === null ? "" : String(+(t.hurdle * 100).toFixed(2)), gp: String(+(t.gp_share * 100).toFixed(2)) })),
});
function fromDraft(d: Draft): { config: Config | null; error: string | null } {
  const n = (s: string) => (s.trim() === "" ? NaN : Number(s) / 100);
  const lp = n(d.lp);
  const pref = n(d.pref);
  if (!(lp > 0 && lp < 1)) return { config: null, error: "Investor (LP) share of equity must be between 0% and 100%." };
  if (!(pref >= 0 && pref <= 0.5)) return { config: null, error: "Preferred return must be between 0% and 50%." };
  let last = pref;
  const tiers: Tier[] = [];
  for (const [i, t] of d.tiers.entries()) {
    const gp = n(t.gp);
    if (!(gp >= 0 && gp < 1)) return { config: null, error: `Tier ${i + 2}: sponsor (GP) share must be at least 0% and below 100%.` };
    if (i === d.tiers.length - 1) {
      tiers.push({ hurdle: null, gp_share: gp });
    } else {
      const h = n(t.hurdle);
      if (!(h > last && h <= 1)) return { config: null, error: `Tier ${i + 2}: the hurdle must be above ${pct(last, 1)}.` };
      last = h;
      tiers.push({ hurdle: h, gp_share: gp });
    }
  }
  return { config: { lp_share: lp, pref_rate: pref, tiers }, error: null };
}

function PctInput({ id, value, onChange, disabled, placeholder }: { id: string; value: string; onChange: (v: string) => void; disabled?: boolean; placeholder?: string }) {
  return (
    <div className="flex items-center gap-1">
      <Input id={id} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} placeholder={placeholder} className="w-20 tabular" />
      <span className="text-sm text-muted-foreground">%</span>
    </div>
  );
}

/** LP/GP profit split for the deal: preferred return, promote tiers and the resulting returns. */
export function WaterfallCard({ propertyId, canEdit }: { propertyId: string; canEdit: boolean }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const saved = useQuery({ queryKey: [org, "waterfall", propertyId], queryFn: () => api<Resp>(`/api/properties/${propertyId}/waterfall`) });
  const [draft, setDraft] = useState<Draft | null>(null);
  const d = draft ?? (saved.data ? toDraft(saved.data.config) : null);
  const parsed = d ? fromDraft(d) : { config: null, error: null };
  const key = draft && parsed.config ? JSON.stringify(parsed.config) : null;
  const deferred = useDeferredValue(key);
  const preview = useQuery({
    queryKey: [org, "waterfall-preview", propertyId, deferred],
    queryFn: () => api<Resp>(`/api/properties/${propertyId}/waterfall/preview`, { body: JSON.parse(deferred!) }),
    enabled: !!deferred,
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: () => api<Resp>(`/api/properties/${propertyId}/waterfall`, { method: "PUT", body: parsed.config }),
    onSuccess: (r) => {
      qc.setQueryData([org, "waterfall", propertyId], r);
      setDraft(null);
      toast.success("Profit split saved");
    },
    onError: (e) => toast.error(e.message),
  });

  if (saved.isLoading) return <LoadingBlock rows={4} />;
  if (saved.error) return <ErrorBlock error={saved.error} />;
  if (!d || !saved.data) return null;
  const res = (draft ? preview.data?.result : saved.data.result) ?? saved.data.result;
  const set = (next: Partial<Draft>) => setDraft({ ...d, ...next });
  const setTier = (i: number, next: Partial<Draft["tiers"][number]>) => set({ tiers: d.tiers.map((t, j) => (j === i ? { ...t, ...next } : t)) });
  const gpPct = d.lp.trim() ? String(+(100 - Number(d.lp)).toFixed(2)) : "—";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          Profit split (waterfall)
          <TermInfo term="waterfall" label="Waterfall" />
        </CardTitle>
        <CardDescription>
          How this deal&apos;s cash to equity is shared between investors (LP) and the sponsor (GP), using the {res.scenario.name} cash flows. Cash is
          paid out tier by tier, top to bottom.
          {!saved.data.saved && " These are example terms; adjust and save them for this deal."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (parsed.config) save.mutate();
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="wf-lp">Investors (LP) put in</Label>
              <PctInput id="wf-lp" value={d.lp} onChange={(lp) => set({ lp })} disabled={!canEdit} />
              <p className="text-xs text-muted-foreground">Sponsor (GP) puts in {gpPct}%</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wf-pref" className="flex items-center gap-1">
                Preferred return <TermInfo term="preferred-return" label="Preferred return" />
              </Label>
              <PctInput id="wf-pref" value={d.pref} onChange={(pref) => set({ pref })} disabled={!canEdit} />
            </div>
          </div>
          <ol className="space-y-2 text-sm">
            <li className="rounded-md border bg-muted/40 px-3 py-2">
              <span className="font-medium">1.</span> Return of capital + {d.pref || "?"}% preferred return, split in proportion to the money each put in.
            </li>
            {d.tiers.map((t, i) => {
              const last = i === d.tiers.length - 1;
              return (
                <li key={i} className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2">
                  <span className="font-medium">{i + 2}.</span>
                  {last ? <span>Everything after that:</span> : <span>Until investors reach</span>}
                  {!last && <PctInput id={`wf-h-${i}`} value={t.hurdle} onChange={(hurdle) => setTier(i, { hurdle })} disabled={!canEdit} placeholder="12" />}
                  {!last && <span>IRR:</span>}
                  <span>sponsor gets</span>
                  <PctInput id={`wf-gp-${i}`} value={t.gp} onChange={(gp) => setTier(i, { gp })} disabled={!canEdit} />
                  {canEdit && d.tiers.length > 1 && (
                    <Button type="button" size="icon-sm" variant="ghost" className="ml-auto" aria-label={`Remove tier ${i + 2}`} onClick={() => set({ tiers: d.tiers.filter((_, j) => j !== i) })}>
                      <Trash2 />
                    </Button>
                  )}
                </li>
              );
            })}
          </ol>
          {parsed.error && (
            <p role="alert" className="text-sm text-destructive">
              {parsed.error}
            </p>
          )}
          {canEdit && (
            <div className="flex flex-wrap justify-between gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={d.tiers.length >= 5}
                onClick={() => {
                  const prev = d.tiers.slice(0, -1);
                  const lastHurdle = prev.length ? Number(prev[prev.length - 1].hurdle) || Number(d.pref) : Number(d.pref);
                  set({ tiers: [...prev, { hurdle: String(lastHurdle + 4), gp: d.tiers[d.tiers.length - 1].gp }, { hurdle: "", gp: String(Math.min(Number(d.tiers[d.tiers.length - 1].gp) + 10, 50)) }] });
                }}
              >
                <Plus /> Add a tier
              </Button>
              <div className="flex gap-2">
                {draft && (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
                    Discard
                  </Button>
                )}
                <Button type="submit" size="sm" disabled={!parsed.config || (!draft && saved.data.saved)} loading={save.isPending}>
                  Save split
                </Button>
              </div>
            </div>
          )}
        </form>

        <div className={cn("space-y-4", draft && preview.isFetching && "opacity-70 transition-opacity")}>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH />
                <TH className="text-right">Investors (LP)</TH>
                <TH className="text-right">Sponsor (GP)</TH>
              </TR>
            </THead>
            <TBody>
              <TR>
                <TD>Put in</TD>
                <TD className="text-right tabular">{usd(res.lp.contributed)}</TD>
                <TD className="text-right tabular">{usd(res.gp.contributed)}</TD>
              </TR>
              <TR>
                <TD>Get back</TD>
                <TD className="text-right tabular">{usd(res.lp.distributed)}</TD>
                <TD className="text-right tabular">{usd(res.gp.distributed)}</TD>
              </TR>
              <TR>
                <TD className="flex items-center gap-1">
                  IRR <TermInfo term="irr" label="IRR" />
                </TD>
                <TD className="text-right tabular font-medium">{pct(res.lp.irr, 1)}</TD>
                <TD className="text-right tabular font-medium">{pct(res.gp.irr, 1)}</TD>
              </TR>
              <TR>
                <TD>Equity multiple</TD>
                <TD className="text-right tabular">{mult(res.lp.multiple)}</TD>
                <TD className="text-right tabular">{mult(res.gp.multiple)}</TD>
              </TR>
            </TBody>
          </Table>
          <p className="text-sm">
            The whole deal returns <span className="font-medium tabular">{pct(res.deal_irr, 1)}</span> IRR. The sponsor&apos;s promote (cash above its
            share of the money put in) is <span className="font-medium tabular">{usd(res.gp.promote)}</span>.
          </p>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Tier</TH>
                <TH className="text-right">LP / GP</TH>
                <TH className="text-right">To LP</TH>
                <TH className="text-right">To GP</TH>
              </TR>
            </THead>
            <TBody>
              {res.tiers.map((t) => (
                <TR key={t.name} className={cn(t.lp + t.gp === 0 && "text-muted-foreground")}>
                  <TD>{t.name}</TD>
                  <TD className="text-right tabular">
                    {pct(1 - t.gp_share, 0)} / {pct(t.gp_share, 0)}
                  </TD>
                  <TD className="text-right tabular">{usd(t.lp)}</TD>
                  <TD className="text-right tabular">{usd(t.gp)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
