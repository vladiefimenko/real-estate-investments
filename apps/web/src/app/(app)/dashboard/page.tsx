"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Building2, Plus } from "lucide-react";
import Link from "next/link";
import { Fragment } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_PROPS, BAR_RADIUS, ChartTooltip, GRID_PROPS, SERIES } from "@/components/charts";
import { DashboardViewControls, useDashboardLayout } from "@/components/dashboard-views";
import type { Layout, MetricKey, SectionKey } from "@/components/dashboard-views";
import { EmptyState, ErrorBlock, LoadingBlock, Metric, PageHeader, StatusBadge } from "@/components/common";
import { GettingStarted } from "@/components/getting-started";
import { WeeklyProgress } from "@/components/weekly-progress";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/overlays";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Select } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Property } from "@/lib/types";
import { pct, relativeTime, STATUS_LABELS, stripDemo, TYPE_LABELS, usdShort } from "@/lib/format";

interface Dashboard {
  totals: {
    deals: number;
    active_deals: number;
    pipeline_volume: number;
    aum: number;
    weighted_avg_cap_rate: number | null;
    irr_min: number | null;
    irr_max: number | null;
    irr_median: number | null;
    demo_deals: number;
  };
  pipeline: { status: string; count: number; volume: number }[];
  exposure_by_type: { key: string; value: number }[];
  exposure_by_state: { key: string; value: number }[];
  alerts: { property_id: string; name: string; severity: string; message: string }[];
  recent_activity: {
    action: string;
    entity_type: string;
    user_name: string | null;
    property_name: string | null;
    property_id: string | null;
    created_at: string;
    details: Record<string, unknown>;
  }[];
}

const ACTION_LABELS: Record<string, string> = {
  "underwriting.run": "ran underwriting",
  "property.create": "created deal",
  "property.update": "updated deal",
  "document.upload": "uploaded a document to",
  "document.extract": "extracted data from a document on",
  "extraction.accept": "verified a field on",
  "extraction.edit": "edited a field on",
  "extraction.reject": "rejected a field on",
  "extraction.apply": "applied verified data to",
  "scenario.create": "created a scenario on",
  "scenario.update": "updated assumptions on",
  "financing.activate": "activated financing on",
  "report.excel": "exported the Excel model for",
  "report.one_pager": "exported the one-pager for",
  "report.ic_memo": "generated the IC memo for",
  "analyst.question": "asked the analyst about",
};

