"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookmarkPlus, History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Badge, Input, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dateTime, mult, pct, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

type Fmt = "usd" | "pct" | "x";
interface Version {
  id: string;
  calculated_at: string;
  by: string | null;
  label: string | null;
  engine_version: string;
  is_current: boolean;
  metrics: Record<string, number | null>;
}
interface Versions {
  metrics: { key: string; label: string; fmt: Fmt }[];
  versions: Version[];
}
interface Compare {
  before: { id: string; label: string | null; calculated_at: string };
  after: { id: string; label: string | null; calculated_at: string };
  assumption_changes: { path: string; before: unknown; after: unknown }[];
  metrics: { key: string; label: string; fmt: Fmt; before: number | null; after: number | null; delta: number | null }[];
}

const fmt = (f: Fmt, v: number | null | undefined) => (f === "usd" ? usd(v) : f === "pct" ? pct(v, 2) : mult(v));
const show = (path: string, v: unknown) => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (/(rate|growth|pct|ltv|vacancy|loss|share)/.test(path) && Math.abs(v) < 1) return pct(v, 2);
    return Math.abs(v) >= 1000 ? usd(v) : String(v);
  }
  if (Array.isArray(v)) return `${v.length} items`;
  return String(v);
};
const nice = (path: string) => path.replace(/_/g, " ").replace(/\./g, " › ");

/** Saved versions of a scenario: name the current state, compare any two, restore an earlier one. */
export function VersionHistory({ scenarioId, scenarioName, canEdit, dirty }: { scenarioId: string; scenarioName: string; canEdit: boolean; dirty: boolean }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [namedOnly, setNamedOnly] = useState(false);
  const list = useQuery({
    queryKey: [org, "versions", scenarioId, namedOnly],
    queryFn: () => api<Versions>(`/api/scenarios/${scenarioId}/versions${namedOnly ? "?labelled_only=true" : ""}`),
    enabled: open,
  });
  const cmp = useQuery({
    queryKey: [org, "versions-compare", scenarioId, ...picked],
    queryFn: () => api<Compare>(`/api/scenarios/${scenarioId}/versions/compare?a=${picked[0]}&b=${picked[1]}`),
    enabled: open && picked.length === 2,
  });
  const save = useMutation({
    mutationFn: () => api(`/api/scenarios/${scenarioId}/versions/save`, { body: { label: label.trim() } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "versions", scenarioId] });
      toast.success(`Saved version “${label.trim()}”`);
      setLabel("");
    },
    onError: (e) => toast.error(e.message),
  });
  const restore = useMutation({
    mutationFn: (v: Version) => api(`/api/scenarios/${scenarioId}/versions/${v.id}/restore`, { method: "POST" }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: [org] });
      setPicked([]);
      toast.success(`Restored ${v.label ? `“${v.label}”` : "that version"}. Recalculated; the previous state is still in history.`);
    },
    onError: (e) => toast.error(e.message),
  });
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p.slice(-1), id]));

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <History /> History
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title={`Version history · ${scenarioName}`}
          description="Every calculation is saved permanently with its inputs and results. Name important versions, tick two to compare, or restore an earlier one (restoring adds a new version; nothing is deleted)."
          className="max-w-4xl"
        >
          {canEdit && (
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (label.trim()) save.mutate();
              }}
            >
              <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} placeholder="Name the current version, e.g. Sent to lender" className="max-w-sm" aria-label="Version name" />
              <Button type="submit" size="sm" disabled={!label.trim() || dirty} loading={save.isPending}>
                <BookmarkPlus /> Save version
              </Button>
              {dirty && <span className="text-xs text-warning">Save your changes first.</span>}
            </form>
          )}
          <label className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={namedOnly} onChange={(e) => setNamedOnly(e.target.checked)} /> Named versions only
          </label>
          {list.isLoading && <LoadingBlock rows={4} />}
          {list.error && <ErrorBlock error={list.error} />}
          {list.data && (
            <div className="max-h-[38vh] overflow-auto rounded-md border">
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH className="w-8" />
                    <TH>Version</TH>
                    <TH className="text-right">Lev. IRR</TH>
                    <TH className="text-right">Multiple</TH>
                    <TH className="text-right">NOI (Y1)</TH>
                    <TH className="text-right">DSCR</TH>
                    {canEdit && <TH />}
                  </TR>
                </THead>
                <TBody>
                  {list.data.versions.map((v) => (
                    <TR key={v.id} className={cn(picked.includes(v.id) && "bg-accent/10")}>
                      <TD>
                        <input type="checkbox" checked={picked.includes(v.id)} onChange={() => toggle(v.id)} aria-label={`Compare ${v.label ?? dateTime(v.calculated_at)}`} />
                      </TD>
                      <TD>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-medium">{v.label ?? dateTime(v.calculated_at)}</span>
                          {v.is_current && <Badge variant="success">Current</Badge>}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {v.label ? `${dateTime(v.calculated_at)} · ` : ""}
                          {v.by ?? "System"}
                        </div>
                      </TD>
                      <TD className="text-right tabular">{pct(v.metrics.irr_levered, 1)}</TD>
                      <TD className="text-right tabular">{mult(v.metrics.equity_multiple_levered)}</TD>
                      <TD className="text-right tabular">{usd(v.metrics.noi_year1)}</TD>
                      <TD className="text-right tabular">{mult(v.metrics.dscr_year1)}</TD>
                      {canEdit && (
                        <TD className="text-right">
                          {!v.is_current && (
                            <Button size="sm" variant="ghost" disabled={dirty} loading={restore.isPending && restore.variables?.id === v.id} onClick={() => confirm(`Restore ${v.label ? `“${v.label}”` : "this version"}? Its assumptions replace the current ones and the scenario recalculates.`) && restore.mutate(v)}>
                              <RotateCcw /> Restore
                            </Button>
                          )}
                        </TD>
                      )}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
          {picked.length < 2 && <p className="text-xs text-muted-foreground">Tick two versions to compare them.</p>}
          {picked.length === 2 && cmp.data && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                  {cmp.data.before.label ?? dateTime(cmp.data.before.calculated_at)} <ArrowRight className="size-3.5" /> {cmp.data.after.label ?? dateTime(cmp.data.after.calculated_at)}
                </div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Assumptions changed</div>
                {cmp.data.assumption_changes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Same assumptions.</p>
                ) : (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {cmp.data.assumption_changes.map((c) => (
                      <li key={c.path} className="flex justify-between gap-3 border-b py-1 last:border-0">
                        <span className="capitalize text-muted-foreground">{nice(c.path)}</span>
                        <span className="tabular">
                          {show(c.path, c.before)} → <span className="font-medium">{show(c.path, c.after)}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="mb-1 mt-6 text-xs font-semibold uppercase tracking-wide text-muted-foreground md:mt-7">Results</div>
                <ul className="space-y-1 text-sm">
                  {cmp.data.metrics.map((m) => (
                    <li key={m.key} className="flex justify-between gap-3 border-b py-1 last:border-0">
                      <span className="text-muted-foreground">{m.label}</span>
                      <span className="tabular">
                        {fmt(m.fmt, m.before)} → <span className="font-medium">{fmt(m.fmt, m.after)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
