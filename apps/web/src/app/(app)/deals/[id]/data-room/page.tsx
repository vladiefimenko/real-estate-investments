"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FolderLock, PackagePlus, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Callout, EmptyState, ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch } from "@/components/ui/overlays";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { rawFetch, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLong, dateTime, relativeTime } from "@/lib/format";

interface RoomDoc {
  id: string;
  name: string;
  type: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  data_room: boolean;
  created_at: string;
  published: boolean;
}
interface Room {
  documents: RoomDoc[];
  my_access: { can_download: boolean; expires_at: string | null } | null;
}
interface Share {
  user_id: string;
  name: string;
  email: string;
  shared: boolean;
  expired: boolean;
  expires_at: string | null;
  can_download: boolean;
}
interface LogRow {
  at: string;
  action: string;
  who: string;
  email: string | null;
  external: boolean;
  document: string | null;
}

const ACTION: Record<string, string> = {
  "dataroom.view": "viewed",
  "dataroom.download": "downloaded",
  "dataroom.add": "added to the data room",
  "dataroom.remove": "removed from the data room",
  "dataroom.publish": "published a report package",
  "deal.share": "changed guest access",
  "deal.unshare": "removed a guest",
};
const kb = (n: number) => (n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

async function downloadDoc(d: RoomDoc) {
  const r = await rawFetch(`/api/documents/${d.id}/download`);
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "Download failed");
  }
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = d.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function DataRoomPage() {
  const { property, canEdit } = useDeal();
  const { org: membership, hasRole } = useAuth();
  const external = membership?.role === "external";
  const org = useOrgKey();
  const room = useQuery({ queryKey: [org, "data-room", property.id], queryFn: () => api<Room>(`/api/properties/${property.id}/data-room`) });
  const dl = useMutation({ mutationFn: downloadDoc, onError: (e) => toast.error(e.message) });

  if (room.isLoading) return <LoadingBlock rows={4} />;
  if (room.error) return <ErrorBlock error={room.error} />;
  const docs = room.data?.documents ?? [];
  const inRoom = docs.filter((d) => d.data_room);

  if (external) {
    const a = room.data?.my_access;
    return (
      <div className="space-y-4">
        <Callout title="Shared with you">
          {a?.expires_at ? `Your access ends ${dateLong(a.expires_at)}. ` : ""}
          {a?.can_download ? "PDF downloads are stamped with your email and the date." : "This data room is view-only for you: open documents to read them here."} Your views and downloads are recorded.
        </Callout>
        {inRoom.length === 0 ? (
          <EmptyState icon={FolderLock} title="Nothing here yet" description="The sponsor hasn't added documents to this data room yet." />
        ) : (
          <Card>
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Document</TH>
                  <TH>Added</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {inRoom.map((d) => (
                  <TR key={d.id}>
                    <TD>
                      <div className="font-medium">{d.name}</div>
                      <div className="text-xs text-muted-foreground">{kb(d.size_bytes)}</div>
                    </TD>
                    <TD className="text-xs text-muted-foreground">{dateTime(d.created_at)}</TD>
                    <TD className="text-right">
                      <div className="flex justify-end gap-1.5">
                        {!d.published && (
                          <Button size="sm" variant="ghost" asChild>
                            <Link href={`/deals/${property.id}/documents/${d.id}`}>
                              <Eye /> View
                            </Link>
                          </Button>
                        )}
                        {a?.can_download && (
                          <Button size="sm" variant="outline" loading={dl.isPending && dl.variables?.id === d.id} onClick={() => dl.mutate(d)}>
                            <Download /> Download
                          </Button>
                        )}
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <RoomDocuments propertyId={property.id} docs={docs} canEdit={canEdit} onDownload={(d) => dl.mutate(d)} />
      {hasRole("admin") && <Guests propertyId={property.id} />}
      {hasRole("admin") && <AccessLog propertyId={property.id} />}
    </div>
  );
}

function RoomDocuments({ propertyId, docs, canEdit, onDownload }: { propertyId: string; docs: RoomDoc[]; canEdit: boolean; onDownload: (d: RoomDoc) => void }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [publishing, setPublishing] = useState(false);
  const [items, setItems] = useState<string[]>(["one_pager", "ic_memo", "excel"]);
  const toggle = useMutation({
    mutationFn: ({ d, on }: { d: RoomDoc; on: boolean }) => api(`/api/documents/${d.id}/data-room`, { method: "PUT", body: { in_room: on } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "data-room", propertyId] }),
    onError: (e) => toast.error(e.message),
  });
  const publish = useMutation({
    mutationFn: () => api<{ documents: RoomDoc[] }>(`/api/properties/${propertyId}/data-room/publish`, { body: { items } }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: [org] });
      setPublishing(false);
      toast.success(`Published ${r.documents.length} file${r.documents.length === 1 ? "" : "s"} to the data room`);
    },
    onError: (e) => toast.error(e.message),
  });
  const count = docs.filter((d) => d.data_room).length;
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FolderLock className="size-4" /> Data room · {count} document{count === 1 ? "" : "s"}
          </CardTitle>
          <CardDescription>
            External guests (lenders, partners) see only the documents switched on here. Their PDF downloads are stamped with their email and the date, and
            every view and download is logged. IC votes and internal notes are never included.
          </CardDescription>
        </div>
        {canEdit && (
          <Button onClick={() => setPublishing(true)}>
            <PackagePlus /> Publish package
          </Button>
        )}
      </CardHeader>
      <CardContent className="px-0 pb-2">
        {docs.length === 0 ? (
          <p className="px-6 pb-4 text-sm text-muted-foreground">
            No documents on this deal yet. Upload them on the{" "}
            <Link href={`/deals/${propertyId}/documents`} className="underline underline-offset-4">
              Documents
            </Link>{" "}
            tab, or publish a report package.
          </p>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH className="pl-6">In data room</TH>
                <TH>Document</TH>
                <TH>Added</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {docs.map((d) => (
                <TR key={d.id}>
                  <TD className="pl-6">
                    <Switch checked={d.data_room} disabled={!canEdit || (toggle.isPending && toggle.variables?.d.id === d.id)} onCheckedChange={(on) => toggle.mutate({ d, on })} aria-label={`${d.name} in data room`} />
                  </TD>
                  <TD>
                    <div className="flex flex-wrap items-center gap-1.5 font-medium">
                      {d.name}
                      {d.published && <Badge variant="outline">Published report</Badge>}
                    </div>
                    <div className="text-xs text-muted-foreground">{kb(d.size_bytes)}</div>
                  </TD>
                  <TD className="text-xs text-muted-foreground">{dateTime(d.created_at)}</TD>
                  <TD className="pr-6 text-right">
                    <Button size="sm" variant="ghost" onClick={() => onDownload(d)}>
                      <Download /> Download
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
      <Dialog open={publishing} onOpenChange={setPublishing}>
        <DialogContent title="Publish a report package" description="Generates the latest reports from the base case and puts them straight into the data room. IC votes and deliberations are left out of the memo.">
          <div className="space-y-2">
            {(
              [
                ["one_pager", "One-page summary (PDF)"],
                ["ic_memo", "Investment memo (PDF)"],
                ["excel", "Excel model with live formulas"],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                <input type="checkbox" checked={items.includes(k)} onChange={(e) => setItems(e.target.checked ? [...items, k] : items.filter((x) => x !== k))} />
                {label}
              </label>
            ))}
          </div>
          <div className="flex justify-end">
            <Button disabled={!items.length} loading={publish.isPending} onClick={() => publish.mutate()}>
              <PackagePlus /> Publish {items.length} file{items.length === 1 ? "" : "s"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Guests({ propertyId }: { propertyId: string }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const shares = useQuery({ queryKey: [org, "shares", propertyId], queryFn: () => api<Share[]>(`/api/properties/${propertyId}/shares`) });
  const [edits, setEdits] = useState<Record<string, { until: string; download: boolean }>>({});
  const save = useMutation({
    mutationFn: ({ s, until, download }: { s: Share; until: string; download: boolean }) =>
      api(`/api/properties/${propertyId}/shares`, { body: { user_id: s.user_id, can_download: download, expires_at: until ? new Date(`${until}T23:59:59`).toISOString() : null } }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: [org, "shares", propertyId] });
      setEdits(({ [v.s.user_id]: _, ...rest }) => rest);
      toast.success(`Access saved for ${v.s.name}`);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (s: Share) => api(`/api/properties/${propertyId}/shares/${s.user_id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "shares", propertyId] }),
    onError: (e) => toast.error(e.message),
  });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-4" /> Guests
        </CardTitle>
        <CardDescription>
          External members you can give access to. Set an end date and access stops automatically; turn off downloads for view-only access. Invite guests
          with the External role in{" "}
          <Link href="/settings?tab=members" className="underline underline-offset-4">
            Settings → Members
          </Link>
          .
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {shares.isLoading && <LoadingBlock rows={2} />}
        {shares.data?.length === 0 && <p className="text-sm text-muted-foreground">No external members in this workspace yet.</p>}
        {shares.data?.map((s) => {
          const e = edits[s.user_id] ?? { until: s.expires_at ? s.expires_at.slice(0, 10) : "", download: s.can_download };
          const dirty = !!edits[s.user_id];
          return (
            <div key={s.user_id} className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2 text-sm">
              <div className="min-w-40 flex-1">
                <div className="font-medium">{s.name}</div>
                <div className="text-xs text-muted-foreground">{s.email}</div>
              </div>
              <Badge variant={s.shared ? "success" : s.expired ? "warning" : "outline"}>{s.shared ? "Has access" : s.expired ? "Expired" : "No access"}</Badge>
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                Access until
                <Input type="date" min={today} value={e.until} onChange={(ev) => setEdits({ ...edits, [s.user_id]: { ...e, until: ev.target.value } })} className="h-8 w-40" aria-label={`Access end date for ${s.name}`} />
              </label>
              <label className="flex items-center gap-1.5 text-xs">
                <Switch checked={e.download} onCheckedChange={(v) => setEdits({ ...edits, [s.user_id]: { ...e, download: v } })} aria-label={`Allow downloads for ${s.name}`} />
                Downloads
              </label>
              <Button size="sm" variant={s.shared && !dirty ? "outline" : "default"} disabled={s.shared && !dirty} loading={save.isPending && save.variables?.s.user_id === s.user_id} onClick={() => save.mutate({ s, until: e.until, download: e.download })}>
                {s.shared ? "Save" : "Give access"}
              </Button>
              {(s.shared || s.expired) && (
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(s)}>
                  Remove
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function AccessLog({ propertyId }: { propertyId: string }) {
  const org = useOrgKey();
  const log = useQuery({ queryKey: [org, "data-room-log", propertyId], queryFn: () => api<LogRow[]>(`/api/properties/${propertyId}/data-room/access-log`) });
  const [guestsOnly, setGuestsOnly] = useState(true);
  const rows = (log.data ?? []).filter((r) => !guestsOnly || r.external);
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Access log</CardTitle>
          <CardDescription>Who looked at or downloaded what, and changes to the data room and guest access.</CardDescription>
        </div>
        <label className="flex items-center gap-2 text-xs">
          <Switch checked={guestsOnly} onCheckedChange={setGuestsOnly} aria-label="Guests only" /> Guests only
        </label>
      </CardHeader>
      <CardContent className="px-0 pb-2">
        {log.isLoading && <LoadingBlock rows={3} />}
        {rows.length === 0 && !log.isLoading && <p className="px-6 pb-4 text-sm text-muted-foreground">No activity yet.</p>}
        {rows.length > 0 && (
          <Table>
            <TBody>
              {rows.slice(0, 100).map((r, i) => (
                <TR key={i}>
                  <TD className="pl-6">
                    <span className="font-medium">{r.who}</span>
                    {r.external && <span className="ml-1.5 text-xs text-muted-foreground">({r.email})</span>}
                  </TD>
                  <TD>
                    {ACTION[r.action] ?? r.action} {r.document && <span className="font-medium">{r.document}</span>}
                  </TD>
                  <TD className="pr-6 text-right text-xs text-muted-foreground" title={dateTime(r.at)}>
                    {relativeTime(r.at)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
