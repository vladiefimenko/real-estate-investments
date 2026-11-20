"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, ChevronDown, LayoutGrid, Save, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Switch,
} from "@/components/ui/overlays";
import { Input, Label } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";

export const METRIC_LABELS = {
  active_deals: "Active deals",
  pipeline_volume: "Pipeline volume",
  aum: "AUM (closed)",
  cap_rate: "Wtd. avg cap rate",
  irr_median: "Median levered IRR",
  irr_range: "IRR range",
} as const;
export const SECTION_LABELS = {
  pipeline: "Pipeline by stage",
  exposure: "Exposure by type and state",
  alerts: "Alerts",
  activity: "Recent activity",
  recent_deals: "Recently updated deals",
} as const;
export type MetricKey = keyof typeof METRIC_LABELS;
export type SectionKey = keyof typeof SECTION_LABELS;

export interface Layout {
  filters: { property_type: string | null; status: string | null; mine_only: boolean };
  metrics: MetricKey[];
  sections: SectionKey[];
}

interface SavedView {
  id: string;
  name: string;
  config: Layout;
  is_default: boolean;
}

export const DEFAULT_LAYOUT: Layout = {
  filters: { property_type: null, status: null, mine_only: false },
  metrics: Object.keys(METRIC_LABELS) as MetricKey[],
  sections: Object.keys(SECTION_LABELS) as SectionKey[],
};

/** The active dashboard layout: the chosen saved view (or your default one), plus any unsaved edits. */
export function useDashboardLayout() {
  const org = useOrgKey();
  const views = useQuery({ queryKey: [org, "views", "dashboard"], queryFn: () => api<SavedView[]>("/api/views?page=dashboard") });
  // undefined = nothing picked yet, so use the default view; null = the built-in layout.
  const [chosen, setChosen] = useState<string | null | undefined>(undefined);
  const [draft, setDraft] = useState<Layout | null>(null);
  const list = views.data ?? [];
  const active = chosen === undefined ? list.find((v) => v.is_default) ?? null : chosen === null ? null : list.find((v) => v.id === chosen) ?? null;
  const layout = draft ?? active?.config ?? DEFAULT_LAYOUT;
  return {
    ready: !views.isLoading,
    views: list,
    active,
    layout,
    dirty: draft !== null,
    edit: (next: Partial<Layout>) => setDraft({ ...layout, ...next }),
    choose: (id: string | null) => {
      setChosen(id);
      setDraft(null);
    },
    discard: () => setDraft(null),
  };
}

type Ctl = ReturnType<typeof useDashboardLayout>;

