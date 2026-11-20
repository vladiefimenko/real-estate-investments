"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, Gauge } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorBlock, LoadingBlock, Metric, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api, download } from "@/lib/api";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

type Stage = "sourcing" | "underwriting" | "ic" | "closed";

interface Metrics {
  deals: number;
  funnel: Record<Stage | "passed", number>;
  conversion: Record<string, number | null>;
  win_rate: number | null;
  decided: number;
  avg_days_in_stage: Record<Stage, number | null>;
  in_stage_now: Record<"sourcing" | "underwriting" | "ic", { count: number; avg_days: number | null }>;
  median_days_to_close: number | null;
  avg_irr_closed: number | null;
  closed_with_irr: number;
}

interface Velocity {
  days: number;
  mine: Metrics;
  workspace: Metrics;
  owners: number;
}

const STAGES: [Stage, string][] = [
  ["sourcing", "Sourcing"],
  ["underwriting", "Underwriting"],
  ["ic", "Investment Committee"],
  ["closed", "Closed"],
];

const PERIODS: [number, string][] = [
  [90, "Last 90 days"],
  [180, "Last 6 months"],
  [365, "Last 12 months"],
  [0, "All time"],
];

const p = (v: number | null) => (v === null ? "—" : pct(v, 0));
const days = (v: number | null) => (v === null ? "—" : `${num(v, 1)} days`);

