"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GitCompareArrows } from "lucide-react";
import { useState } from "react";

import { ErrorBlock, LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch } from "@/components/ui/overlays";
import { Badge, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dateTime, num, pct, usd } from "@/lib/format";
import type { DocumentRec } from "@/lib/types";
import { cn } from "@/lib/utils";

type Change = "changed" | "added" | "removed" | "same";

interface MixRow {
  name: string;
  units_before: number | null;
  units_after: number | null;
  rent_before: number | null;
  rent_after: number | null;
  status: "added" | "removed" | "changed" | "same";
}

interface Row {
  field_path: string;
  label: string;
  group: string;
  kind: string;
  before: unknown;
  after: unknown;
  change: Change;
  before_status: string | null;
  after_status: string | null;
  delta: number | null;
  delta_pct: number | null;
  unit_mix?: MixRow[];
}

interface Comparison {
  before: DocumentRec;
  after: DocumentRec;
  rows: Row[];
  counts: Record<Change, number>;
}

const CHANGE: Record<Change, { label: string; className: string }> = {
  changed: { label: "Changed", className: "border-warning/40 bg-warning/10 text-warning" },
  added: { label: "New", className: "border-success/40 bg-success/10 text-success" },
  removed: { label: "Missing", className: "border-destructive/40 bg-destructive/10 text-destructive" },
  same: { label: "Same", className: "text-muted-foreground" },
};

function fmt(kind: string, v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (kind === "unit_mix" && Array.isArray(v)) {
    const units = v.reduce((s: number, u: { units?: number }) => s + (u.units ?? 0), 0);
    return `${v.length} unit types · ${num(units)} units`;
  }
  if (typeof v !== "number") return String(v);
  if (kind === "currency") return usd(v);
  if (kind === "percent") return pct(v);
  if (kind === "years") return `${num(v, 1)} yrs`;
  return num(v, kind === "integer" ? 0 : 2);
}

function delta(r: Row): string | null {
  if (r.delta === null) return null;
  const sign = r.delta > 0 ? "+" : r.delta < 0 ? "−" : "";
  const abs = Math.abs(r.delta);
  const body = r.kind === "currency" ? usd(abs) : r.kind === "percent" ? `${num(abs * 100, 2)} pts` : num(abs, r.kind === "integer" ? 0 : 2);
  const rel = r.delta_pct !== null && r.kind !== "percent" ? ` (${sign}${pct(Math.abs(r.delta_pct), 1)})` : "";
  return `${sign}${body}${rel}`;
}

const reviewed = (s: string | null) => s === "accepted" || s === "edited";