function Reorder<K extends string>({ title, labels, shown, onChange }: { title: string; labels: Record<K, string>; shown: K[]; onChange: (v: K[]) => void }) {
  const all = [...shown, ...(Object.keys(labels) as K[]).filter((k) => !shown.includes(k))];
  const move = (k: K, dir: -1 | 1) => {
    const i = shown.indexOf(k);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= shown.length) return;
    const next = [...shown];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium">{title}</legend>
      <ul className="space-y-1">
        {all.map((k) => {
          const on = shown.includes(k);
          const i = shown.indexOf(k);
          return (
            <li key={k} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm">
              <input
                type="checkbox"
                id={`show-${k}`}
                checked={on}
                onChange={(e) => onChange(e.target.checked ? [...shown, k] : shown.filter((x) => x !== k))}
              />
              <label htmlFor={`show-${k}`} className={on ? "flex-1" : "flex-1 text-muted-foreground"}>
                {labels[k]}
              </label>
              <Button type="button" size="icon-sm" variant="ghost" aria-label={`Move ${labels[k]} up`} disabled={!on || i === 0} onClick={() => move(k, -1)}>
                <ArrowUp />
              </Button>
              <Button type="button" size="icon-sm" variant="ghost" aria-label={`Move ${labels[k]} down`} disabled={!on || i === shown.length - 1} onClick={() => move(k, 1)}>
                <ArrowDown />
              </Button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

/** "Views" menu and "Customize" dialog for the dashboard. */
export function DashboardViewControls({ ctl }: { ctl: Ctl }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [customizing, setCustomizing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: [org, "views", "dashboard"] });

  const create = useMutation({
    mutationFn: () => api<SavedView>("/api/views", { body: { name: name.trim(), config: ctl.layout, is_default: makeDefault } }),
    onSuccess: async (v) => {
      await refresh();
      ctl.choose(v.id);
      setSaving(false);
      toast.success(`Saved view “${v.name}”`);
    },
    onError: (e) => toast.error(e.message),
  });
  const update = useMutation({
    mutationFn: (body: { config?: Layout; is_default?: boolean }) => api<SavedView>(`/api/views/${ctl.active!.id}`, { method: "PATCH", body }),
    onSuccess: async (v, body) => {
      await refresh();
      ctl.choose(v.id);
      toast.success(body.config ? `Updated “${v.name}”` : v.is_default ? `“${v.name}” now opens by default` : `“${v.name}” is no longer your default`);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/views/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      ctl.choose(null);
      await refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  const openSave = () => {
    setName("");
    setMakeDefault(ctl.views.length === 0);
    setSaving(true);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="max-w-56" aria-label="Dashboard views">
            <LayoutGrid />
            <span className="truncate">{ctl.active?.name ?? "Standard view"}</span>
            {ctl.dirty && <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-label="unsaved changes" />}
            <ChevronDown className="opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>Your views</DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => ctl.choose(null)}>
            <span className="flex-1">Standard view</span>
            {!ctl.active && <Check />}
          </DropdownMenuItem>
          {ctl.views.map((v) => (
            <DropdownMenuItem key={v.id} onSelect={() => ctl.choose(v.id)}>
              <span className="flex-1 truncate">{v.name}</span>
              {v.is_default && <Star className="text-accent" aria-label="default" />}
              {ctl.active?.id === v.id && <Check />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCustomizing(true)}>
            <LayoutGrid /> Customize cards &amp; sections…
          </DropdownMenuItem>
          {ctl.active && ctl.dirty && (
            <DropdownMenuItem onSelect={() => update.mutate({ config: ctl.layout })}>
              <Save /> Update “{ctl.active.name}”
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onSelect={openSave}>
            <Save /> Save as new view…
          </DropdownMenuItem>
          {ctl.dirty && <DropdownMenuItem onSelect={ctl.discard}>Discard changes</DropdownMenuItem>}
          {ctl.active && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => update.mutate({ is_default: !ctl.active!.is_default })}>
                <Star /> {ctl.active.is_default ? "Stop opening by default" : "Open this view by default"}
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onSelect={() => confirm(`Delete view “${ctl.active!.name}”?`) && remove.mutate(ctl.active!.id)}>
                <Trash2 /> Delete view
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={customizing} onOpenChange={setCustomizing}>
        <DialogContent
          title="Customize your dashboard"
          description="Tick what to show and use the arrows to set the order. Changes apply right away; save them as a view from the Views menu to keep them."
          className="max-w-2xl"
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Reorder title="Metric cards" labels={METRIC_LABELS} shown={ctl.layout.metrics} onChange={(metrics) => ctl.edit({ metrics })} />
            <Reorder title="Sections" labels={SECTION_LABELS} shown={ctl.layout.sections} onChange={(sections) => ctl.edit({ sections })} />
          </div>
          <div className="mt-4 flex items-center justify-between gap-2">
            <Button variant="ghost" size="sm" onClick={() => ctl.edit({ metrics: DEFAULT_LAYOUT.metrics, sections: DEFAULT_LAYOUT.sections })}>
              Reset to standard
            </Button>
            <Button onClick={() => setCustomizing(false)}>Done</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={saving} onOpenChange={setSaving}>
        <DialogContent title="Save view" description="Saves the current filters, cards and sections. Views are private to you.">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="view-name">Name</Label>
              <Input id="view-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="e.g. My active multifamily pipeline" autoFocus required />
            </div>
            <div className="flex items-center gap-2">
              <Switch id="view-default" checked={makeDefault} onCheckedChange={setMakeDefault} />
              <Label htmlFor="view-default">Open this view when I visit the dashboard</Label>
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={!name.trim()} loading={create.isPending}>
                Save view
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
