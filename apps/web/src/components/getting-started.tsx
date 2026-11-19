"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Check, X } from "lucide-react";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type StepKey = "deal_created" | "document_uploaded" | "field_verified" | "scenario_explored" | "report_generated";

interface Onboarding {
  steps: Record<StepKey, boolean>;
  completed: number;
  total: number;
}

const STEPS: { key: StepKey; title: string; how: string; href: string; cta: string }[] = [
  {
    key: "deal_created",
    title: "Create your first deal",
    how: "Click New deal and enter the property basics. You can explore the [DEMO] deals first; they don't count here.",
    href: "/deals?new=1",
    cta: "New deal",
  },
  {
    key: "document_uploaded",
    title: "Upload an OM, T12 or rent roll",
    how: "Open a deal, go to the Documents tab and drop in a PDF or Excel file. Axiom reads it and proposes values.",
    href: "/deals",
    cta: "Open deals",
  },
  {
    key: "field_verified",
    title: "Verify an extracted value",
    how: "On Documents, click Review next to a file. Check each value against its source, then accept, edit or reject it.",
    href: "/deals",
    cta: "Open deals",
  },
  {
    key: "scenario_explored",
    title: "Change an assumption or run a scenario",
    how: "Apply verified data, edit an assumption on Underwriting, or add a scenario on Scenarios & Risk and compare the returns.",
    href: "/deals",
    cta: "Open deals",
  },
  {
    key: "report_generated",
    title: "Export a report",
    how: "On a deal's Reports tab, download the Excel model, the one-pager or the IC memo.",
    href: "/deals",
    cta: "Open deals",
  },
];

function subscribeStorage(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function readDismissed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

/** Dismissible Getting Started checklist; progress comes from what the workspace has actually done. */
export function GettingStarted() {
  const org = useOrgKey();
  const storageKey = `axiom.gettingStarted.dismissed.${org}`;
  // Server render assumes dismissed, so the card never flashes for people who hid it.
  const storedDismissed = useSyncExternalStore(subscribeStorage, () => readDismissed(storageKey), () => true);
  const [hiddenNow, setHiddenNow] = useState(false);
  const dismissed = storedDismissed || hiddenNow;
  const { data } = useQuery({
    queryKey: [org, "onboarding"],
    queryFn: () => api<Onboarding>("/api/org/onboarding"),
  });

  const dismiss = () => {
    setHiddenNow(true);
    try {
      window.localStorage.setItem(storageKey, "1");
    } catch {
      /* storage unavailable: hide for this visit only */
    }
  };

  if (dismissed || !data) return null;
  const done = data.completed === data.total;
  const next = STEPS.find((s) => !data.steps[s.key]);

  return (
    <Card className="mb-6 px-5 py-4" aria-labelledby="getting-started-title">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="getting-started-title" className="font-semibold">
            {done ? "You've completed Getting Started" : "Getting started"}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {done
              ? "You've used every core step of the workflow. Hide this card whenever you like."
              : `${data.completed} of ${data.total} done. Each step ticks itself off when you do it.`}
          </p>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={dismiss} aria-label="Hide Getting Started">
          <X />
        </Button>
      </div>
      <div
        className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={data.total}
        aria-valuenow={data.completed}
        aria-label="Getting Started progress"
      >
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${(data.completed / data.total) * 100}%` }} />
      </div>
      <ol className="mt-4 space-y-2.5">
        {STEPS.map((s) => {
          const complete = data.steps[s.key];
          const isNext = s === next;
          return (
            <li key={s.key} className="flex items-start gap-3">
              <span
                className={cn(
                  "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-[11px]",
                  complete ? "border-success bg-success text-white" : isNext ? "border-accent text-accent" : "text-muted-foreground",
                )}
                aria-hidden
              >
                {complete ? <Check className="size-3" /> : STEPS.indexOf(s) + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className={cn("text-sm font-medium", complete && "text-muted-foreground line-through")}>
                  {s.title}
                  <span className="sr-only">{complete ? " (done)" : " (not done yet)"}</span>
                </div>
                {isNext && <p className="mt-0.5 text-xs text-muted-foreground">{s.how}</p>}
              </div>
              {isNext && (
                <Button size="sm" variant="outline" asChild>
                  <Link href={s.href}>{s.cta}</Link>
                </Button>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-4 flex items-center gap-1.5 border-t pt-3 text-xs text-muted-foreground">
        <BookOpen className="size-3.5" />
        <span>
          New to the numbers? Hover any ⓘ icon for a quick definition, or browse the{" "}
          <Link href="/glossary" className="text-accent underline-offset-2 hover:underline">
            glossary
          </Link>
          .
        </span>
      </p>
    </Card>
  );
}
