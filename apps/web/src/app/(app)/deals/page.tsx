"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Columns3, FileDown, FileStack, GitCompareArrows, Plus, Rows3, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { DemoBadge, EmptyState, ErrorBlock, LoadingBlock, PageHeader, RiskBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { NewDealWizard } from "@/components/new-deal-wizard";
import { Card, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey, useProperties, usePropertyTypes } from "@/hooks/queries";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { mult, pct, STATUS_LABELS, STATUSES, stripDemo, TYPE_LABELS, usd, usdShort } from "@/lib/format";
import type { Property } from "@/lib/types";
import { cn } from "@/lib/utils";
import { gateError } from "@/lib/workflow";

function DealsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { hasRole } = useAuth();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [view, setView] = useState<"table" | "kanban">(() => {
    try {
      return window.localStorage.getItem("axiom.deals.view") === "kanban" ? "kanban" : "table";
    } catch {
      return "table";
    }
  });
  const [open, setOpen] = useState(params.get("new") === "1");
  const [selected, setSelected] = useState<string[]>([]);
  const { data, isLoading, error } = useProperties({ q: q || undefined, property_type: type || undefined, status: status || undefined });

  const changeView = (v: "table" | "kanban") => {
    setView(v);
    try {
      window.localStorage.setItem("axiom.deals.view", v);
    } catch {
      /* ignore */
    }
  };

  return (
    <>
      <PageHeader
        title="Deals"
        description="Every opportunity in your pipeline, with base-case returns from the latest calculation."
        actions={
          <>
            <Button variant="outline" asChild>
              <Link href="/documents">
                <FileStack /> Document queue
              </Link>
            </Button>
            {hasRole("analyst") && (
              <Button onClick={() => setOpen(true)}>
                <Plus /> New deal
              </Button>
            )}
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-64">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input placeholder="Search name or market…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" aria-label="Search deals" />
        </div>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-44" aria-label="Property type">
          <option value="">All property types</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44" aria-label="Status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
        <div className="ml-auto inline-flex rounded-md border p-0.5" role="group" aria-label="View">
          <Button variant={view === "table" ? "secondary" : "ghost"} size="sm" onClick={() => changeView("table")} aria-pressed={view === "table"}>
            <Rows3 /> Table
          </Button>
          <Button variant={view === "kanban" ? "secondary" : "ghost"} size="sm" onClick={() => changeView("kanban")} aria-pressed={view === "kanban"}>
            <Columns3 /> Pipeline
          </Button>
        </div>
      </div>
      {isLoading && <LoadingBlock rows={6} />}
      {error && <ErrorBlock error={error} />}
      {data && data.length === 0 && (
        <EmptyState icon={Building2} title="No deals match" description="Adjust filters or create a new deal." />
      )}
      {data && data.length > 0 && view === "table" && (
        <>
          <BulkBar deals={data} selected={selected} onClear={() => setSelected([])} />
          <DealTable deals={data} onOpen={(id) => router.push(`/deals/${id}`)} selected={selected} onSelect={setSelected} />
        </>
      )}
      {data && data.length > 0 && view === "kanban" && <Kanban deals={data} />}
      <NewDealWizard open={open} onOpenChange={setOpen} />
    </>
  );
}

const MAX_COMPARE = 8;
const MAX_PACK = 25;