export default function DashboardPage() {
  const org = useOrgKey();
  const { hasRole, me } = useAuth();
  const ctl = useDashboardLayout();
  const { layout } = ctl;
  const f = layout.filters;
  const setFilter = (next: Partial<Layout["filters"]>) => ctl.edit({ filters: { ...f, ...next } });
  const qs = new URLSearchParams({
    ...(f.property_type && { property_type: f.property_type }),
    ...(f.status && { status: f.status }),
    ...(f.mine_only && me && { owner_id: me.user.id }),
  }).toString();
  const { data, isLoading, error } = useQuery({
    queryKey: [org, "dashboard", qs],
    queryFn: () => api<Dashboard>(`/api/dashboard${qs ? `?${qs}` : ""}`),
    enabled: ctl.ready,
  });

  const metrics: Record<MetricKey, (d: Dashboard) => React.ReactNode> = {
    active_deals: (d) => <Metric key="active_deals" label="Active deals" value={d.totals.active_deals} sub={`${d.totals.deals} total`} />,
    pipeline_volume: (d) => (
      <Metric key="pipeline_volume" label="Pipeline volume" term="pipeline" hint="Purchase prices of deals from Sourcing through Investment Committee." value={usdShort(d.totals.pipeline_volume)} sub="Sourcing → IC" />
    ),
    aum: (d) => <Metric key="aum" label="AUM (closed)" term="aum" value={usdShort(d.totals.aum)} />,
    cap_rate: (d) => (
      <Metric
        key="cap_rate"
        label="Wtd. avg cap rate"
        term="cap-rate"
        value={pct(d.totals.weighted_avg_cap_rate)}
        hint="On this dashboard: going-in cap rates weighted by purchase price, excluding passed deals."
      />
    ),
    irr_median: (d) => <Metric key="irr_median" label="Median levered IRR" term="irr" value={pct(d.totals.irr_median, 1)} hint="On this dashboard: base scenarios, latest calculation." />,
    irr_range: (d) => (
      <Metric
        key="irr_range"
        label="IRR range"
        value={
          <span className="text-base">
            {pct(d.totals.irr_min, 1)} – {pct(d.totals.irr_max, 1)}
          </span>
        }
      />
    ),
  };

  const sections: Record<SectionKey, (data: Dashboard) => React.ReactNode> = {
    pipeline: (data) => (
      <Card className="xl:col-span-4">
        <CardHeader>
          <CardTitle>Pipeline by stage</CardTitle>
          <CardDescription>Deal volume (purchase price) at each stage.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={data.pipeline.map((p) => ({ ...p, label: STATUS_LABELS[p.status] }))} barCategoryGap="30%">
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="label" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} tickFormatter={(v) => usdShort(v)} width={64} axisLine={false} />
                <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={usdShort} />} />
                <Bar dataKey="volume" name="Volume" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 grid grid-cols-5 gap-2 text-center text-xs">
            {data.pipeline.map((p) => (
              <Link
                key={p.status}
                href={`/deals?status=${p.status}`}
                className="rounded-md border px-2 py-1.5 transition-colors hover:bg-muted"
              >
                <div className="text-muted-foreground">{STATUS_LABELS[p.status]}</div>
                <div className="text-sm font-semibold tabular">{p.count}</div>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>
    ),
    exposure: (data) => (
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle>Exposure by property type</CardTitle>
          <CardDescription>Share of purchase price, excluding passed deals.</CardDescription>
        </CardHeader>
        <CardContent>
          <ExposureBars rows={data.exposure_by_type.map((r) => ({ ...r, key: TYPE_LABELS[r.key] ?? r.key }))} />
          <div className="mt-5 mb-2 text-xs font-medium text-muted-foreground">By state</div>
          <ExposureBars rows={data.exposure_by_state} />
        </CardContent>
      </Card>
    ),
    alerts: (data) => (
      <Card className="xl:col-span-3">
        <CardHeader>
          <CardTitle>Alerts</CardTitle>
          <CardDescription>Risk-screen flags and projected covenant breaches.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.alerts.length === 0 && <p className="text-sm text-muted-foreground">No alerts. All deals clear the screening thresholds.</p>}
          {data.alerts.map((a, i) => (
            <Link
              key={i}
              href={`/deals/${a.property_id}`}
              className="flex items-start gap-3 rounded-md border px-3 py-2.5 text-sm transition-colors hover:bg-muted"
            >
              <AlertTriangle className={a.severity === "high" ? "mt-0.5 size-4 text-destructive" : "mt-0.5 size-4 text-warning"} aria-label={a.severity} />
              <div className="min-w-0">
                <div className="font-medium">{stripDemo(a.name)}</div>
                <div className="text-muted-foreground">{a.message}</div>
              </div>
              <Badge variant={a.severity === "high" ? "danger" : "warning"} className="ml-auto shrink-0">
                {a.severity}
              </Badge>
            </Link>
          ))}
        </CardContent>
      </Card>
    ),
    activity: (data) => (
      <Card className="xl:col-span-3">
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>Audit trail across the workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2.5">
            {data.recent_activity.map((a, i) => (
              <li key={i} className="flex items-start gap-3 text-sm">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                <div className="min-w-0 flex-1">
                  <span className="font-medium">{a.user_name ?? "System"}</span>{" "}
                  <span className="text-muted-foreground">{ACTION_LABELS[a.action] ?? a.action}</span>{" "}
                  {a.property_id && a.property_name ? (
                    <Link href={`/deals/${a.property_id}`} className="font-medium hover:underline">
                      {stripDemo(a.property_name)}
                    </Link>
                  ) : null}
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(a.created_at)}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    ),
    recent_deals: () => (
      <div className="xl:col-span-6">
        <RecentDeals />
      </div>
    ),
  };

  return (
    <>
      <PageHeader
        title="Investment Dashboard"
        description="Pipeline, exposure and portfolio returns across your workspace."
        actions={
          <>
            <Select value={f.property_type ?? ""} onChange={(e) => setFilter({ property_type: e.target.value || null })} className="w-40" aria-label="Filter by property type">
              <option value="">All property types</option>
              {Object.entries(TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
            <Select value={f.status ?? ""} onChange={(e) => setFilter({ status: e.target.value || null })} className="w-40" aria-label="Filter by status">
              <option value="">All statuses</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
            <label className="flex h-9 items-center gap-2 rounded-md border bg-card px-3 text-sm">
              <Switch checked={f.mine_only} onCheckedChange={(v) => setFilter({ mine_only: v })} aria-label="Only my deals" />
              My deals
            </label>
            <DashboardViewControls ctl={ctl} />
            {hasRole("analyst") && (
              <Button asChild>
                <Link href="/deals?new=1">
                  <Plus /> New deal
                </Link>
              </Button>
            )}
          </>
        }
      />
      <GettingStarted />
      <WeeklyProgress />
      {(isLoading || !ctl.ready) && <LoadingBlock rows={6} />}
      {error && <ErrorBlock error={error} />}
      {data && data.totals.deals === 0 && (
        <EmptyState
          icon={Building2}
          title={qs ? "No deals match these filters" : "No deals yet"}
          description={qs ? "Change or clear the filters at the top to see more deals." : "Create your first deal to start underwriting."}
          action={
            hasRole("analyst") && !qs ? (
              <Button asChild>
                <Link href="/deals?new=1">Create a deal</Link>
              </Button>
            ) : undefined
          }
        />
      )}
      {data && data.totals.deals > 0 && (
        <div className="space-y-6">
          {data.totals.demo_deals > 0 && (
            <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <AlertTriangle className="size-3.5" />
              {data.totals.demo_deals} of {data.totals.deals} deals are fictional demo data, shown for demonstration purposes only.
            </div>
          )}
          {layout.metrics.length > 0 && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">{layout.metrics.map((k) => metrics[k](data))}</div>
          )}
          {layout.sections.length > 0 && (
            <div className="grid gap-4 xl:grid-cols-6">
              {layout.sections.map((k) => (
                <Fragment key={k}>{sections[k](data)}</Fragment>
              ))}
            </div>
          )}
          {layout.metrics.length + layout.sections.length === 0 && (
            <p className="rounded-md border p-6 text-center text-sm text-muted-foreground">Everything is hidden in this view. Use Views → Customize to show cards and sections.</p>
          )}
        </div>
      )}
    </>
  );
}

function ExposureBars({ rows }: { rows: { key: string; value: number }[] }) {
  const total = rows.reduce((s, r) => s + r.value, 0) || 1;
  return (
    <ul className="space-y-2">
      {rows.slice(0, 6).map((r) => (
        <li key={r.key}>
          <div className="mb-1 flex justify-between text-xs">
            <span>{r.key}</span>
            <span className="tabular text-muted-foreground">
              {usdShort(r.value)} · {pct(r.value / total, 0)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="presentation">
            <div className="h-full rounded-full" style={{ width: `${(r.value / total) * 100}%`, background: SERIES[0] }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function RecentDeals() {
  const org = useOrgKey();
  const { data } = useQuery({
    queryKey: [org, "properties", ""],
    queryFn: () => api<Property[]>("/api/properties"),
  });
  if (!data?.length) return null;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Recently updated deals</CardTitle>
          <CardDescription>Latest base-case returns.</CardDescription>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/deals">
            All deals <ArrowRight />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.slice(0, 6).map((p) => (
          <Link key={p.id} href={`/deals/${p.id}`} className="rounded-md border p-3.5 transition-colors hover:bg-muted/60">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-medium">{stripDemo(p.name)}</span>
              {p.is_demo && <Badge variant="demo">Demo</Badge>}
              <span className="ml-auto">
                <StatusBadge status={p.status} />
              </span>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {TYPE_LABELS[p.property_type]} · {[p.city, p.state].filter(Boolean).join(", ")}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div>
                <div className="text-muted-foreground">Price</div>
                <div className="font-semibold tabular">{usdShort(p.purchase_price)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Cap rate</div>
                <div className="font-semibold tabular">{pct(p.latest?.cap_rate)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Lev. IRR</div>
                <div className="font-semibold tabular">{pct(p.latest?.irr_levered, 1)}</div>
              </div>
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