/** Pick two versions of a deal document and see which extracted values changed between them. */
export function DocCompare({ docs }: { docs: DocumentRec[] }) {
  const ready = docs.filter((d) => d.status === "extracted");
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState<[string, string] | null>(null);
  const [showSame, setShowSame] = useState(false);
  const org = useOrgKey();

  // Default: the two newest documents of the same type, else the two newest overall.
  const defaults = (): [string, string] | null => {
    for (const d of ready) {
      const prev = ready.find((o) => o.id !== d.id && o.type === d.type);
      if (prev) return [prev.id, d.id];
    }
    return ready.length >= 2 ? [ready[1].id, ready[0].id] : null;
  };
  const [a, b] = pick ?? defaults() ?? ["", ""];
  const valid = a && b && a !== b;
  const q = useQuery({
    queryKey: [org, "doc-compare", a, b],
    queryFn: () => api<Comparison>(`/api/documents/${a}/compare?other=${b}`),
    enabled: open && !!valid,
  });

  if (ready.length < 2) return null;
  const rows = (q.data?.rows ?? []).filter((r) => showSame || r.change !== "same");
  const docLabel = (d: DocumentRec) => `${d.name} · ${dateTime(d.created_at)}`;

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <GitCompareArrows /> Compare versions
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Compare document versions"
          description="See what changed between two documents on this deal, such as last month's and this month's rent roll or T12. The older upload is shown as “before”. Reviewed values are used where you've accepted or edited them."
          className="max-w-4xl"
        >
          <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
            <div className="space-y-1.5">
              <Label htmlFor="cmp-a">Document</Label>
              <Select id="cmp-a" value={a} onChange={(e) => setPick([e.target.value, b])}>
                {ready.map((d) => (
                  <option key={d.id} value={d.id}>
                    {docLabel(d)}
                  </option>
                ))}
              </Select>
            </div>
            <ArrowRight className="mb-2.5 hidden size-4 text-muted-foreground sm:block" />
            <div className="space-y-1.5">
              <Label htmlFor="cmp-b">Compare with</Label>
              <Select id="cmp-b" value={b} onChange={(e) => setPick([a, e.target.value])}>
                {ready.map((d) => (
                  <option key={d.id} value={d.id}>
                    {docLabel(d)}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {!valid && <p className="mt-4 text-sm text-muted-foreground">Choose two different documents.</p>}
          {valid && q.isLoading && <LoadingBlock rows={4} />}
          {valid && q.error && <ErrorBlock error={q.error} />}
          {valid && q.data && (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">
                  {q.data.before.name} <ArrowRight className="inline size-3.5" /> {q.data.after.name}:
                </span>
                {(["changed", "added", "removed", "same"] as Change[]).map((k) => (
                  <Badge key={k} variant="outline" className={CHANGE[k].className}>
                    {q.data.counts[k]} {CHANGE[k].label.toLowerCase()}
                  </Badge>
                ))}
                <span className="ml-auto flex items-center gap-2">
                  <Switch id="cmp-same" checked={showSame} onCheckedChange={setShowSame} />
                  <Label htmlFor="cmp-same" className="text-xs">
                    Show unchanged
                  </Label>
                </span>
              </div>
              {rows.length === 0 ? (
                <p className="rounded-md border p-4 text-center text-sm text-muted-foreground">
                  {q.data.rows.length ? "No differences: every value matches." : "Neither document has extracted values to compare."}
                </p>
              ) : (
                <div className="max-h-[55vh] overflow-auto rounded-md border">
                  <Table>
                    <THead>
                      <TR className="hover:bg-transparent">
                        <TH>Value</TH>
                        <TH className="text-right">Before</TH>
                        <TH className="text-right">After</TH>
                        <TH className="text-right">Change</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {rows.map((r) => (
                        <TR key={r.field_path} className={cn(r.change === "same" && "text-muted-foreground")}>
                          <TD>
                            <div className="font-medium">{r.label}</div>
                            <div className="text-xs text-muted-foreground">{r.group}</div>
                            {r.unit_mix && (
                              <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
                                {r.unit_mix
                                  .filter((u) => u.status !== "same")
                                  .map((u) => (
                                    <li key={u.name}>
                                      {u.name}: {u.status === "added" ? "new" : u.status === "removed" ? "no longer listed" : ""}
                                      {u.status === "changed" &&
                                        `${num(u.units_before)} → ${num(u.units_after)} units, ${usd(u.rent_before)} → ${usd(u.rent_after)}/mo`}
                                    </li>
                                  ))}
                              </ul>
                            )}
                          </TD>
                          <TD className="text-right tabular">
                            {fmt(r.kind, r.before)}
                            {r.before_status && !reviewed(r.before_status) && <div className="text-[11px] text-muted-foreground">unreviewed</div>}
                          </TD>
                          <TD className="text-right tabular">
                            {fmt(r.kind, r.after)}
                            {r.after_status && !reviewed(r.after_status) && <div className="text-[11px] text-muted-foreground">unreviewed</div>}
                          </TD>
                          <TD className="text-right">
                            <Badge variant="outline" className={CHANGE[r.change].className}>
                              {CHANGE[r.change].label}
                            </Badge>
                            {delta(r) && <div className="mt-1 text-xs tabular">{delta(r)}</div>}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