function BulkBar({ deals, selected, onClear }: { deals: Property[]; selected: string[]; onClear: () => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const org = useOrgKey();
  const { hasRole } = useAuth();
  const [exporting, setExporting] = useState(false);
  // Only act on deals still visible under the current filters.
  const ids = selected.filter((id) => deals.some((d) => d.id === id));
  const stage = useMutation({
    mutationFn: ({ status, override = false }: { status: string; override?: boolean }) =>
      api<{ updated: string[] }>("/api/properties/bulk-status", { body: { ids, status, override_requirements: override } }),
    onSuccess: (r, v) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success(`${r.updated.length} deal${r.updated.length === 1 ? "" : "s"} moved to ${STATUS_LABELS[v.status]}`);
    },
    onError: (e, v) => {
      const g = gateError(e);
      if (!g) return toast.error(e.message);
      const list = Object.entries(g.blocked)
        .map(([name, missing]) => `• ${name}: ${missing.join("; ")}`)
        .join("\n");
      if (g.canOverride && confirm(`${g.message}:\n\n${list}\n\nMove all selected deals anyway? This is logged.`)) stage.mutate({ status: v.status, override: true });
      else if (!g.canOverride) toast.error(`${g.message}. ${Object.keys(g.blocked).join(", ")}`);
    },
  });
  if (!ids.length) return null;
  const exportPack = async () => {
    setExporting(true);
    try {
      await download(`/api/reports/summary-pack?ids=${ids.join(",")}`, "deal-summary-pack.pdf");
      toast.success("Summary pack downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not export the summary pack");
    } finally {
      setExporting(false);
    }
  };
  return (
    <div className="sticky top-16 z-20 mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-2 shadow-sm" role="region" aria-label="Bulk actions">
      <span className="text-sm font-medium">{ids.length} selected</span>
      {hasRole("analyst") && (
        <Select
          value=""
          onChange={(e) => e.target.value && stage.mutate({ status: e.target.value })}
          className="h-8 w-44"
          aria-label="Move selected deals to stage"
          disabled={stage.isPending}
        >
          <option value="">Move to stage…</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={ids.length < 2 || ids.length > MAX_COMPARE}
        title={ids.length > MAX_COMPARE ? `Compare up to ${MAX_COMPARE} deals` : undefined}
        onClick={() => router.push(`/compare?ids=${ids.join(",")}`)}
      >
        <GitCompareArrows /> Compare
      </Button>
      <Button size="sm" variant="outline" loading={exporting} disabled={ids.length > MAX_PACK} onClick={exportPack}>
        <FileDown /> Export summary pack
      </Button>
      <Button size="sm" variant="ghost" className="ml-auto" onClick={onClear}>
        Clear selection
      </Button>
    </div>
  );
}

function DealTable({
  deals,
  onOpen,
  selected,
  onSelect,
}: {
  deals: Property[];
  onOpen: (id: string) => void;
  selected: string[];
  onSelect: (ids: string[]) => void;
}) {
  const visible = deals.map((d) => d.id);
  const allOn = visible.every((id) => selected.includes(id));
  const toggle = (id: string) => onSelect(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <Card>
      <Table>
        <THead>
          <TR className="hover:bg-transparent">
            <TH className="w-8">
              <input
                type="checkbox"
                aria-label="Select all deals"
                checked={allOn}
                onChange={() => onSelect(allOn ? selected.filter((id) => !visible.includes(id)) : [...new Set([...selected, ...visible])])}
              />
            </TH>
            <TH>Deal</TH>
            <TH>Type</TH>
            <TH>Status</TH>
            <TH className="text-right">Price</TH>
            <TH className="text-right">$/unit · $/SF</TH>
            <TH className="text-right">Cap rate</TH>
            <TH className="text-right">Lev. IRR</TH>
            <TH className="text-right">Eq. multiple</TH>
            <TH className="text-right">DSCR</TH>
            <TH>Risk</TH>
            <TH>Owner</TH>
          </TR>
        </THead>
        <TBody>
          {deals.map((p) => (
            <TR key={p.id} className={cn("cursor-pointer", selected.includes(p.id) && "bg-accent/5")} onClick={() => onOpen(p.id)}>
              <TD onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" aria-label={`Select ${stripDemo(p.name)}`} checked={selected.includes(p.id)} onChange={() => toggle(p.id)} />
              </TD>
              <TD>
                <Link href={`/deals/${p.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                  {stripDemo(p.name)}
                </Link>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {[p.city, p.state].filter(Boolean).join(", ") || "—"}
                  {p.is_demo && <DemoBadge />}
                </div>
              </TD>
              <TD className="text-muted-foreground">{TYPE_LABELS[p.property_type]}</TD>
              <TD>
                <StatusBadge status={p.status} />
              </TD>
              <TD className="text-right">{usdShort(p.purchase_price)}</TD>
              <TD className="text-right text-muted-foreground">
                {p.latest?.price_per_unit ? usd(p.latest.price_per_unit) : p.latest?.price_per_sf ? `${usd(p.latest.price_per_sf, 2)}/SF` : "—"}
              </TD>
              <TD className="text-right">{pct(p.latest?.cap_rate)}</TD>
              <TD className="text-right font-medium">{pct(p.latest?.irr_levered, 1)}</TD>
              <TD className="text-right">{mult(p.latest?.equity_multiple)}</TD>
              <TD className="text-right">{mult(p.latest?.dscr)}</TD>
              <TD>
                <RiskBadge level={p.latest?.risk_level} score={p.latest?.risk_score} />
              </TD>
              <TD className="text-muted-foreground">{p.owner_name ?? "—"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

function Kanban({ deals }: { deals: Property[] }) {
  const qc = useQueryClient();
  const org = useOrgKey();
  const { hasRole } = useAuth();
  const [dragId, setDragId] = useState<string | null>(null);
  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api(`/api/properties/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org] }),
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="grid grid-cols-1 gap-3 overflow-x-auto pb-2 md:grid-cols-5">
      {STATUSES.map((s) => {
        const col = deals.filter((d) => d.status === s);
        return (
          <div
            key={s}
            className={cn("min-w-56 rounded-lg border bg-muted/40 p-2", dragId && "outline-dashed outline-1 outline-border")}
            onDragOver={(e) => hasRole("analyst") && e.preventDefault()}
            onDrop={() => {
              if (dragId) move.mutate({ id: dragId, status: s });
              setDragId(null);
            }}
          >
            <div className="mb-2 flex items-center justify-between px-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {STATUS_LABELS[s]}
              <span className="tabular">
                {col.length} · {usdShort(col.reduce((a, d) => a + (d.purchase_price ?? 0), 0))}
              </span>
            </div>
            <div className="space-y-2">
              {col.map((p) => (
                <Link
                  key={p.id}
                  href={`/deals/${p.id}`}
                  draggable={hasRole("analyst")}
                  onDragStart={() => setDragId(p.id)}
                  className="block rounded-md border bg-card p-3 shadow-xs transition-shadow hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-medium leading-snug">{stripDemo(p.name)}</div>
                    {p.is_demo && <DemoBadge />}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {TYPE_LABELS[p.property_type]} · {p.city ?? "—"}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs tabular">
                    <span>{usdShort(p.purchase_price)}</span>
                    <span className="font-medium">{pct(p.latest?.irr_levered, 1)} IRR</span>
                  </div>
                </Link>
              ))}
              {col.length === 0 && <div className="px-1.5 py-4 text-center text-xs text-muted-foreground">No deals</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function DealsPage() {
  return (
    <Suspense>
      <DealsInner />
    </Suspense>
  );
}
