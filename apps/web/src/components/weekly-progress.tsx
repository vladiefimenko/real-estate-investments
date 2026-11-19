"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Building2, CheckCheck, FileText, FileUp, Layers } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";

type Key = "deals_created" | "documents_uploaded" | "fields_verified" | "scenarios_explored" | "reports_generated" | "analyst_questions";

const ITEMS: { key: Key; label: string; icon: LucideIcon }[] = [
  { key: "deals_created", label: "Deals created", icon: Building2 },
  { key: "documents_uploaded", label: "Documents uploaded", icon: FileUp },
  { key: "fields_verified", label: "Values reviewed", icon: CheckCheck },
  { key: "scenarios_explored", label: "Scenario changes", icon: Layers },
  { key: "reports_generated", label: "Reports exported", icon: FileText },
  { key: "analyst_questions", label: "Analyst questions", icon: Bot },
];

/** The signed-in user's own activity over the last 7 days. */
export function WeeklyProgress() {
  const org = useOrgKey();
  const { data } = useQuery({
    queryKey: [org, "progress", 7],
    queryFn: () => api<{ days: number; counts: Record<Key, number> }>("/api/org/progress?days=7"),
  });
  if (!data) return null;
  const total = Object.values(data.counts).reduce((a, b) => a + b, 0);
  return (
    <Card className="mb-6 px-5 py-4" aria-labelledby="weekly-progress-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="weekly-progress-title" className="font-semibold">
          Your progress this week
        </h2>
        <p className="text-xs text-muted-foreground">
          {total === 0 ? "Nothing yet in the last 7 days. Demo deals don't count." : "Your own actions in the last 7 days."}
        </p>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {ITEMS.map(({ key, label, icon: Icon }) => (
          <div key={key} className="flex items-center gap-2.5 rounded-md border px-3 py-2">
            <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div>
              <dd className="text-lg font-semibold leading-none tabular">{data.counts[key]}</dd>
              <dt className="mt-1 text-[11px] text-muted-foreground">{label}</dt>
            </div>
          </div>
        ))}
      </dl>
    </Card>
  );
}
