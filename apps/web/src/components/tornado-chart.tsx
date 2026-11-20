"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { LoadingBlock, TermInfo } from "@/components/common";
import { SectionCard } from "@/components/deal-widgets";
import { Select } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { mult, pct, usdShort } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Driver {
  path: string;
  label: string;
  kind: "pct" | "usd" | "int";
  base_value: number;
  low_value: number;
  high_value: number;
  irr_low: number;
  irr_high: number;
  em_low: number | null;
  em_high: number | null;
}

interface Tornado {
  scenario_name: string;
  metric: "irr_levered" | "irr_unlevered";
  base_irr: number | null;
  base_em: number | null;
  drivers: Driver[];
}

const fmtInput = (d: Driver, v: number) => (d.kind === "pct" ? pct(v) : d.kind === "usd" ? usdShort(v) : `${v} yrs`);

/** Ranked one-at-a-time sensitivity: which assumptions move returns the most. */
export function TornadoChart({ propertyId, scenarioId, resultId }: { propertyId: string; scenarioId?: string; resultId?: string }) {
  const org = useOrgKey();
  const [metric, setMetric] = useState<"irr" | "em">("irr");
  const { data, isLoading } = useQuery({
    queryKey: [org, "tornado", propertyId, scenarioId, resultId],
    queryFn: () => api<Tornado>(`/api/properties/${propertyId}/tornado${scenarioId ? `?scenario_id=${scenarioId}` : ""}`),
  });

  const pick = (d: Driver, side: "low" | "high") => (metric === "irr" ? d[`irr_${side}`] : d[`em_${side}`]);
  const base = metric === "irr" ? data?.base_irr : data?.base_em;
  const fmt = (v: number | null | undefined) => (metric === "irr" ? pct(v) : mult(v));
  const rows = (data?.drivers ?? []).filter((d) => pick(d, "low") !== null && pick(d, "high") !== null);
  const span = Math.max(1e-9, ...rows.flatMap((d) => [Math.abs((pick(d, "low") ?? 0) - (base ?? 0)), Math.abs((pick(d, "high") ?? 0) - (base ?? 0))]));
  const at = (v: number) => 50 + ((v - (base ?? 0)) / span) * 46; // % position, base at the centre

  return (
    <SectionCard
      title="What moves returns the most"
      description="Tornado chart: each row runs the deal twice, with only that assumption moved down and up by the step shown. Longest bars matter most."
      action={
        <Select value={metric} onChange={(e) => setMetric(e.target.value as "irr" | "em")} className="w-44" aria-label="Metric">
          <option value="irr">{data?.metric === "irr_unlevered" ? "Unlevered IRR" : "Levered IRR"}</option>
          <option value="em">Equity multiple</option>
        </Select>
      }
    >
      {isLoading || !data ? (
        <LoadingBlock rows={4} />
      ) : (
        <div className="space-y-3">
          <p className="flex items-center gap-1 text-sm">
            {data.scenario_name}: {metric === "irr" ? "IRR" : "equity multiple"} <span className="font-semibold">{fmt(base)}</span>
            <TermInfo term={metric === "irr" ? "irr" : "equity-multiple"} />
          </p>
          <div className="flex justify-between text-[11px] text-muted-foreground" aria-hidden>
            <span>Worse</span>
            <span>Base</span>
            <span>Better</span>
          </div>
          <ul className="space-y-2.5" aria-label="Drivers ranked by impact">
            {rows.map((d) => {
              const lo = pick(d, "low") as number;
              const hi = pick(d, "high") as number;
              const left = Math.min(at(lo), at(hi));
              const right = Math.max(at(lo), at(hi));
              const lowIsWorse = lo < hi;
              return (
                <li key={d.path} className="grid grid-cols-[minmax(0,11rem)_1fr] items-center gap-3 text-sm sm:grid-cols-[minmax(0,13rem)_1fr]">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{d.label}</div>
                    <div className="truncate text-[11px] text-muted-foreground">
                      {fmtInput(d, d.low_value)} ↔ {fmtInput(d, d.high_value)} (base {fmtInput(d, d.base_value)})
                    </div>
                  </div>
                  <div className="relative h-7" role="img" aria-label={`${d.label}: ${fmt(lo)} at ${fmtInput(d, d.low_value)}, ${fmt(hi)} at ${fmtInput(d, d.high_value)}`}>
                    <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                    <span
                      className={cn("absolute inset-y-1 rounded-l", "bg-destructive/60")}
                      style={{ left: `${left}%`, width: `${Math.max(0, 50 - left)}%` }}
                    />
                    <span
                      className={cn("absolute inset-y-1 rounded-r", "bg-success/60")}
                      style={{ left: "50%", width: `${Math.max(0, right - 50)}%` }}
                    />
                    <span
                      className={cn("absolute top-1/2 -translate-y-1/2 text-[11px] tabular", left < 15 ? "pl-1" : "pr-1")}
                      style={left < 15 ? { left: `${left}%` } : { right: `${100 - left}%` }}
                    >
                      {fmt(lowIsWorse ? lo : hi)}
                    </span>
                    <span
                      className={cn("absolute top-1/2 -translate-y-1/2 text-[11px] tabular", right > 85 ? "pr-1" : "pl-1")}
                      style={right > 85 ? { right: `${100 - right}%` } : { left: `${right}%` }}
                    >
                      {fmt(lowIsWorse ? hi : lo)}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-muted-foreground">
            Steps: rent and expense growth ±1 pt, vacancy ±2 pts, exit cap ±0.5 pt, price ±5%, interest rate ±1 pt, hold ±2 years. Red is the
            downside, green the upside.
          </p>
        </div>
      )}
    </SectionCard>
  );
}
