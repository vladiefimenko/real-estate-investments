"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  BookOpen,
  Building2,
  CornerDownLeft,
  FileText,
  GraduationCap,
  Gauge,
  GitCompareArrows,
  Keyboard,
  LayoutDashboard,
  MonitorPlay,
  Plus,
  Search,
  Settings,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { Dialog, DialogContent } from "@/components/ui/overlays";
import { useProperties } from "@/hooks/queries";
import { useAuth } from "@/lib/auth";
import { stripDemo } from "@/lib/format";
import { cn } from "@/lib/utils";

type Item = { id: string; group: string; label: string; hint?: string; icon: LucideIcon; keywords?: string; run: () => void };

const DEAL_TABS: [slug: string, label: string][] = [
  ["", "Overview"],
  ["underwriting", "Underwriting"],
  ["documents", "Documents"],
  ["scenarios", "Scenarios & Risk"],
  ["financing", "Financing"],
  ["valuation", "Valuation"],
  ["analyst", "AI Analyst"],
  ["reports", "Reports"],
  ["activity", "Activity"],
];

/** Two-key "go to" shortcuts (press G, then the letter). */
const GO_TO: Record<string, [href: string, label: string]> = {
  d: ["/dashboard", "Dashboard"],
  l: ["/deals", "Deals list"],
  c: ["/compare", "Compare"],
  g: ["/glossary", "Glossary"],
  s: ["/settings", "Settings"],
};

export const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ["⌘/Ctrl", "K"], label: "Open the command palette" },
  { keys: ["N"], label: "New deal" },
  ...Object.entries(GO_TO).map(([k, [, label]]) => ({ keys: ["G", k.toUpperCase()], label: `Go to ${label}` })),
  { keys: ["?"], label: "Show keyboard shortcuts" },
  { keys: ["J", "K", "A", "R"], label: "On a document review: move, accept, reject" },
];

const isMac = () => typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

