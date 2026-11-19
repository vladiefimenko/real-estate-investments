"use client";

import { Search } from "lucide-react";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { EmptyState, PageHeader } from "@/components/common";
import { Card, Input } from "@/components/ui/primitives";
import { GLOSSARY_CATEGORIES, searchGlossary } from "@/lib/glossary";
import { cn } from "@/lib/utils";

function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export default function GlossaryPage() {
  const [query, setQuery] = useState("");
  // Arriving from a metric's info icon (/glossary#dscr) highlights and scrolls to that term.
  const target = useSyncExternalStore(subscribeHash, () => decodeURIComponent(window.location.hash.slice(1)), () => "");
  const results = useMemo(() => searchGlossary(query), [query]);

  useEffect(() => {
    if (target) requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView({ block: "center" }));
  }, [target]);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Glossary"
        description="Plain-English definitions of the numbers you see in Axiom. Ranges are rules of thumb for orientation; markets differ, and the engine never uses them."
      />
      <div className="relative mb-6">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search terms, e.g. DSCR, cap rate, T12…"
          aria-label="Search the glossary"
          className="pl-9"
        />
      </div>
      {results.length === 0 && <EmptyState icon={Search} title="No matching terms" description="Try a shorter word or an abbreviation like NOI or LTV." />}
      <div className="space-y-8">
        {GLOSSARY_CATEGORIES.map((cat) => {
          const items = results.filter((e) => e.category === cat);
          if (!items.length) return null;
          return (
            <section key={cat} aria-labelledby={`cat-${cat}`}>
              <h2 id={`cat-${cat}`} className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {cat}
              </h2>
              <div className="space-y-3">
                {items.map((e) => (
                  <Card
                    key={e.id}
                    id={e.id}
                    className={cn("scroll-mt-24 px-5 py-4 transition-shadow", target === e.id && "ring-2 ring-accent")}
                  >
                    <h3 className="font-semibold">
                      {e.term}
                      {e.aka?.length ? <span className="ml-2 text-xs font-normal text-muted-foreground">also: {e.aka.join(", ")}</span> : null}
                    </h3>
                    <p className="mt-1.5 text-sm">{e.definition}</p>
                    <dl className="mt-2 space-y-1 text-sm">
                      {e.formula && (
                        <div className="flex gap-2">
                          <dt className="w-28 shrink-0 text-muted-foreground">Formula</dt>
                          <dd className="font-mono text-[13px]">{e.formula}</dd>
                        </div>
                      )}
                      {e.typical && (
                        <div className="flex gap-2">
                          <dt className="w-28 shrink-0 text-muted-foreground">Rule of thumb</dt>
                          <dd>{e.typical}</dd>
                        </div>
                      )}
                      {e.why && (
                        <div className="flex gap-2">
                          <dt className="w-28 shrink-0 text-muted-foreground">Why it matters</dt>
                          <dd>{e.why}</dd>
                        </div>
                      )}
                    </dl>
                  </Card>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
