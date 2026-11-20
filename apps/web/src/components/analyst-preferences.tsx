"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, SlidersHorizontal, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Callout } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { Card, Input, Label, Textarea } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";

interface Prefs {
  instructions: string | null;
  dscr_floor: number | null;
  exit_cap_stress_bps: number | null;
}
interface Note {
  id: string;
  text: string;
  created_at: string;
}
interface PrefsView {
  workspace: Prefs;
  personal: Prefs & { notes: Note[] };
  effective: { dscr_floor: number | null; exit_cap_stress_bps: number | null; workspace_instructions: string | null; personal_instructions: string | null; notes: string[] };
  can_edit_workspace: boolean;
}

function usePrefs() {
  const org = useOrgKey();
  return useQuery({ queryKey: [org, "analyst-prefs"], queryFn: () => api<PrefsView>("/api/analyst/preferences") });
}

function PrefsForm({ initial, onSave, saving, disabled, who }: { initial: Prefs; onSave: (p: Prefs) => void; saving: boolean; disabled?: boolean; who: string }) {
  const [instructions, setInstructions] = useState(initial.instructions ?? "");
  const [dscr, setDscr] = useState(initial.dscr_floor?.toString() ?? "");
  const [bps, setBps] = useState(initial.exit_cap_stress_bps?.toString() ?? "");
  const dscrN = dscr.trim() ? Number(dscr) : null;
  const bpsN = bps.trim() ? Number(bps) : null;
  const dscrOk = dscrN === null || (dscrN >= 1 && dscrN <= 3);
  const bpsOk = bpsN === null || (Number.isInteger(bpsN) && bpsN >= 10 && bpsN <= 300);
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (dscrOk && bpsOk) onSave({ instructions: instructions.trim() || null, dscr_floor: dscrN, exit_cap_stress_bps: bpsN });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${who}-dscr`}>Flag DSCR below</Label>
          <div className="flex items-center gap-1.5">
            <Input id={`${who}-dscr`} inputMode="decimal" value={dscr} onChange={(e) => setDscr(e.target.value)} placeholder="e.g. 1.30" className="w-28" disabled={disabled} aria-invalid={!dscrOk} />
            <span className="text-sm text-muted-foreground">x</span>
          </div>
          {!dscrOk && <p className="text-xs text-destructive">Between 1.00 and 3.00.</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${who}-bps`}>Standard exit-cap stress</Label>
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-muted-foreground">+</span>
            <Input id={`${who}-bps`} inputMode="numeric" value={bps} onChange={(e) => setBps(e.target.value)} placeholder="e.g. 50" className="w-24" disabled={disabled} aria-invalid={!bpsOk} />
            <span className="text-sm text-muted-foreground">bps</span>
          </div>
          {!bpsOk && <p className="text-xs text-destructive">A whole number from 10 to 300.</p>}
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${who}-instructions`}>Instructions</Label>
        <Textarea
          id={`${who}-instructions`}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          maxLength={2000}
          rows={4}
          disabled={disabled}
          placeholder={'e.g. "Write in concise IC-memo bullets." "Always mention the debt yield." "Compare against our 1.35x lender standard."'}
        />
        <p className="text-xs text-muted-foreground">Style and emphasis only. The analyst still only uses numbers from the engine and verified documents.</p>
      </div>
      {!disabled && (
        <div className="flex justify-end">
          <Button type="submit" loading={saving} disabled={!dscrOk || !bpsOk}>
            Save
          </Button>
        </div>
      )}
    </form>
  );
}

/** Sidebar card on the AI Analyst page: what the analyst follows for you, with an editor. */
export function AnalystPreferences({ aiAvailable }: { aiAvailable: boolean }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const prefs = usePrefs();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const done = (msg: string) => (v: PrefsView) => {
    qc.setQueryData([org, "analyst-prefs"], v);
    toast.success(msg);
  };
  const savePersonal = useMutation({
    mutationFn: (p: Prefs) => api<PrefsView>("/api/analyst/preferences/personal", { method: "PUT", body: p }),
    onSuccess: done("Your preferences are saved"),
    onError: (e) => toast.error(e.message),
  });
  const saveWorkspace = useMutation({
    mutationFn: (p: Prefs) => api<PrefsView>("/api/analyst/preferences/workspace", { method: "PUT", body: p }),
    onSuccess: done("Workspace standards saved"),
    onError: (e) => toast.error(e.message),
  });
  const addNote = useMutation({
    mutationFn: (text: string) => api("/api/analyst/notes", { body: { text } }),
    onSuccess: () => {
      setNote("");
      qc.invalidateQueries({ queryKey: [org, "analyst-prefs"] });
    },
    onError: (e) => toast.error(e.message),
  });
  const delNote = useMutation({
    mutationFn: (id: string) => api(`/api/analyst/notes/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "analyst-prefs"] }),
    onError: (e) => toast.error(e.message),
  });
  const d = prefs.data;
  const e = d?.effective;
  const items = e
    ? [
        e.dscr_floor ? `Flags DSCR below ${e.dscr_floor.toFixed(2)}x` : null,
        e.exit_cap_stress_bps ? `Suggests an exit cap +${e.exit_cap_stress_bps} bps stress` : null,
        e.workspace_instructions ? "Follows your workspace standards" : null,
        e.personal_instructions ? "Follows your personal instructions" : null,
        e.notes.length ? `Remembers ${e.notes.length} note${e.notes.length === 1 ? "" : "s"}` : null,
      ].filter(Boolean)
    : [];

  return (
    <>
      <Card className="space-y-2 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <SlidersHorizontal className="size-4" /> Your analyst
          </div>
          <Button size="sm" variant="outline" onClick={() => setOpen(true)} disabled={!d}>
            Customize
          </Button>
        </div>
        {items.length ? (
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {items.map((i) => (
              <li key={i}>• {i}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">Set your standards (like a minimum DSCR) and how you like answers written, and the analyst will remember them.</p>
        )}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Customize the AI analyst" description="Your standards and style, remembered across every deal in this workspace." className="max-w-2xl">
          {!aiAvailable && (
            <Callout tone="warn">
              No AI model is connected, so the built-in analyst applies the DSCR flag and exit-cap stress only. Instructions and notes take effect once an
              Anthropic API key is added.
            </Callout>
          )}
          {d && (
            <Tabs defaultValue="me" className="mt-3">
              <TabsList>
                <TabsTrigger value="me">For me</TabsTrigger>
                <TabsTrigger value="workspace">Workspace standards</TabsTrigger>
                <TabsTrigger value="notes">Remembered notes ({d.personal.notes.length})</TabsTrigger>
              </TabsList>
              <TabsContent value="me" className="mt-4">
                <p className="mb-3 text-xs text-muted-foreground">Private to you. Where you set a threshold, it replaces the workspace standard for your questions.</p>
                <PrefsForm who="me" initial={d.personal} saving={savePersonal.isPending} onSave={(p) => savePersonal.mutate(p)} />
              </TabsContent>
              <TabsContent value="workspace" className="mt-4">
                <p className="mb-3 text-xs text-muted-foreground">
                  Applies to everyone in the workspace. {d.can_edit_workspace ? "Only admins can change these." : "Only admins can change these; ask one if they need updating."}
                </p>
                <PrefsForm who="ws" initial={d.workspace} saving={saveWorkspace.isPending} disabled={!d.can_edit_workspace} onSave={(p) => saveWorkspace.mutate(p)} />
              </TabsContent>
              <TabsContent value="notes" className="mt-4 space-y-3">
                <p className="text-xs text-muted-foreground">
                  Corrections and facts the analyst should keep in mind, such as &quot;Our lenders size to 1.35x&quot;. You can also add one from any answer with
                  &quot;Remember a correction&quot;.
                </p>
                <form
                  className="flex gap-2"
                  onSubmit={(ev) => {
                    ev.preventDefault();
                    if (note.trim()) addNote.mutate(note.trim());
                  }}
                >
                  <Input value={note} onChange={(ev) => setNote(ev.target.value)} maxLength={500} placeholder="Add a note…" aria-label="New note" />
                  <Button type="submit" disabled={!note.trim()} loading={addNote.isPending}>
                    Add
                  </Button>
                </form>
                <ul className="space-y-1.5">
                  {d.personal.notes.map((n) => (
                    <li key={n.id} className="flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
                      <span className="flex-1">{n.text}</span>
                      <Button size="icon-sm" variant="ghost" aria-label="Delete note" onClick={() => delNote.mutate(n.id)}>
                        <Trash2 />
                      </Button>
                    </li>
                  ))}
                  {!d.personal.notes.length && <li className="text-sm text-muted-foreground">No notes yet.</li>}
                </ul>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Small action under an analyst answer: save a correction for the analyst to remember. */
export function RememberCorrection() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const save = useMutation({
    mutationFn: () => api("/api/analyst/notes", { body: { text: text.trim() } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "analyst-prefs"] });
      setOpen(false);
      setText("");
      toast.success("The analyst will remember that");
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
        <BookmarkPlus className="size-3" /> Remember a correction
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Remember a correction" description="What should the analyst keep in mind next time? It's saved to your notes and used for future answers.">
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) save.mutate();
            }}
          >
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={500} rows={3} autoFocus aria-label="Correction" placeholder='e.g. "We treat RUBS income as other income, not rent."' />
            <div className="flex justify-end">
              <Button type="submit" disabled={!text.trim()} loading={save.isPending}>
                Remember
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
