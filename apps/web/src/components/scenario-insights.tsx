"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { LoadingBlock, TermInfo } from "@/components/common";
import { SectionCard } from "@/components/deal-widgets";
import { Select } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { pct, usdShort } from "@/lib/format";
import type { ScenarioComparisonRow } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Driver {
  key: string;
  label: string;
  kind: "pct" | "usd" | "int" | "other";
  base_value: number | null;
  scenario_value: number | null;
  irr_impact: number | null;
}

interface Explanation {
  scenario_name: string;
  base_name: string;
  metric: "irr_levered" | "irr_unlevered";
  base_irr: number | null;
  scenario_irr: number | null;
  total_change: number | null;
  interaction: number | null;
  drivers: Driver[];
}

/** Percentage-point change, e.g. -0.0312 → "−3.1 pts". */
const pts = (v: number | null) => (v === null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(1)} pts`);

function fmtValue(d: Driver, v: number | null) {
  if (v === null) return "";
  if (d.kind === "pct") return pct(v);
  if (d.kind === "usd") return usdShort(v);
  if (d.kind === "int") return d.key === "hold_period_years" ? `${v} yrs` : String(v);
  return String(v);
}

function describeChange(d: Driver) {
  if (d.kind === "other" || d.base_value === null || d.scenario_value === null) return `${d.label} changed`;
  return `${d.label} ${fmtValue(d, d.base_value)} → ${fmtValue(d, d.scenario_value)}`;
}

function Summary({ e }: { e: Explanation }) {
  const irrName = e.metric === "irr_levered" ? "levered IRR" : "unlevered IRR";
  if (e.drivers.length === 0) return <p className="text-sm">{e.scenario_name} uses the same assumptions as {e.base_name}.</p>;
  const top = e.drivers.filter((d) => d.irr_impact !== null).slice(0, 2);
  const direction = (e.total_change ?? 0) < 0 ? "lower" : "raise";
  return (
    <p className="text-sm leading-relaxed">
      <span className="font-medium">{e.scenario_name}</span> changes {e.drivers.length} assumption{e.drivers.length === 1 ? "" : "s"} from {e.base_name}.
      Together they {direction} {irrName} from <span className="font-medium">{pct(e.base_irr)}</span> to{" "}
      <span className="font-medium">{pct(e.scenario_irr)}</span> ({pts(e.total_change)}).
      {top.length > 0 && (
        <>
          {" "}
          The biggest driver is <span className="font-medium">{describeChange(top[0]).toLowerCase()}</span>, which on its own moves IRR by{" "}
          {pts(top[0].irr_impact)}
          {top[1] && (
            <>
              , followed by {describeChange(top[1]).toLowerCase()} ({pts(top[1].irr_impact)})
            </>
          )}
          .
        </>
      )}
    </p>
  );
}

/** Plain-language "what changed vs the base case", with each driver's IRR impact computed by the engine. */
export function ScenarioInsights({ rows }: { rows: ScenarioComparisonRow[] }) {
  const org = useOrgKey();
  const others = rows.filter((r) => !r.is_base);
  const [picked, setPicked] = useState<string | null>(null);
  const selected = others.find((r) => r.scenario_id === picked) ?? others[0];
  const { data, isLoading } = useQuery({
    queryKey: [org, "scenario-explain", selected?.scenario_id, selected?.metrics?.result_id],
    queryFn: () => api<Explanation>(`/api/scenarios/${selected!.scenario_id}/explain`),
    enabled: Boolean(selected),
  });
  if (!selected) return null;
  const max = Math.max(1e-9, ...(data?.drivers ?? []).map((d) => Math.abs(d.irr_impact ?? 0)));

  return (
    <SectionCard
      title="What changed, and why it matters"
      description="Each bar is a full engine run of the base case with only that one assumption changed."
      action={
        others.length > 1 && (
          <Select value={selected.scenario_id} onChange={(e) => setPicked(e.target.value)} className="w-48" aria-label="Scenario to explain">
            {others.map((r) => (
              <option key={r.scenario_id} value={r.scenario_id}>
                {r.name}
              </option>
            ))}
          </Select>
        )
      }
    >
      {isLoading || !data ? (
        <LoadingBlock rows={3} />
      ) : (
        <div className="space-y-4">
          <Summary e={data} />
          {data.drivers.length > 0 && (
            <ul className="space-y-2" aria-label="IRR impact by assumption">
              {data.drivers.map((d) => {
                const v = d.irr_impact ?? 0;
                return (
                  <li key={d.key} className="grid grid-cols-[minmax(0,14rem)_1fr_4.5rem] items-center gap-3 text-sm">
                    <span className="truncate" title={describeChange(d)}>
                      {describeChange(d)}
                    </span>
                    <span className="relative h-3 rounded bg-muted" aria-hidden>
                      <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                      <span
                        className={cn("absolute inset-y-0 rounded", v < 0 ? "right-1/2 bg-destructive/70" : "left-1/2 bg-success/70")}
                        style={{ width: `${(Math.abs(v) / max) * 50}%` }}
                      />
                    </span>
                    <span className={cn("text-right tabular", v < 0 ? "text-destructive" : v > 0 ? "text-success" : "")}>{pts(d.irr_impact)}</span>
                  </li>
                );
              })}
            </ul>
          )}
          {data.interaction !== null && Math.abs(data.interaction) >= 0.001 && (
            <p className="text-xs text-muted-foreground">
              The single impacts don&apos;t add up exactly: {pts(data.interaction)} comes from the changes working together (for example, higher vacancy
              hurts more when rents also grow slower).
            </p>
          )}
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            1 pt = one percentage point of IRR. <TermInfo term="sensitivity" label="sensitivity analysis" /> Try the sensitivity table below to explore
            any two drivers together.
          </p>
        </div>
      )}
    </SectionCard>
  );
}
