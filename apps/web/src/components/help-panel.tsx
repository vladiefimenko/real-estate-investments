"use client";

import { BookOpen, CircleHelp } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { GLOSSARY_BY_ID } from "@/lib/glossary";
import { helpFor } from "@/lib/help";

/** "?" button in the top bar: a short guide to the current page and the terms used on it. */
export function HelpPanel() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const topic = helpFor(pathname);
  if (!topic) return null;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="ghost" size="icon-sm" aria-label="Help for this page" title="Help for this page" onClick={() => setOpen(true)}>
        <CircleHelp />
      </Button>
      <DialogContent
        title={topic.title}
        description={topic.summary}
        className="left-auto right-0 top-0 h-full max-h-none w-full max-w-md translate-x-0 translate-y-0 content-start rounded-none border-y-0 border-r-0"
      >
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">How to use this page</h3>
          <ol className="list-decimal space-y-1.5 pl-5 text-sm">
            {topic.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </section>
        {topic.terms && topic.terms.length > 0 && (
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Terms on this page</h3>
            <ul className="space-y-2">
              {topic.terms.map((id) => {
                const e = GLOSSARY_BY_ID[id];
                if (!e) return null;
                return (
                  <li key={id} className="text-sm">
                    <Link href={`/glossary#${id}`} onClick={() => setOpen(false)} className="font-medium text-accent underline-offset-2 hover:underline">
                      {e.term}
                    </Link>
                    <p className="text-muted-foreground">{e.definition}</p>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <Link
          href="/glossary"
          onClick={() => setOpen(false)}
          className="flex items-center gap-1.5 border-t pt-3 text-sm text-muted-foreground hover:text-foreground"
        >
          <BookOpen className="size-4" /> Open the full glossary
        </Link>
      </DialogContent>
    </Dialog>
  );
}