function typingTarget(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/** ⌘K command palette plus global keyboard shortcuts. Rendered once in the app shell. */
export function CommandPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const { hasRole, org } = useAuth();
  const external = org?.role === "external";
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const deals = useProperties();
  const canCreate = hasRole("analyst");
  const mac = useSyncExternalStore(
    () => () => {},
    isMac,
    () => false,
  );

  // Global shortcuts.
  useEffect(() => {
    let pendingG: number | null = null;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || typingTarget(e.target) || document.querySelector("[role=dialog]")) return;
      const k = e.key.toLowerCase();
      if (pendingG !== null) {
        window.clearTimeout(pendingG);
        pendingG = null;
        if (GO_TO[k]) {
          e.preventDefault();
          router.push(GO_TO[k][0]);
        }
        return;
      }
      if (k === "g") {
        pendingG = window.setTimeout(() => (pendingG = null), 1200);
      } else if (k === "n" && canCreate) {
        e.preventDefault();
        router.push("/deals?new=1");
      } else if (e.key === "?") {
        e.preventDefault();
        setHelp(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (pendingG !== null) window.clearTimeout(pendingG);
    };
  }, [router, canCreate]);

  const go = (href: string) => () => router.push(href);
  const dealMatch = /^\/deals\/([^/]+)/.exec(pathname);
  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    if (canCreate) out.push({ id: "new", group: "Actions", label: "New deal", hint: "N", icon: Plus, keywords: "create add", run: go("/deals?new=1") });
    out.push({ id: "keys", group: "Actions", label: "Keyboard shortcuts", hint: "?", icon: Keyboard, run: () => setHelp(true) });
    if (dealMatch) {
      const root = `/deals/${dealMatch[1]}`;
      out.push({ id: "present", group: "Actions", label: "Present this deal", icon: MonitorPlay, keywords: "present slides screen share full screen", run: go(`/present/${dealMatch[1]}`) });
      const name = deals.data?.find((d) => d.id === dealMatch[1])?.name;
      for (const [slug, label] of DEAL_TABS)
        out.push({ id: `tab-${slug}`, group: name ? `This deal: ${stripDemo(name)}` : "This deal", label, icon: FileText, run: go(slug ? `${root}/${slug}` : root) });
    }
    const nav: [string, string, LucideIcon, string][] = [
      ["/dashboard", "Dashboard", LayoutDashboard, "G D"],
      ["/deals", "Deals", Building2, "G L"],
      ["/compare", "Compare deals", GitCompareArrows, "G C"],
      ["/scorecard", "Pipeline scorecard", Gauge, ""],
      ["/glossary", "Glossary", BookOpen, "G G"],
      ["/practice", "Practice verification", GraduationCap, ""],
      ["/settings", "Settings", Settings, "G S"],
    ];
    for (const [href, label, icon, hint] of nav)
      if (!external || href === "/deals" || href === "/glossary") out.push({ id: href, group: "Go to", label, hint: hint || undefined, icon, run: go(href) });
    for (const d of deals.data ?? [])
      out.push({
        id: `deal-${d.id}`,
        group: "Deals",
        label: stripDemo(d.name),
        hint: [d.city, d.state].filter(Boolean).join(", "),
        icon: Building2,
        keywords: `${d.property_type} ${d.status} ${d.city ?? ""} ${d.state ?? ""}`,
        run: go(`/deals/${d.id}`),
      });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deals.data, pathname, canCreate, external]);

  const q = query.trim().toLowerCase();
  const results = q
    ? items.filter((i) => q.split(/\s+/).every((w) => `${i.label} ${i.group} ${i.keywords ?? ""} ${i.hint ?? ""}`.toLowerCase().includes(w)))
    : items;
  const shown = results.slice(0, 50);
  const current = Math.min(active, Math.max(0, shown.length - 1));

  const close = (o: boolean) => {
    setOpen(o);
    if (!o) {
      setQuery("");
      setActive(0);
    }
  };
  const choose = (i: Item | undefined) => {
    if (!i) return;
    close(false);
    i.run();
  };

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${current}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  let lastGroup = "";
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden h-8 items-center gap-2 rounded-md border bg-card px-2.5 text-xs text-muted-foreground hover:bg-muted md:flex"
        aria-label="Open command palette"
      >
        <Search className="size-3.5" /> Search or jump to…
        <kbd className="rounded border bg-muted px-1 font-sans text-[10px]">{mac ? "⌘" : "Ctrl"} K</kbd>
      </button>

      <DialogPrimitive.Root open={open} onOpenChange={close}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
          <DialogPrimitive.Content
            className="fixed left-1/2 top-[12vh] z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border bg-card shadow-2xl"
            aria-describedby={undefined}
          >
            <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
            <div className="flex items-center gap-2 border-b px-3">
              <Search className="size-4 text-muted-foreground" />
              <input
                autoFocus
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActive(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setActive((a) => Math.min(a + 1, shown.length - 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setActive((a) => Math.max(a - 1, 0));
                  } else if (e.key === "Enter") {
                    e.preventDefault();
                    choose(shown[current]);
                  }
                }}
                placeholder="Search deals, pages and actions…"
                className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                role="combobox"
                aria-expanded
                aria-controls="cmdk-list"
                aria-activedescendant={shown[current] ? `cmdk-${shown[current].id}` : undefined}
                aria-label="Search deals, pages and actions"
              />
            </div>
            <div ref={listRef} id="cmdk-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-1.5">
              {shown.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted-foreground">No matches.</p>}
              {shown.map((i, idx) => {
                const header = i.group !== lastGroup ? i.group : null;
                lastGroup = i.group;
                const Icon = i.icon;
                return (
                  <div key={i.id}>
                    {header && <div className="px-2.5 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{header}</div>}
                    <div
                      id={`cmdk-${i.id}`}
                      role="option"
                      aria-selected={idx === current}
                      data-index={idx}
                      onMouseMove={() => setActive(idx)}
                      onClick={() => choose(i)}
                      className={cn(
                        "flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm",
                        idx === current && "bg-muted",
                      )}
                    >
                      <Icon className="size-4 shrink-0 text-muted-foreground" />
                      <span className="flex-1 truncate">{i.label}</span>
                      {i.hint && <span className="shrink-0 text-xs text-muted-foreground">{i.hint}</span>}
                      {idx === current && <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" />}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-3 border-t px-3 py-2 text-[11px] text-muted-foreground">
              <span>↑↓ move</span>
              <span>↵ open</span>
              <span>esc close</span>
            </div>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>

      <Dialog open={help} onOpenChange={setHelp}>
        <DialogContent title="Keyboard shortcuts" description="Shortcuts work anywhere except while you're typing in a field.">
          <ul className="space-y-2 text-sm">
            {SHORTCUTS.map((s) => (
              <li key={s.label} className="flex items-center justify-between gap-4">
                <span>{s.label}</span>
                <span className="flex gap-1">
                  {s.keys.map((k) => (
                    <kbd key={k} className="min-w-6 rounded border bg-muted px-1.5 py-0.5 text-center font-sans text-xs">
                      {k}
                    </kbd>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
