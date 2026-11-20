"use client";

import { Check, GraduationCap, Pencil, RotateCcw, Trophy, X } from "lucide-react";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/primitives";
import { type Answer, EXERCISES } from "@/lib/practice";
import { cn } from "@/lib/utils";

const BEST = "axiom.practice.best";
const listeners = new Set<() => void>();
const readBest = () => {
  try {
    return Number(localStorage.getItem(BEST) ?? "0");
  } catch {
    return 0;
  }
};
const saveBest = (n: number) => {
  try {
    if (n > readBest()) localStorage.setItem(BEST, String(n));
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
};

function Excerpt({ text }: { text: string }) {
  const parts = text.split(/\[\[|\]\]/);
  return (
    <p className="rounded-md border bg-muted/40 px-4 py-3 font-mono text-sm leading-relaxed">
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded bg-accent/30 px-0.5 text-foreground">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </p>
  );
}

export default function PracticePage() {
  const best = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    readBest,
    () => 0,
  );
  const [i, setI] = useState(0);
  const [answers, setAnswers] = useState<(Answer | null)[]>(() => EXERCISES.map(() => null));
  const done = i >= EXERCISES.length;
  const score = answers.filter((a, k) => a === EXERCISES[k].answer).length;
  const ex = EXERCISES[Math.min(i, EXERCISES.length - 1)];
  const picked = done ? null : answers[i];
  const restart = () => {
    setAnswers(EXERCISES.map(() => null));
    setI(0);
  };

  return (
    <>
      <PageHeader
        title="Practice verification"
        description="Short, safe exercises on sample documents. Decide whether to accept, edit or reject what the AI read, then see why. Nothing here touches your deals."
      />
      {done ? (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trophy className="size-5 text-accent" /> You scored {score} of {EXERCISES.length}
            </CardTitle>
            <CardDescription>{score === EXERCISES.length ? "Perfect. You're ready to review real documents." : "Here's what to watch for on real documents:"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {score < EXERCISES.length && (
              <ul className="space-y-2 text-sm">
                {EXERCISES.filter((e, k) => answers[k] !== e.answer).map((e) => (
                  <li key={e.id} className="rounded-md border px-3 py-2">
                    <span className="font-medium">{e.lesson}:</span> <span className="text-muted-foreground">{e.explanation}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={restart}>
                <RotateCcw /> Try again
              </Button>
              <Button variant="outline" asChild>
                <Link href="/deals">Go to my deals</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="max-w-2xl">
          <CardHeader>
            <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>
                Exercise {i + 1} of {EXERCISES.length}
              </span>
              {best > 0 && <span>Your best: {best} / {EXERCISES.length}</span>}
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={i} aria-valuemin={0} aria-valuemax={EXERCISES.length} aria-label="Progress">
              <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${(i / EXERCISES.length) * 100}%` }} />
            </div>
            <CardTitle className="mt-3">{ex.field}</CardTitle>
            <CardDescription>
              From the <Badge variant="outline">{ex.doc}</Badge>. The AI read <span className="font-semibold text-foreground">{ex.proposed}</span> from the highlighted text.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Excerpt text={ex.excerpt} />
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {(
                [
                  ["accept", <Check key="a" />, `Accept ${ex.proposed}`],
                  ["edit", <Pencil key="e" />, `Edit to ${ex.editTo}`],
                  ["reject", <X key="r" />, "Reject"],
                ] as const
              ).map(([a, icon, label]) => {
                const chosen = picked === a;
                const right = picked && a === ex.answer;
                return (
                  <Button
                    key={a}
                    variant="outline"
                    disabled={!!picked}
                    onClick={() => setAnswers(answers.map((x, k) => (k === i ? a : x)))}
                    className={cn("h-auto justify-start py-2.5 text-left whitespace-normal disabled:opacity-100", right && "border-success bg-success/10", chosen && !right && "border-destructive bg-destructive/10")}
                  >
                    {icon} {label}
                  </Button>
                );
              })}
            </div>
            {picked && (
              <div role="status" className={cn("rounded-md border px-4 py-3 text-sm", picked === ex.answer ? "border-success/40 bg-success/5" : "border-destructive/40 bg-destructive/5")}>
                <div className="mb-1 font-semibold">
                  {picked === ex.answer ? "Correct" : `Not quite: the right call is ${ex.answer === "edit" ? `edit to ${ex.editTo}` : ex.answer}`} · {ex.lesson}
                </div>
                <p className="text-muted-foreground">{ex.explanation}</p>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <GraduationCap className="size-3.5" /> Score so far: {score}
              </span>
              <Button
                disabled={!picked}
                onClick={() => {
                  if (i === EXERCISES.length - 1) saveBest(answers.filter((a, k) => a === EXERCISES[k].answer).length);
                  setI(i + 1);
                }}
              >
                {i === EXERCISES.length - 1 ? "See my score" : "Next"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </>
  );
}
