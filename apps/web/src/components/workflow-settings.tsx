"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { STATUS_LABELS } from "@/lib/format";

interface Workflow {
  requirements: Record<string, string[]>;
  available: Record<string, { label: string; stages: string[] }>;
}

const STAGES = ["underwriting", "ic", "closed"];

/** Admins choose what must be done before a deal can enter each stage. */
export function WorkflowTab() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin");
  const { data, isLoading, error } = useQuery({ queryKey: [org, "workflow"], queryFn: () => api<Workflow>("/api/org/workflow") });
  const [draft, setDraft] = useState<Record<string, string[]> | null>(null);
  const reqs = draft ?? data?.requirements ?? {};
  const save = useMutation({
    mutationFn: () => api<Workflow>("/api/org/workflow", { method: "PUT", body: { requirements: reqs } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "workflow"] });
      setDraft(null);
      toast.success("Stage requirements saved");
    },
    onError: (e) => toast.error(e.message),
  });
  if (isLoading) return <LoadingBlock rows={3} />;
  if (error) return <ErrorBlock error={error} />;
  if (!data) return null;
  const toggle = (stage: string, key: string, on: boolean) => {
    const cur = reqs[stage] ?? [];
    setDraft({ ...reqs, [stage]: on ? [...cur, key] : cur.filter((k) => k !== key) });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Workflow</CardTitle>
        <CardDescription>
          Choose what must be done before a deal can move into each stage. Deals that aren&apos;t ready are stopped with a list of what&apos;s
          missing; admins can move them anyway, and that override is logged. Deals at Investment Committee get a voting panel on their Overview.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {STAGES.map((stage) => {
          const options = Object.entries(data.available).filter(([, v]) => v.stages.includes(stage));
          return (
            <fieldset key={stage} className="rounded-md border p-3">
              <legend className="px-1 text-sm font-medium">Before moving to {STATUS_LABELS[stage]}</legend>
              <div className="mt-1 space-y-1.5">
                {options.map(([key, v]) => (
                  <label key={key} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      disabled={!canEdit}
                      checked={(reqs[stage] ?? []).includes(key)}
                      onChange={(e) => toggle(stage, key, e.target.checked)}
                    />
                    {v.label}
                  </label>
                ))}
              </div>
            </fieldset>
          );
        })}
        {canEdit ? (
          <div className="flex justify-end">
            <Button disabled={!draft} loading={save.isPending} onClick={() => save.mutate()}>
              Save requirements
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Only owners and admins can change these.</p>
        )}
      </CardContent>
    </Card>
  );
}
