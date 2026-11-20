"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Legend, SERIES } from "@/components/charts";
import { LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { pct, stripDemo, usdShort } from "@/lib/format";
import type { Financing } from "@/lib/types";

interface StackRow {
  name: string;
  loan_amount: number;
  mezzanine: number;
  preferred_equity: number;
  equity_invested: number;
  is_active: boolean;
  financing_id: string | null;
}

// Fixed order = seniority, and each layer keeps its color whatever the structure.
const LAYERS: { key: keyof StackRow; label: string; color: string }[] = [
  { key: "loan_amount", label: "Senior loan", color: SERIES[0] },
  { key: "mezzanine", label: "Mezzanine", color: SERIES[1] },
  { key: "preferred_equity", label: "Preferred equity", color: SERIES[2] },
  { key: "equity_invested", label: "Common equity", color: SERIES[3] },
];

/** How each structure funds the deal: one bar per structure, senior debt first. */
export function CapitalStack({ rows }: { rows: StackRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Capital stack</CardTitle>
        <CardDescription>How each structure pays for the deal, from the first money repaid (senior loan) to the last (your common equity).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Legend items={LAYERS.map((l) => ({ label: l.label, color: l.color }))} />
        <ul className="space-y-4">
          {rows.map((r) => {
            const parts = LAYERS.map((l) => ({ ...l, value: Number(r[l.key]) || 0 })).filter((p) => p.value > 0);
            const total = parts.reduce((s, p) => s + p.value, 0) || 1;
            return (
              <li key={r.financing_id ?? "cash"}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium">
                    {r.name}
                    {r.is_active && <span className="ml-2 text-xs text-muted-foreground">(active)</span>}
                  </span>
                  <span className="tabular text-xs text-muted-foreground">{usdShort(total)} total</span>
                </div>
                <div className="flex h-6 gap-[2px] overflow-hidden rounded-[4px]" role="img" aria-label={`${r.name}: ${parts.map((p) => `${p.label} ${pct(p.value / total, 0)}`).join(", ")}`}>
                  {parts.map((p) => (
                    <div key={p.label} title={`${p.label}: ${usdShort(p.value)} (${pct(p.value / total, 1)})`} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />
                  ))}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {parts.map((p, i) => (
                    <span key={p.label}>
                      {i > 0 && " · "}
                      {p.label} <span className="tabular text-foreground">{pct(p.value / total, 0)}</span> ({usdShort(p.value)})
                    </span>
                  ))}
                </p>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

type LibraryItem = Financing & { property_name: string };

/** Copy a structure from another deal in the workspace as a starting point. */
export function CopyStructure({ propertyId }: { propertyId: string }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const lib = useQuery({
    queryKey: [org, "financing-library", propertyId],
    queryFn: () => api<LibraryItem[]>(`/api/financing?exclude_property=${propertyId}`),
    enabled: open,
  });
  const copy = useMutation({
    mutationFn: (f: LibraryItem) => api<Financing>(`/api/properties/${propertyId}/financing/clone`, { body: { financing_id: f.id } }),
    onSuccess: (f) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success(`Added “${f.name}”. Edit it or make it active.`);
      setOpen(false);
    },
    onError: (e) => toast.error(e.message),
  });
  const groups = new Map<string, LibraryItem[]>();
  for (const f of lib.data ?? []) groups.set(f.property_name, [...(groups.get(f.property_name) ?? []), f]);

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Copy /> Copy from another deal
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Copy a financing structure" description="Start from terms you've already set up on another deal. The copy is added here as an inactive structure you can edit." className="max-w-xl">
          {lib.isLoading && <LoadingBlock rows={3} />}
          {lib.data?.length === 0 && <p className="text-sm text-muted-foreground">No other deal in this workspace has a financing structure yet.</p>}
          <div className="max-h-[60vh] space-y-4 overflow-y-auto">
            {[...groups.entries()].map(([deal, items]) => (
              <div key={deal}>
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{stripDemo(deal)}</div>
                <ul className="space-y-1.5">
                  {items.map((f) => (
                    <li key={f.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                      <div className="min-w-0">
                        <div className="truncate font-medium">{f.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {f.loan_amount !== null ? usdShort(f.loan_amount) : `${pct(f.ltv, 0)} LTV`} at{" "}
                          {f.rate_type === "floating" ? `${pct(f.index_rate + f.spread, 2)} floating` : pct(f.interest_rate, 2)} · {f.term_years} yr
                          {f.mezzanine?.amount ? ` · + ${usdShort(f.mezzanine.amount)} mezz` : ""}
                          {f.preferred_equity?.amount ? ` · + ${usdShort(f.preferred_equity.amount)} pref` : ""}
                        </div>
                      </div>
                      <Button size="sm" loading={copy.isPending && copy.variables?.id === f.id} onClick={() => copy.mutate(f)}>
                        Copy
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
