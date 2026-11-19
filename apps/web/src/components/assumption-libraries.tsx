"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Library, Lock, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Callout } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { Badge, Input, Label } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { pct, TYPE_LABELS } from "@/lib/format";
import type { Scenario } from "@/lib/types";

interface LibraryRec {
  id: string;
  name: string;
  description: string | null;
  property_type: string | null;
  is_shared: boolean;
  values: Record<string, number>;
  mine: boolean;
}

interface FieldDef {
  key: string;
  label: string;
}

const fmt = (key: string, v: number) => (key === "hold_period_years" ? `${v} yrs` : pct(v));

/** Save a scenario's standard assumptions as a named library, or apply one in a single step. */
export function AssumptionLibraries({ scenario, propertyType, dirty }: { scenario: Scenario; propertyType: string; dirty: boolean }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const libs = useQuery({ queryKey: [org, "libraries"], queryFn: () => api<LibraryRec[]>("/api/libraries"), enabled: open });
  const fields = useQuery({ queryKey: ["library-fields"], queryFn: () => api<FieldDef[]>("/api/libraries/fields"), staleTime: Infinity, enabled: open });
  const available = (fields.data ?? []).filter((f) => typeof (scenario.assumptions as unknown as Record<string, unknown>)[f.key] === "number");
  const [name, setName] = useState("");
  const [shared, setShared] = useState(true);
  const [keys, setKeys] = useState<string[] | null>(null); // null = default selection
  const chosen = keys ?? available.map((f) => f.key).filter((k) => k !== "hold_period_years");
  const labelOf = (k: string) => fields.data?.find((f) => f.key === k)?.label ?? k;

  const apply = useMutation({
    mutationFn: (lib: LibraryRec) => api<{ changed: string[] }>(`/api/scenarios/${scenario.id}/apply-library`, { body: { library_id: lib.id } }),
    onSuccess: (r, lib) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success(r.changed.length ? `Applied "${lib.name}": ${r.changed.length} assumption(s) changed and recalculated` : `"${lib.name}" already matches this scenario`);
      setOpen(false);
    },
    onError: (e) => toast.error(e.message),
  });
  const save = useMutation({
    mutationFn: () => api<LibraryRec>("/api/libraries/from-scenario", { body: { scenario_id: scenario.id, name: name.trim(), keys: chosen, is_shared: shared } }),
    onSuccess: (lib) => {
      qc.invalidateQueries({ queryKey: [org, "libraries"] });
      toast.success(`Saved library "${lib.name}"`);
      setName("");
      setKeys(null);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (lib: LibraryRec) => api(`/api/libraries/${lib.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "libraries"] }),
    onError: (e) => toast.error(e.message),
  });

  const list = [...(libs.data ?? [])].sort((a, b) => Number(b.property_type === propertyType) - Number(a.property_type === propertyType));

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Library /> Libraries
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Assumption libraries"
          description="Your standard assumptions, saved once and applied to any deal. Applying overwrites only the values in the library, then recalculates."
          className="max-w-2xl"
        >
          <Tabs defaultValue="apply">
            <TabsList>
              <TabsTrigger value="apply">Apply a library</TabsTrigger>
              <TabsTrigger value="save">Save from “{scenario.name}”</TabsTrigger>
            </TabsList>

            <TabsContent value="apply" className="mt-4 space-y-3">
              {dirty && <Callout tone="warn">You have unsaved changes. Save or discard them before applying a library.</Callout>}
              {libs.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
              {libs.data?.length === 0 && (
                <p className="text-sm text-muted-foreground">No libraries yet. Use the “Save from” tab to turn this scenario&apos;s assumptions into your first one.</p>
              )}
              {list.map((lib) => (
                <div key={lib.id} className="rounded-md border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5 font-medium">
                        {lib.name}
                        {lib.property_type && <Badge variant="outline">{TYPE_LABELS[lib.property_type] ?? lib.property_type}</Badge>}
                        <Badge variant="outline" className="gap-1">
                          {lib.is_shared ? <Users className="size-3" /> : <Lock className="size-3" />}
                          {lib.is_shared ? "Team" : "Private"}
                        </Badge>
                      </div>
                      {lib.description && <p className="mt-0.5 text-xs text-muted-foreground">{lib.description}</p>}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {lib.mine && (
                        <Button size="icon-sm" variant="ghost" aria-label={`Delete ${lib.name}`} onClick={() => confirm(`Delete library "${lib.name}"?`) && remove.mutate(lib)}>
                          <Trash2 />
                        </Button>
                      )}
                      <Button size="sm" disabled={dirty} loading={apply.isPending && apply.variables?.id === lib.id} onClick={() => apply.mutate(lib)}>
                        Apply
                      </Button>
                    </div>
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-1.5 text-xs">
                    {Object.entries(lib.values).map(([k, v]) => {
                      const current = (scenario.assumptions as unknown as Record<string, number>)[k];
                      const differs = current !== v;
                      return (
                        <li key={k} className={differs ? "rounded bg-accent/10 px-1.5 py-0.5" : "rounded bg-muted px-1.5 py-0.5 text-muted-foreground"}>
                          {labelOf(k)} {fmt(k, v)}
                          {differs && typeof current === "number" && <span className="text-muted-foreground"> (now {fmt(k, current)})</span>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </TabsContent>

            <TabsContent value="save" className="mt-4">
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (name.trim() && chosen.length) save.mutate();
                }}
              >
                {dirty && <p className="text-xs text-warning">Unsaved changes aren&apos;t included: the library uses the scenario&apos;s saved values.</p>}
                <div className="space-y-1.5">
                  <Label htmlFor="lib-name">Library name</Label>
                  <Input id="lib-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="e.g. My multifamily standards" required />
                </div>
                <fieldset>
                  <legend className="mb-1.5 text-sm font-medium">Values to include</legend>
                  <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                    {available.map((f) => (
                      <label key={f.key} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs">
                        <input
                          type="checkbox"
                          checked={chosen.includes(f.key)}
                          onChange={(e) => setKeys(e.target.checked ? [...chosen, f.key] : chosen.filter((k) => k !== f.key))}
                        />
                        <span className="flex-1">{f.label}</span>
                        <span className="tabular text-muted-foreground">{fmt(f.key, (scenario.assumptions as unknown as Record<string, number>)[f.key])}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="flex items-center gap-2">
                  <Switch id="lib-shared" checked={shared} onCheckedChange={setShared} />
                  <Label htmlFor="lib-shared">Share with my team (otherwise private to me)</Label>
                </div>
                <div className="flex justify-end">
                  <Button type="submit" disabled={!name.trim() || !chosen.length} loading={save.isPending}>
                    Save library ({chosen.length} values)
                  </Button>
                </div>
              </form>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  );
}
