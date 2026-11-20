"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
} from "@/components/ui/primitives";
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
  const { data, isLoading, error } = useQuery({
    queryKey: [org, "workflow"],
    queryFn: () => api<Workflow>("/api/org/workflow"),
  });
  const [draft, setDraft] = useState<Record<string, string[]> | null>(null);
  const reqs = draft ?? data?.requirements ?? {};
  const save = useMutation({
    mutationFn: () =>
      api<Workflow>("/api/org/workflow", {
        method: "PUT",
        body: { requirements: reqs },
      }),
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
    setDraft({
      ...reqs,
      [stage]: on ? [...cur, key] : cur.filter((k) => k !== key),
    });
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Workflow</CardTitle>
          <CardDescription>
            Choose what must be done before a deal can move into each stage.
            Deals that aren&apos;t ready are stopped with a list of what&apos;s
            missing; admins can move them anyway, and that override is logged.
            Deals at Investment Committee get a voting panel on their Overview.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {STAGES.map((stage) => {
            const options = Object.entries(data.available).filter(([, v]) =>
              v.stages.includes(stage),
            );
            return (
              <fieldset key={stage} className="rounded-md border p-3">
                <legend className="px-1 text-sm font-medium">
                  Before moving to {STATUS_LABELS[stage]}
                </legend>
                <div className="mt-1 space-y-1.5">
                  {options.map(([key, v]) => (
                    <label
                      key={key}
                      className="flex items-center gap-2 text-sm"
                    >
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
              <Button
                disabled={!draft}
                loading={save.isPending}
                onClick={() => save.mutate()}
              >
                Save requirements
              </Button>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Only owners and admins can change these.
            </p>
          )}
        </CardContent>
      </Card>
      <ApprovalChainCard canEdit={canEdit} />
    </div>
  );
}

interface Member {
  user_id: string;
  name: string;
  email: string;
  role: string;
}
interface Step {
  name: string;
  approvers: string[];
  min_approvals: number;
}

/** Ordered sign-offs a deal needs at Investment Committee before it can be approved. */
function ApprovalChainCard({ canEdit }: { canEdit: boolean }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const chain = useQuery({
    queryKey: [org, "approval-chain"],
    queryFn: () => api<{ steps: Step[] }>("/api/org/workflow/chain"),
  });
  const members = useQuery({
    queryKey: [org, "members"],
    queryFn: () => api<Member[]>("/api/org/members"),
  });
  const [draft, setDraft] = useState<Step[] | null>(null);
  const steps =
    draft ??
    chain.data?.steps.map(({ name, approvers, min_approvals }) => ({
      name,
      approvers,
      min_approvals,
    })) ??
    [];
  const eligible = (members.data ?? []).filter((m) => m.role !== "external");
  const save = useMutation({
    mutationFn: () =>
      api("/api/org/workflow/chain", { method: "PUT", body: { steps } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "approval-chain"] });
      setDraft(null);
      toast.success(
        steps.length
          ? "Approval chain saved. It applies from the next time a deal enters IC."
          : "Approval chain turned off",
      );
    },
    onError: (e) => toast.error(e.message),
  });
  const setStep = (i: number, next: Partial<Step>) =>
    setDraft(steps.map((st, j) => (j === i ? { ...st, ...next } : st)));
  const valid = steps.every(
    (st) =>
      st.name.trim() &&
      st.approvers.length &&
      st.min_approvals >= 1 &&
      st.min_approvals <= st.approvers.length,
  );

  if (chain.isLoading || members.isLoading) return <LoadingBlock rows={2} />;
  if (chain.error) return <ErrorBlock error={chain.error} />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Investment Committee approval chain</CardTitle>
        <CardDescription>
          Optional sign-offs, in order, before a deal can be approved at IC.
          When a deal enters IC, the first step&apos;s approvers are notified;
          each step that approves notifies the next. A decline at any step stops
          the chain. Changes apply to the next IC round, not ones already open.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {steps.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No approval chain: admins record the IC decision directly after
            members vote.
          </p>
        )}
        {steps.map((st, i) => (
          <fieldset key={i} className="space-y-2 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Step {i + 1}</legend>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={st.name}
                onChange={(e) => setStep(i, { name: e.target.value })}
                maxLength={60}
                placeholder="e.g. Asset management review"
                className="max-w-xs"
                aria-label={`Step ${i + 1} name`}
                disabled={!canEdit}
              />
              <span className="text-sm text-muted-foreground">needs</span>
              <Select
                value={String(st.min_approvals)}
                onChange={(e) =>
                  setStep(i, { min_approvals: Number(e.target.value) })
                }
                className="w-20"
                aria-label={`Approvals needed for step ${i + 1}`}
                disabled={!canEdit}
              >
                {Array.from(
                  { length: Math.max(st.approvers.length, 1) },
                  (_, k) => k + 1,
                ).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
              <span className="text-sm text-muted-foreground">
                approval{st.min_approvals === 1 ? "" : "s"} from:
              </span>
              {canEdit && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => setDraft(steps.filter((_, j) => j !== i))}
                >
                  Remove step
                </Button>
              )}
            </div>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {eligible.map((m) => (
                <label
                  key={m.user_id}
                  className="flex items-center gap-2 text-sm"
                >
                  <input
                    type="checkbox"
                    disabled={!canEdit}
                    checked={st.approvers.includes(m.user_id)}
                    onChange={(e) => {
                      const approvers = e.target.checked
                        ? [...st.approvers, m.user_id]
                        : st.approvers.filter((u) => u !== m.user_id);
                      setStep(i, {
                        approvers,
                        min_approvals: Math.min(
                          st.min_approvals,
                          Math.max(approvers.length, 1),
                        ),
                      });
                    }}
                  />
                  {m.name}{" "}
                  <span className="text-xs text-muted-foreground">
                    ({m.role})
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        {canEdit ? (
          <div className="flex flex-wrap justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={steps.length >= 5}
              onClick={() =>
                setDraft([
                  ...steps,
                  { name: "", approvers: [], min_approvals: 1 },
                ])
              }
            >
              Add a step
            </Button>
            <Button
              disabled={!draft || !valid}
              loading={save.isPending}
              onClick={() => save.mutate()}
            >
              Save approval chain
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Only owners and admins can change the approval chain.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
