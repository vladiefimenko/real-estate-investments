"use client";

import { GraduationCap, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";

const KEY = "axiom.tour.verify.v1";
const listeners = new Set<() => void>();
const readSeen = () => {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return true; // storage blocked: don't nag
  }
};
const markSeen = () => {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
};

const STEPS: { target?: string; title: string; body: string }[] = [
  {
    title: "AI proposes, you verify",
    body: "Axiom reads the document and proposes values, but none of them reach your model until a person checks them. This takes about a minute to learn.",
  },
  {
    target: "field",
    title: "1. A proposed value",
    body: "Each card is one value Axiom found, with how confident it is. Click a card to jump to where it came from.",
  },
  {
    target: "source",
    title: "2. Check the source",
    body: "The highlighted text (or cells, for spreadsheets) is exactly where the value came from. A green shield means the excerpt was found word for word; an orange one means check it yourself.",
  },
  {
    target: "actions",
    title: "3. Decide",
    body: "Accept if it matches the source. Edit if it's close but wrong (a monthly figure shown as annual, for example). Reject if it's the wrong number altogether.",
  },
  {
    target: "bulk",
    title: "4. Speed it up",
    body: "Accept verified accepts every pending value whose source was confirmed and whose confidence is above the threshold you pick. You can still undo any of them.",
  },
  {
    title: "Why it matters",
    body: "Every decision is saved with your name and time in the deal's Activity, and the IC memo lists each verified value with its source. Only accepted or edited values are used when you apply the data to the base case.",
  },
];

/** First-visit walkthrough of the document review screen. */
export function VerificationTour({ ready, onStart }: { ready: boolean; onStart: () => void }) {
  const seen = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    readSeen,
    () => true,
  );
  const [manual, setManual] = useState(false);
  const [step, setStep] = useState(0);
  const open = ready && (manual || !seen);
  const s = STEPS[step];

  useEffect(() => {
    if (!open || !s.target) return;
    const el = document.querySelector<HTMLElement>(`[data-tour="${s.target}"]`);
    if (!el) return;
    el.classList.add("tour-highlight");
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    return () => el.classList.remove("tour-highlight");
  }, [open, s.target]);

  const close = () => {
    markSeen();
    setManual(false);
    setStep(0);
  };

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          setStep(0);
          setManual(true);
          onStart();
        }}
      >
        <GraduationCap /> Tutorial
      </Button>
      {open && (
        <div role="dialog" aria-label="Verification tutorial" className="fixed bottom-4 right-4 z-50 w-[min(380px,calc(100vw-2rem))] rounded-lg border bg-card p-4 shadow-2xl">
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Tutorial · {step + 1} of {STEPS.length}
            </div>
            <Button size="icon-sm" variant="ghost" aria-label="Close tutorial" onClick={close}>
              <X />
            </Button>
          </div>
          <h3 className="mt-1 font-semibold">{s.title}</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">{s.body}</p>
          {step === STEPS.length - 1 && (
            <p className="mt-2 text-sm">
              Want to try it safely first?{" "}
              <Link href="/practice" className="font-medium underline underline-offset-4" onClick={markSeen}>
                Practice verification
              </Link>
            </p>
          )}
          <div className="mt-3 flex items-center justify-between">
            <Button size="sm" variant="ghost" onClick={close}>
              Skip
            </Button>
            <div className="flex gap-2">
              {step > 0 && (
                <Button size="sm" variant="outline" onClick={() => setStep(step - 1)}>
                  Back
                </Button>
              )}
              <Button
                size="sm"
                onClick={() => {
                  if (step === 0) onStart();
                  if (step < STEPS.length - 1) setStep(step + 1);
                  else close();
                }}
              >
                {step < STEPS.length - 1 ? "Next" : "Got it"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
