"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Columns3, Plus, Rows3, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { DemoBadge, EmptyState, ErrorBlock, LoadingBlock, PageHeader, RiskBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { NewDealWizard } from "@/components/new-deal-wizard";
import { Card, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey, useProperties, usePropertyTypes } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { mult, pct, STATUS_LABELS, STATUSES, stripDemo, TYPE_LABELS, usd, usdShort } from "@/lib/format";
import type { Property } from "@/lib/types";
import { cn } from "@/lib/utils";

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
          hasRole("analyst") && (
            <Button onClick={() => setOpen(true)}>
              <Plus /> New deal
            </Button>
          )
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
      {data && data.length > 0 && (view === "table" ? <DealTable deals={data} onOpen={(id) => router.push(`/deals/${id}`)} /> : <Kanban deals={data} />)}
      <NewDealWizard open={open} onOpenChange={setOpen} />
    </>
  );
}

function DealTable({ deals, onOpen }: { deals: Property[]; onOpen: (id: string) => void }) {
  return (
    <Card>
      <Table>
        <THead>
          <TR className="hover:bg-transparent">
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
            <TR key={p.id} className="cursor-pointer" onClick={() => onOpen(p.id)}>
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
    <div className="grid gap-3 overflow-x-auto pb-2 md:grid-cols-5">
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
