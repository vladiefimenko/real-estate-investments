"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, FileDown, PieChart } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SERIES } from "@/components/charts";
import { EmptyState, ErrorBlock, LoadingBlock, Metric, PageHeader, TermInfo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch } from "@/components/ui/overlays";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api, rawFetch } from "@/lib/api";
import { pct, usdShort } from "@/lib/format";
import { cn } from "@/lib/utils";

type Dim = "market" | "state" | "property_type" | "sponsor" | "vintage" | "stage";

interface Segment {
  segment: string;
  deals: number;
  volume: number;
  share: number | null;
  noi: number;
  noi_share: number | null;
  cap_rate: number | null;
  irr_levered: number | null;
  risk_score: number | null;
  return_per_risk: number | null;
  deal_names: string[];
}

interface Portfolio {
  dimension: Dim;
  dimension_label: string;
  dimensions: Record<Dim, string>;
  segments: Segment[];
  totals: { deals: number; volume: number; noi: number; irr_levered: number | null };
  concentration: { hhi: number | null; top_share: number | null; level: "low" | "moderate" | "high" | null; flags: string[] };
  demo_deals: number;
}

const SCOPES: Record<string, { label: string; statuses: string | null }> = {
  active: { label: "Active (not passed)", statuses: null },
  closed: { label: "Closed (owned)", statuses: "closed" },
  pipeline: { label: "Pipeline (not yet closed)", statuses: "sourcing,underwriting,ic" },
  all: { label: "All, including passed", statuses: "sourcing,underwriting,ic,closed,passed" },
};
const DIM_ORDER: Dim[] = ["market", "property_type", "sponsor", "vintage", "state", "stage"];

