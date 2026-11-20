"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, FileText, GraduationCap, MonitorPlay, Presentation, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Callout } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/overlays";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Select, Textarea } from "@/components/ui/primitives";
import { useFeature, useOrgKey } from "@/hooks/queries";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { stripDemo } from "@/lib/format";

type ReportKey = "excel" | "one-pager" | "ic-memo" | "junior-pack" | "presentation";

export default function ReportsPage() {
  const { property, scenarios, base } = useDeal();
  const { hasRole } = useAuth();
  const org = useOrgKey();
  const qc = useQueryClient();
  const icEnabled = useFeature("ic_memo");
  const [scenarioId, setScenarioId] = useState(base?.id ?? scenarios[0]?.id ?? "");
  const [aiNarrative, setAiNarrative] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [coverNote, setCoverNote] = useState("");
  const [deck, setDeck] = useState({ title: "", preparedFor: "", firm: "", risk: true });
  const [busy, setBusy] = useState<Partial<Record<ReportKey, boolean>>>({});

  const status = useQuery({
    queryKey: [org, "analyst-status"],
    queryFn: () => api<{ ai_available: boolean; model: string }>("/api/analyst/status"),
    staleTime: 60_000,
    enabled: hasRole("viewer"), // external members can't use the analyst
  });
  const aiAvailable = status.data?.ai_available === true;
  const scenario = scenarios.find((s) => s.id === scenarioId);
  const slug = stripDemo(property.name).replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") || "deal";

  const run = async (key: ReportKey, path: string, fallback: string, label: string) => {
    setBusy((b) => ({ ...b, [key]: true }));
    try {
      await download(path, fallback);
      toast.success(`${label} downloaded`);
      qc.invalidateQueries({ queryKey: [org, "audit", property.id] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Could not generate the ${label.toLowerCase()}`);
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  };

  const qs = `scenario_id=${encodeURIComponent(scenarioId)}`;
  const root = `/api/properties/${property.id}/reports`;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Reports &amp; exports</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Generated on demand from the selected scenario&apos;s current assumptions. Every export is logged in the deal&apos;s activity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor="report-scenario" className="whitespace-nowrap">
            Scenario
          </Label>
          <Select id="report-scenario" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} className="w-56">
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.is_base ? " (base)" : ""}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {property.is_demo && (
        <Callout tone="danger" title="Demo watermark">
          This is a fictional demo deal. Every page and sheet of these exports is watermarked as demonstration data.
        </Callout>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <ReportCard
          icon={FileSpreadsheet}
          title="Full underwriting model"
          format="Excel (.xlsx)"
          description="Assumptions, annual cash flows, debt schedule, sources & uses, returns and sensitivity, built with working formulas, plus a reconciliation sheet tying formulas to engine outputs."
          action={
            <Button
              className="w-full"
              loading={!!busy.excel}
              disabled={!scenarioId}
              onClick={() => run("excel", `${root}/excel?${qs}`, `${slug}-model.xlsx`, "Excel model")}
            >
              <Download /> Download Excel model
            </Button>
          }
        />
        <ReportCard
          icon={FileText}
          title="One-page deal summary"
          format="PDF"
          description="Property snapshot, key returns and leverage metrics, sources & uses and headline risks on a single page for quick circulation."
          action={
            <Button
              className="w-full"
              loading={!!busy["one-pager"]}
              disabled={!scenarioId}
              onClick={() => run("one-pager", `${root}/one-pager?${qs}`, `${slug}-summary.pdf`, "One-page summary")}
            >
              <Download /> Download one-pager
            </Button>
          }
        />
        <ReportCard
          icon={Presentation}
          title="Investment Committee memorandum"
          format="PDF"
          description="Multi-page memo: deal overview, underwriting, scenario comparison, IRR sensitivity, verified document data and risk assessment."
          disabledNote={icEnabled === false ? "The IC memorandum generator is not enabled on this workspace's plan." : undefined}
          extra={
            <div className="space-y-1.5 rounded-md border bg-muted/40 px-3 py-2.5">
              <div className="flex items-start gap-3">
                <Switch
                  id="ic-ai"
                  checked={aiNarrative && aiAvailable}
                  onCheckedChange={setAiNarrative}
                  disabled={!aiAvailable || icEnabled === false}
                  aria-describedby="ic-ai-note"
                  className="mt-0.5"
                />
                <Label htmlFor="ic-ai" className="text-xs leading-snug text-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Sparkles className="size-3.5" aria-hidden /> Include AI-drafted narrative
                  </span>
                </Label>
              </div>
              <p id="ic-ai-note" className="text-[11px] leading-snug text-muted-foreground">
                {status.isLoading
                  ? "Checking AI availability…"
                  : aiAvailable
                    ? `Requires AI configured (${status.data?.model}). Narrative sections are clearly labelled as AI-drafted for human review; all figures come from the engine.`
                    : "AI is not configured for this workspace, so the memo uses the standard template narrative only."}
              </p>
            </div>
          }
          action={
            <Button
              className="w-full"
              loading={!!busy["ic-memo"]}
              disabled={!scenarioId || icEnabled === false}
              onClick={() =>
                run(
                  "ic-memo",
                  `${root}/ic-memo?${qs}&ai_narrative=${aiNarrative && aiAvailable ? "true" : "false"}`,
                  `${slug}-IC-memo.pdf`,
                  "IC memorandum",
                )
              }
            >
              <Download /> {busy["ic-memo"] && aiNarrative && aiAvailable ? "Drafting memo…" : "Generate IC memo"}
            </Button>
          }
        />
      </div>

      <ReportCard
        icon={MonitorPlay}
        title="Client presentation"
        format="PDF · landscape"
        description="A clean, landscape deck for clients, lenders and partners: cover page, investment highlights, cash flow chart and capital stack, and optional key considerations. Your firm name replaces the Axiom header."
        extra={
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="pr-title">Title (optional)</Label>
              <Input id="pr-title" value={deck.title} maxLength={120} onChange={(e) => setDeck({ ...deck, title: e.target.value })} placeholder={stripDemo(property.name)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pr-for">Prepared for (optional)</Label>
              <Input id="pr-for" value={deck.preparedFor} maxLength={120} onChange={(e) => setDeck({ ...deck, preparedFor: e.target.value })} placeholder="e.g. First Coast Bank" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pr-firm">Your firm name (optional)</Label>
              <Input id="pr-firm" value={deck.firm} maxLength={80} onChange={(e) => setDeck({ ...deck, firm: e.target.value })} placeholder="Shown in the header" />
            </div>
            <div className="flex items-center gap-2 sm:col-span-3">
              <Switch id="pr-risk" checked={deck.risk} onCheckedChange={(v) => setDeck({ ...deck, risk: v })} />
              <Label htmlFor="pr-risk">Include a &ldquo;Key considerations&rdquo; page (risk flags and assumption notes)</Label>
            </div>
            {property.is_demo && <p className="text-xs text-warning sm:col-span-3">Demo deals are always watermarked.</p>}
          </div>
        }
        action={
          <Button
            className="w-full sm:w-auto"
            loading={!!busy.presentation}
            disabled={!scenarioId}
            onClick={() => {
              const p = new URLSearchParams(qs);
              if (deck.title.trim()) p.set("title", deck.title.trim());
              if (deck.preparedFor.trim()) p.set("prepared_for", deck.preparedFor.trim());
              if (deck.firm.trim()) p.set("firm_name", deck.firm.trim());
              p.set("include_risk", String(deck.risk));
              run("presentation", `${root}/presentation?${p.toString()}`, `${slug}-presentation.pdf`, "Client presentation");
            }}
          >
            <Download /> Download presentation
          </Button>
        }
      />

      <ReportCard
        icon={GraduationCap}
        title="Junior Analyst Report Pack"
        format="PDF"
        description="Four pages for a newer analyst to hand to a senior: a cover note with prepared-by and reviewed-by lines, the deal summary, every key assumption with a plain-English note on what to check, and a glossary of the terms used."
        extra={
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="jp-reviewer">Reviewed by (optional)</Label>
              <Input id="jp-reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} maxLength={120} placeholder="Your senior or team lead" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="jp-note">Cover note (optional)</Label>
              <Textarea
                id="jp-note"
                value={coverNote}
                onChange={(e) => setCoverNote(e.target.value)}
                maxLength={1500}
                rows={2}
                placeholder="e.g. First pass. Questions on the expense ratio and the exit cap."
              />
            </div>
          </div>
        }
        action={
          <Button
            className="w-full sm:w-auto"
            loading={!!busy["junior-pack"]}
            disabled={!scenarioId}
            onClick={() => {
              const p = new URLSearchParams(qs);
              if (reviewer.trim()) p.set("reviewed_by", reviewer.trim());
              if (coverNote.trim()) p.set("note", coverNote.trim());
              run("junior-pack", `${root}/junior-pack?${p.toString()}`, `${slug}-junior-pack.pdf`, "Junior report pack");
            }}
          >
            <Download /> Download junior pack
          </Button>
        }
      />

      {scenario && (
        <p className="text-xs text-muted-foreground">
          Exports use <span className="font-medium text-foreground">{scenario.name}</span>
          {scenario.is_base ? " (base scenario)" : ""}. Figures are recalculated by the underwriting engine at export time.
        </p>
      )}
    </div>
  );
}

function ReportCard({
  icon: Icon,
  title,
  format,
  description,
  extra,
  action,
  disabledNote,
}: {
  icon: LucideIcon;
  title: string;
  format: string;
  description: string;
  extra?: React.ReactNode;
  action: React.ReactNode;
  disabledNote?: string;
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="rounded-md bg-muted p-2">
            <Icon className="size-5 text-muted-foreground" aria-hidden />
          </div>
          <Badge variant="outline">{format}</Badge>
        </div>
        <CardTitle className="mt-2">{title}</CardTitle>
        <CardDescription className="leading-relaxed">{description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-3">
        {extra}
        {disabledNote && <p className="text-xs text-warning">{disabledNote}</p>}
        {action}
      </CardContent>
    </Card>
  );
}
