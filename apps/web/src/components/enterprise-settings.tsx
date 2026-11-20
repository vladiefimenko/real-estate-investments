"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, KeyRound, Plus, ShieldCheck, Webhook } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Callout, EmptyState, ErrorBlock, LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLong, dateTime, relativeTime } from "@/lib/format";

// ------------------------------------------------------------------ usage
interface Usage {
  days: number;
  members: number;
  active_users: number;
  deals: { active: number; created: number };
  documents: { stored: number; storage_bytes: number; uploaded: number };
  reports: Record<string, number>;
  values_reviewed: number;
  analyst_questions: number;
  scenario_changes: number;
  api_keys: { active: number; used_in_period: number };
  events_total: number;
  events_per_day: { date: string; events: number }[];
}

const REPORT_LABELS: Record<string, string> = {
  excel: "Excel models",
  one_pager: "One-pagers",
  ic_memo: "IC memos",
  junior_pack: "Junior packs",
  presentation: "Presentations",
  summary_pack: "Summary packs (per deal)",
};

const bytes = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`);

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-md border px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function UsageTab() {
  const org = useOrgKey();
  const { hasRole, org: membership } = useAuth();
  const allowed = hasRole("admin") || membership?.role === "auditor";
  const [days, setDays] = useState(30);
  const { data, isLoading, error } = useQuery({
    queryKey: [org, "usage", days],
    queryFn: () => api<Usage>(`/api/org/usage?days=${days}`),
    enabled: allowed,
  });
  if (!allowed) return <Callout>Only owners, admins and auditors can see workspace usage.</Callout>;
  if (isLoading) return <LoadingBlock rows={4} />;
  if (error) return <ErrorBlock error={error} />;
  if (!data) return null;
  const peak = Math.max(1, ...data.events_per_day.map((d) => d.events));
  const reports = Object.entries(data.reports);
  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <CardTitle>Usage</CardTitle>
          <CardDescription>Who is using the workspace and how, for licensing and ROI. Counts come from the audit log.</CardDescription>
        </div>
        <Select value={String(days)} onChange={(e) => setDays(Number(e.target.value))} className="w-40" aria-label="Period">
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="90">Last 90 days</option>
          <option value="365">Last 12 months</option>
        </Select>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Active users" value={data.active_users} sub={`of ${data.members} member${data.members === 1 ? "" : "s"}`} />
          <Stat label="Deals" value={data.deals.active} sub={`${data.deals.created} created in period`} />
          <Stat label="Documents" value={data.documents.stored} sub={`${bytes(data.documents.storage_bytes)} · ${data.documents.uploaded} uploaded`} />
          <Stat label="Values reviewed" value={data.values_reviewed} />
          <Stat label="Analyst questions" value={data.analyst_questions} />
          <Stat label="Scenario changes" value={data.scenario_changes} />
          <Stat label="Reports exported" value={reports.reduce((a, [, n]) => a + n, 0)} />
          <Stat label="API keys" value={data.api_keys.active} sub={`${data.api_keys.used_in_period} used in period`} />
        </div>
        <div>
          <div className="mb-2 flex items-baseline justify-between text-sm">
            <span className="font-medium">Activity per day</span>
            <span className="text-xs text-muted-foreground">{data.events_total} events</span>
          </div>
          <div className="flex h-24 items-end gap-px" role="img" aria-label={`Daily activity over ${data.days} days, peak ${peak} events`}>
            {data.events_per_day.map((d) => (
              <div
                key={d.date}
                title={`${d.date}: ${d.events} events`}
                className="flex-1 rounded-t-sm bg-accent/70"
                style={{ height: `${Math.max(d.events ? 4 : 1, (d.events / peak) * 100)}%`, opacity: d.events ? 1 : 0.25 }}
              />
            ))}
          </div>
        </div>
        {reports.length > 0 && (
          <div>
            <div className="mb-2 text-sm font-medium">Reports by type</div>
            <ul className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
              {reports.map(([k, n]) => (
                <li key={k} className="flex justify-between rounded-md border px-3 py-1.5">
                  <span className="text-muted-foreground">{REPORT_LABELS[k] ?? k}</span>
                  <span className="font-medium tabular">{n}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ API keys
interface ApiKeyRow {
  id: string;
  name: string;
  prefix: string;
  created_by: string | null;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
}

export function ApiKeysTab() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiry, setExpiry] = useState("365");
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: [org, "api-keys"],
    queryFn: () => api<{ keys: ApiKeyRow[]; scope: { access: string; paths: string[]; rate_limit: string } }>("/api/org/api-keys"),
    enabled: hasRole("admin"),
  });
  const create = useMutation({
    mutationFn: () =>
      api<ApiKeyRow & { key: string }>("/api/org/api-keys", {
        body: { name: name.trim(), ...(expiry ? { expires_in_days: Number(expiry) } : {}) },
      }),
    onSuccess: (k) => {
      qc.invalidateQueries({ queryKey: [org, "api-keys"] });
      setCreated(k.key);
      setName("");
    },
    onError: (e) => toast.error(e.message),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/api/org/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "api-keys"] });
      toast.success("API key revoked");
    },
    onError: (e) => toast.error(e.message),
  });

  if (!hasRole("admin")) return <Callout>Only owners and admins can manage API keys.</Callout>;
  if (isLoading) return <LoadingBlock rows={3} />;
  if (error) return <ErrorBlock error={error} />;

  const close = (o: boolean) => {
    setOpen(o);
    if (!o) {
      setCreated(null);
      setCopied(false);
    }
  };

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <CardTitle>API keys</CardTitle>
          <CardDescription>Let other systems, such as a data warehouse or CRM, read this workspace&apos;s deals.</CardDescription>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus /> New API key
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {data && (
          <Callout title="What a key can do">
            <span className="flex items-start gap-1.5">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" />
              <span>
                Read-only access to deals, scenarios, the dashboard and comparisons ({data.scope.rate_limit}). Keys can&apos;t change anything, see
                members, settings or the audit log, and stop working if revoked, expired, or if the person who created them leaves the workspace.
                Send it as <code className="rounded bg-muted px-1">Authorization: Bearer &lt;key&gt;</code>.
              </span>
            </span>
          </Callout>
        )}
        {data?.keys.length === 0 ? (
          <EmptyState icon={KeyRound} title="No API keys yet" description="Create one when a system needs to read your deal data." />
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Name</TH>
                <TH>Key</TH>
                <TH>Created</TH>
                <TH>Last used</TH>
                <TH>Expires</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {data?.keys.map((k) => (
                <TR key={k.id}>
                  <TD className="font-medium">{k.name}</TD>
                  <TD>
                    <code className="text-xs">{k.prefix}…</code>
                  </TD>
                  <TD className="text-xs text-muted-foreground">
                    {dateTime(k.created_at)}
                    {k.created_by ? ` · ${k.created_by}` : ""}
                  </TD>
                  <TD className="text-xs text-muted-foreground">{k.last_used_at ? relativeTime(k.last_used_at) : "Never"}</TD>
                  <TD className="text-xs text-muted-foreground">{k.expires_at ? dateLong(k.expires_at) : "Never"}</TD>
                  <TD className="text-right">
                    {k.revoked ? (
                      <Badge variant="outline">Revoked</Badge>
                    ) : (
                      <Button size="sm" variant="ghost" className="text-destructive" onClick={() => confirm(`Revoke "${k.name}"? Systems using it will stop working.`) && revoke.mutate(k.id)}>
                        Revoke
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={close}>
        <DialogContent title={created ? "Copy your API key" : "New API key"} description={created ? "This is the only time the full key is shown. Store it somewhere safe, like a password manager." : "Read-only access to this workspace's deal data."}>
          {created ? (
            <div className="space-y-3">
              <div className="flex gap-2">
                <Input readOnly value={created} className="font-mono text-xs" aria-label="New API key" onFocus={(e) => e.target.select()} />
                <Button
                  variant="outline"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(created);
                      setCopied(true);
                    } catch {
                      toast.error("Couldn't copy: select the key and copy it manually");
                    }
                  }}
                >
                  {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <div className="flex justify-end">
                <Button onClick={() => close(false)}>Done</Button>
              </div>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (name.trim()) create.mutate();
              }}
            >
              <div className="space-y-1.5">
                <Label htmlFor="key-name">Name</Label>
                <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="e.g. Data warehouse sync" required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="key-expiry">Expires</Label>
                <Select id="key-expiry" value={expiry} onChange={(e) => setExpiry(e.target.value)}>
                  <option value="30">In 30 days</option>
                  <option value="90">In 90 days</option>
                  <option value="365">In 1 year</option>
                  <option value="">Never</option>
                </Select>
              </div>
              <div className="flex justify-end">
                <Button type="submit" disabled={!name.trim()} loading={create.isPending}>
                  Create key
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ------------------------------------------------------------------ audit export
export function AuditExport() {
  const { hasRole, org } = useAuth();
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState<"csv" | "json" | null>(null);
  if (!hasRole("admin") && org?.role !== "auditor") return null;
  const run = async (format: "csv" | "json") => {
    setBusy(format);
    try {
      const p = new URLSearchParams({ format });
      if (since) p.set("since", since);
      if (until) p.set("until", until);
      await download(`/api/org/audit/export?${p}`, `audit.${format}`);
      toast.success("Audit log exported. The export itself is recorded in the log.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border bg-muted/30 p-3">
      <div className="mr-auto">
        <div className="text-sm font-medium">Export for compliance</div>
        <p className="text-xs text-muted-foreground">The full history (not just the latest 200), with user emails and a SHA-256 checksum.</p>
      </div>
      <div className="space-y-1">
        <Label htmlFor="ax-from" className="text-xs">
          From
        </Label>
        <Input id="ax-from" type="date" value={since} onChange={(e) => setSince(e.target.value)} className="h-8 w-36" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="ax-to" className="text-xs">
          To
        </Label>
        <Input id="ax-to" type="date" value={until} onChange={(e) => setUntil(e.target.value)} className="h-8 w-36" />
      </div>
      <Button size="sm" variant="outline" loading={busy === "csv"} onClick={() => run("csv")}>
        <Download /> CSV
      </Button>
      <Button size="sm" variant="outline" loading={busy === "json"} onClick={() => run("json")}>
        <Download /> JSON
      </Button>
    </div>
  );
}

// ------------------------------------------------------------------ webhooks
interface WebhookRow {
  id: string;
  url: string;
  description: string | null;
  events: string[];
  active: boolean;
  last_delivery_at: string | null;
  last_status: string | null;
  consecutive_failures: number;
}

export function WebhooksTab() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [events, setEvents] = useState<string[]>(["deal.stage_changed"]);
  const [secret, setSecret] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: [org, "webhooks"],
    queryFn: () => api<{ webhooks: WebhookRow[]; events: Record<string, string>; signature: string }>("/api/org/webhooks"),
    enabled: hasRole("admin"),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: [org, "webhooks"] });
  const create = useMutation({
    mutationFn: () => api<WebhookRow & { secret: string }>("/api/org/webhooks", { body: { url: url.trim(), description: description.trim() || null, events } }),
    onSuccess: (h) => {
      refresh();
      setSecret(h.secret);
      setUrl("");
      setDescription("");
    },
    onError: (e) => toast.error(e.message),
  });
  const update = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => api(`/api/org/webhooks/${id}`, { method: "PATCH", body: { active } }),
    onSuccess: refresh,
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/org/webhooks/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      toast.success("Webhook deleted");
    },
    onError: (e) => toast.error(e.message),
  });
  const test = useMutation({
    mutationFn: (id: string) => api<{ ok: boolean; status: string }>(`/api/org/webhooks/${id}/test`, { method: "POST" }),
    onSuccess: (r) => {
      refresh();
      if (r.ok) toast.success(`Test delivered (${r.status})`);
      else toast.error(`Test failed: ${r.status}`);
    },
    onError: (e) => toast.error(e.message),
  });

  if (!hasRole("admin")) return <Callout>Only owners and admins can manage webhooks.</Callout>;
  if (isLoading) return <LoadingBlock rows={3} />;
  if (error) return <ErrorBlock error={error} />;
  const close = (o: boolean) => {
    setOpen(o);
    if (!o) setSecret(null);
  };

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <CardTitle>Webhooks</CardTitle>
          <CardDescription>Notify another system, such as a CRM, Slack workflow or data pipeline, when something happens here.</CardDescription>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus /> New webhook
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {data && (
          <Callout title="How deliveries work">
            Axiom sends a JSON <code className="rounded bg-muted px-1">POST</code> to your https:// address after the change is saved. Verify each
            request with your webhook secret: <code className="rounded bg-muted px-1 text-[11px]">{data.signature}</code>. Only public https addresses
            are allowed, and a webhook switches itself off after 10 failed deliveries in a row.
          </Callout>
        )}
        {data?.webhooks.length === 0 ? (
          <EmptyState icon={Webhook} title="No webhooks yet" description="Add one to push deal stage changes or new reports to another system." />
        ) : (
          <ul className="space-y-3">
            {data?.webhooks.map((h) => (
              <li key={h.id} className="rounded-md border p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="truncate text-sm">{h.url}</code>
                      <Badge variant={h.active ? "success" : "outline"}>{h.active ? "Active" : "Off"}</Badge>
                    </div>
                    {h.description && <p className="mt-0.5 text-xs text-muted-foreground">{h.description}</p>}
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {h.events.map((e) => (
                        <Badge key={e} variant="outline">
                          {e}
                        </Badge>
                      ))}
                    </div>
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      {h.last_delivery_at ? `Last delivery ${relativeTime(h.last_delivery_at)}: ${h.last_status}` : "No deliveries yet"}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <Button size="sm" variant="outline" loading={test.isPending && test.variables === h.id} onClick={() => test.mutate(h.id)}>
                      Send test
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => update.mutate({ id: h.id, active: !h.active })}>
                      {h.active ? "Turn off" : "Turn on"}
                    </Button>
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => confirm(`Delete the webhook to ${h.url}?`) && remove.mutate(h.id)}>
                      Delete
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={close}>
        <DialogContent title={secret ? "Save your webhook secret" : "New webhook"} description={secret ? "Use this secret to verify that requests come from Axiom. It's only shown once." : "Axiom will POST signed JSON to this address."} className="max-w-lg">
          {secret ? (
            <div className="space-y-3">
              <Input readOnly value={secret} className="font-mono text-xs" aria-label="Webhook secret" onFocus={(e) => e.target.select()} />
              <div className="flex justify-end">
                <Button onClick={() => close(false)}>Done</Button>
              </div>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (url.trim() && events.length) create.mutate();
              }}
            >
              <div className="space-y-1.5">
                <Label htmlFor="wh-url">Endpoint URL</Label>
                <Input id="wh-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/axiom-webhook" required maxLength={500} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="wh-desc">Description (optional)</Label>
                <Input id="wh-desc" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} placeholder="e.g. CRM pipeline sync" />
              </div>
              <fieldset>
                <legend className="mb-1.5 text-sm font-medium">Events</legend>
                <div className="space-y-1.5">
                  {Object.entries(data?.events ?? {}).map(([key, label]) => (
                    <label key={key} className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={events.includes(key)}
                        onChange={(e) => setEvents(e.target.checked ? [...events, key] : events.filter((x) => x !== key))}
                      />
                      <span>
                        <code className="text-xs">{key}</code>
                        <span className="block text-xs text-muted-foreground">{label}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="flex justify-end">
                <Button type="submit" disabled={!url.trim() || !events.length} loading={create.isPending}>
                  Add webhook
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