export default function PortfolioPage() {
  const org = useOrgKey();
  const [dim, setDim] = useState<Dim>("market");
  const [scope, setScope] = useState("active");
  const [demo, setDemo] = useState(true);
  const [reportOpen, setReportOpen] = useState(false);
  const statuses = SCOPES[scope].statuses;
  const qs = new URLSearchParams({ dimension: dim, include_demo: String(demo), ...(statuses ? { status: statuses } : {}) }).toString();
  const q = useQuery({ queryKey: [org, "portfolio", qs], queryFn: () => api<Portfolio>(`/api/portfolio?${qs}`), placeholderData: keepPreviousData });
  const d = q.data;

  return (
    <>
      <PageHeader
        title="Portfolio"
        description="Where your capital is concentrated and how each part of the portfolio is performing, by market, type, sponsor, vintage or stage."
        actions={
          <>
            <Select aria-label="Deals to include" value={scope} onChange={(e) => setScope(e.target.value)} className="w-52">
              {Object.entries(SCOPES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </Select>
            <label className="flex h-9 items-center gap-2 rounded-md border bg-card px-3 text-sm">
              <Switch checked={demo} onCheckedChange={setDemo} aria-label="Include demo deals" /> Demo deals
            </label>
            <Button onClick={() => setReportOpen(true)}>
              <FileDown /> Build report
            </Button>
          </>
        }
      />
      <div className="mb-4 flex flex-wrap gap-1.5" role="tablist" aria-label="Break down by">
        {DIM_ORDER.map((k) => (
          <Button key={k} role="tab" aria-selected={dim === k} size="sm" variant={dim === k ? "secondary" : "ghost"} onClick={() => setDim(k)}>
            {d?.dimensions?.[k] ?? k}
          </Button>
        ))}
      </div>
      {q.isLoading && <LoadingBlock rows={6} />}
      {q.error && <ErrorBlock error={q.error} />}
      {d && d.totals.deals === 0 && <EmptyState icon={PieChart} title="No deals match" description="Change the filters at the top, or add deals to see portfolio analytics." />}
      {d && d.totals.deals > 0 && (
        <div className={cn("space-y-5", q.isFetching && "opacity-70 transition-opacity")}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label="Deals" value={d.totals.deals} sub={d.demo_deals ? `${d.demo_deals} demo` : undefined} />
            <Metric label="Volume" value={usdShort(d.totals.volume)} sub="Purchase prices" />
            <Metric label="Year-1 NOI" term="noi" value={usdShort(d.totals.noi)} />
            <Metric label="Equity-weighted IRR" term="irr" value={pct(d.totals.irr_levered, 1)} hint="Levered IRR of each deal weighted by the equity it needs." />
          </div>

          {d.concentration.hhi !== null && d.segments.length > 1 && (
            <div
              className={cn(
                "flex items-start gap-3 rounded-md border px-4 py-3 text-sm",
                d.concentration.level === "high" ? "border-warning/40 bg-warning/8" : "bg-card",
              )}
            >
              {d.concentration.level === "high" && <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />}
              <div>
                <span className="font-medium">
                  Concentration by {d.dimension_label.toLowerCase()}: {d.concentration.level}
                </span>{" "}
                <span className="text-muted-foreground">
                  (HHI {d.concentration.hhi.toFixed(2)}; the largest segment is {pct(d.concentration.top_share, 0)} of volume)
                </span>
                {d.concentration.flags.length > 0 && <div className="mt-0.5">Above the 40% single-segment guideline: {d.concentration.flags.join("; ")}.</div>}
                <div className="mt-1 text-xs text-muted-foreground">HHI is the sum of squared shares: below 0.15 is diversified, above 0.25 is concentrated.</div>
              </div>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>By {d.dimension_label.toLowerCase()}</CardTitle>
              <CardDescription>Base-case figures from each deal&apos;s latest calculation. Hover a bar for the deals in that segment.</CardDescription>
            </CardHeader>
            <CardContent className="px-0 pb-2">
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH className="pl-5">{d.dimension_label}</TH>
                    <TH className="text-right">Deals</TH>
                    <TH className="text-right">Volume</TH>
                    <TH className="w-48">Share of volume</TH>
                    <TH className="text-right">NOI share</TH>
                    <TH className="text-right">Cap rate</TH>
                    <TH className="text-right">Lev. IRR</TH>
                    <TH className="text-right">Risk</TH>
                    <TH className="pr-5 text-right">
                      <span className="inline-flex items-center gap-1">
                        IRR / risk
                        <TermInfo term="risk-score" label="Risk score" note="Equity-weighted levered IRR per 10 points of Axiom risk score. Higher means more return for the risk taken." />
                      </span>
                    </TH>
                  </TR>
                </THead>
                <TBody>
                  {d.segments.map((s) => (
                    <TR key={s.segment}>
                      <TD className="pl-5 font-medium">{s.segment}</TD>
                      <TD className="text-right tabular">{s.deals}</TD>
                      <TD className="text-right tabular">{usdShort(s.volume)}</TD>
                      <TD>
                        <div className="flex items-center gap-2" title={`${s.segment}: ${s.deal_names.join(", ")}`}>
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full" style={{ width: `${(s.share ?? 0) * 100}%`, background: SERIES[0] }} />
                          </div>
                          <span className="w-10 text-right text-xs tabular">{pct(s.share, 0)}</span>
                        </div>
                      </TD>
                      <TD className="text-right tabular">{pct(s.noi_share, 0)}</TD>
                      <TD className="text-right tabular">{pct(s.cap_rate)}</TD>
                      <TD className="text-right tabular">{pct(s.irr_levered, 1)}</TD>
                      <TD className="text-right tabular">{s.risk_score === null ? "—" : s.risk_score.toFixed(0)}</TD>
                      <TD className="pr-5 text-right tabular">{s.return_per_risk === null ? "—" : pct(s.return_per_risk, 1)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
      <ReportDialog open={reportOpen} onOpenChange={setReportOpen} dimensions={d?.dimensions} scope={scope} demo={demo} />
    </>
  );
}

function ReportDialog({ open, onOpenChange, dimensions, scope, demo }: { open: boolean; onOpenChange: (o: boolean) => void; dimensions?: Record<Dim, string>; scope: string; demo: boolean }) {
  const [title, setTitle] = useState("Portfolio Review");
  const [dims, setDims] = useState<Dim[]>(["market", "property_type", "sponsor"]);
  const [deals, setDeals] = useState(true);
  const [conc, setConc] = useState(true);
  const [busy, setBusy] = useState(false);
  const statuses = SCOPES[scope].statuses;

  const build = async () => {
    setBusy(true);
    try {
      const r = await rawFetch("/api/reports/portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim() || "Portfolio Review", dimensions: dims, statuses: statuses ? statuses.split(",") : null, include_demo: demo, include_deal_list: deals, include_concentration: conc }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "Couldn't build the report");
      }
      const blob = await r.blob();
      const name = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") ?? "")?.[1] ?? "portfolio.pdf";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Portfolio report downloaded");
      onOpenChange(false);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Build a portfolio report" description={`A PDF for your board or investment committee, using the deals currently selected (${SCOPES[scope].label.toLowerCase()}${demo ? ", including demo deals" : ""}).`}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (dims.length) build();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="pr-title">Title</Label>
            <Input id="pr-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">Breakdowns to include</legend>
            <div className="grid grid-cols-2 gap-1.5">
              {DIM_ORDER.map((k) => (
                <label key={k} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm">
                  <input type="checkbox" checked={dims.includes(k)} onChange={(e) => setDims(e.target.checked ? [...dims, k] : dims.filter((x) => x !== k))} />
                  {dimensions?.[k] ?? k}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Switch id="pr-conc" checked={conc} onCheckedChange={setConc} />
              <Label htmlFor="pr-conc">Concentration notes</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="pr-deals" checked={deals} onCheckedChange={setDeals} />
              <Label htmlFor="pr-deals">List every deal on the last page</Label>
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={!dims.length} loading={busy}>
              <FileDown /> Download PDF
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