function Funnel({ m }: { m: Metrics }) {
  const max = Math.max(m.funnel.sourcing, 1);
  return (
    <ol className="space-y-2.5" aria-label="Deals reaching each stage">
      {STAGES.map(([key, label], i) => {
        const n = m.funnel[key];
        const conv = i > 0 ? m.conversion[`${STAGES[i - 1][0]}_to_${key}`] : null;
        return (
          <li key={key} className="grid grid-cols-[150px_1fr] items-center gap-3 text-sm">
            <span className="text-muted-foreground">{label}</span>
            <span className="flex items-center gap-2" title={`${label}: ${n} deal${n === 1 ? "" : "s"}${conv !== null ? `, ${p(conv)} of the previous stage` : ""}`}>
              <span className="h-6 rounded-[4px] bg-accent" style={{ width: `${Math.max((n / max) * 100, n ? 2 : 0)}%` }} />
              <span className="shrink-0 tabular font-medium">{n}</span>
              {conv !== null && <span className="shrink-0 text-xs text-muted-foreground">{p(conv)} moved on</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const ROWS: { label: string; value: (m: Metrics) => string; better?: "high" | "low"; raw?: (m: Metrics) => number | null }[] = [
  { label: "Deals in period", value: (m) => String(m.deals) },
  { label: "Sourcing → underwriting", value: (m) => p(m.conversion.sourcing_to_underwriting), better: "high", raw: (m) => m.conversion.sourcing_to_underwriting },
  { label: "Underwriting → IC", value: (m) => p(m.conversion.underwriting_to_ic), better: "high", raw: (m) => m.conversion.underwriting_to_ic },
  { label: "IC → closed", value: (m) => p(m.conversion.ic_to_closed), better: "high", raw: (m) => m.conversion.ic_to_closed },
  { label: "Win rate (closed ÷ decided)", value: (m) => p(m.win_rate), better: "high", raw: (m) => m.win_rate },
  { label: "Avg days in sourcing", value: (m) => days(m.avg_days_in_stage.sourcing), better: "low", raw: (m) => m.avg_days_in_stage.sourcing },
  { label: "Avg days in underwriting", value: (m) => days(m.avg_days_in_stage.underwriting), better: "low", raw: (m) => m.avg_days_in_stage.underwriting },
  { label: "Avg days at IC", value: (m) => days(m.avg_days_in_stage.ic), better: "low", raw: (m) => m.avg_days_in_stage.ic },
  { label: "Median days to close", value: (m) => days(m.median_days_to_close), better: "low", raw: (m) => m.median_days_to_close },
  { label: "Avg levered IRR of closed deals", value: (m) => (m.avg_irr_closed === null ? "—" : pct(m.avg_irr_closed, 1)), better: "high", raw: (m) => m.avg_irr_closed },
];

export default function ScorecardPage() {
  const org = useOrgKey();
  const [period, setPeriod] = useState(365);
  const q = useQuery({ queryKey: [org, "velocity", period], queryFn: () => api<Velocity>(`/api/insights/velocity?days=${period}`) });
  const [exporting, setExporting] = useState(false);
  const exportCsv = async () => {
    setExporting(true);
    try {
      await download(`/api/insights/scorecard.csv?days=${period}`, "pipeline-scorecard.csv");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Pipeline scorecard"
        description="How your deals move through the pipeline: how many reach each stage, how long each stage takes, and how often they close. Demo deals don't count."
        actions={
          <div className="flex gap-2">
            <Select aria-label="Period" value={period} onChange={(e) => setPeriod(Number(e.target.value))} className="w-40">
              {PERIODS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
            <Button variant="outline" onClick={exportCsv} loading={exporting} disabled={!q.data}>
              <Download /> Scorecard CSV
            </Button>
          </div>
        }
      />
      {q.isLoading && <LoadingBlock rows={6} />}
      {q.error && <ErrorBlock error={q.error} />}
      {q.data && q.data.workspace.deals === 0 && (
        <EmptyState
          icon={Gauge}
          title="No deals in this period yet"
          description="Create deals and move them through the stages (Sourcing → Underwriting → IC → Closed or Passed). Your speed and win rate will appear here."
          action={
            <Button asChild>
              <Link href="/deals?new=1">New deal</Link>
            </Button>
          }
        />
      )}
      {q.data && q.data.workspace.deals > 0 && (
        <Body v={q.data} />
      )}
    </>
  );
}

function Body({ v }: { v: Velocity }) {
  const m = v.mine;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Your deals" value={m.deals} sub={`${m.funnel.closed} closed · ${m.funnel.passed} passed`} />
        <Metric label="Win rate" value={p(m.win_rate)} sub={m.decided ? `of ${m.decided} decided deal${m.decided === 1 ? "" : "s"}` : "No closed or passed deals yet"} hint="Closed deals divided by deals that were either closed or passed." />
        <Metric label="Median days to close" value={days(m.median_days_to_close)} sub="From creating the deal to Closed" />
        <Metric label="Avg IRR of closed deals" value={m.avg_irr_closed === null ? "—" : pct(m.avg_irr_closed, 1)} term="irr" sub={m.closed_with_irr ? `${m.closed_with_irr} deal${m.closed_with_irr === 1 ? "" : "s"}, base case levered IRR` : "No closed deals yet"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Your funnel</CardTitle>
            <CardDescription>Deals that reached each stage. A deal moved straight to a later stage counts for the stages before it.</CardDescription>
          </CardHeader>
          <CardContent>
            {m.deals ? <Funnel m={m} /> : <p className="text-sm text-muted-foreground">You don&apos;t own any deals in this period. The workspace figures are on the right.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Waiting right now</CardTitle>
            <CardDescription>Your open deals and how long they&apos;ve been in their current stage.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm">
              {(["sourcing", "underwriting", "ic"] as const).map((s) => {
                const now = m.in_stage_now[s];
                const avg = v.workspace.avg_days_in_stage[s];
                const slow = now.avg_days !== null && avg !== null && now.avg_days > avg * 1.5 && now.avg_days > 7;
                return (
                  <li key={s} className="flex items-center justify-between gap-3 border-b pb-2.5 last:border-0">
                    <span>{STAGES.find(([k]) => k === s)?.[1]}</span>
                    <span className={cn("tabular", slow && "text-warning")}>
                      {now.count} deal{now.count === 1 ? "" : "s"}
                      {now.avg_days !== null && ` · ${days(now.avg_days)} on average`}
                      {slow && " · slower than usual"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>You vs the workspace</CardTitle>
          <CardDescription>
            The workspace column covers all {v.workspace.deals} deals by {v.owners} {v.owners === 1 ? "person" : "people"}, as one combined figure. No one else&apos;s name or numbers are shown.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Metric</TH>
                <TH className="text-right">You</TH>
                <TH className="text-right">Workspace</TH>
              </TR>
            </THead>
            <TBody>
              {ROWS.map((r) => {
                const a = r.raw?.(m) ?? null;
                const b = r.raw?.(v.workspace) ?? null;
                const ahead = a !== null && b !== null && a !== b && (r.better === "high" ? a > b : a < b);
                return (
                  <TR key={r.label}>
                    <TD>{r.label}</TD>
                    <TD className={cn("text-right tabular font-medium", ahead && "text-success")}>{r.value(m)}</TD>
                    <TD className="text-right tabular text-muted-foreground">{r.value(v.workspace)}</TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
