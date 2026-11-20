"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileStack, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorBlock, LoadingBlock, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime, stripDemo, STATUS_LABELS } from "@/lib/format";

interface Queue {
  counts: Record<string, number>;
  documents: { id: string; name: string; type: string; status: string; error: string | null; extractor: string | null; property_id: string; property_name: string; property_stage: string; created_at: string }[];
}

const STATUS: Record<string, { label: string; variant: "success" | "warning" | "danger" | "outline" }> = {
  extracted: { label: "Extracted", variant: "success" },
  processing: { label: "Processing", variant: "warning" },
  uploaded: { label: "Queued", variant: "outline" },
  failed: { label: "Failed", variant: "danger" },
};

/** Every document across the workspace, with batch re-processing (deals at IC go first). */
export default function DocumentQueuePage() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("analyst");
  const [status, setStatus] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  const q = useQuery({
    queryKey: [org, "document-queue", status],
    queryFn: () => api<Queue>(`/api/org/document-queue${status ? `?status=${status}` : ""}`),
    refetchInterval: (query) => ((query.state.data?.counts.processing ?? 0) + (query.state.data?.counts.uploaded ?? 0) > 0 ? 3000 : false),
  });
  const run = useMutation({
    mutationFn: (ids: string[]) => api<{ queued: number }>("/api/documents/batch-extract", { body: { document_ids: ids } }),
    onSuccess: (r) => {
      setSel([]);
      qc.invalidateQueries({ queryKey: [org] });
      toast.success(`Re-processing ${r.queued} document${r.queued === 1 ? "" : "s"}. Deals at IC go first.`);
    },
    onError: (e) => toast.error(e.message),
  });
  const docs = q.data?.documents ?? [];
  const failed = docs.filter((d) => d.status === "failed").map((d) => d.id);
  const allSel = docs.length > 0 && sel.length === Math.min(docs.length, 100);

  return (
    <>
      <PageHeader
        title="Document queue"
        description="Every document across your deals and its processing status. Select documents to re-process them together, for example after a template change or a failed upload."
        actions={
          canEdit && (
            <>
              {failed.length > 0 && (
                <Button variant="outline" onClick={() => run.mutate(failed.slice(0, 100))} loading={run.isPending && run.variables?.length === failed.length}>
                  <RefreshCw /> Retry {failed.length} failed
                </Button>
              )}
              <Button disabled={!sel.length} onClick={() => run.mutate(sel)} loading={run.isPending && run.variables === sel}>
                <RefreshCw /> Re-process {sel.length || ""} selected
              </Button>
            </>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44" aria-label="Filter by status">
          <option value="">All statuses</option>
          {Object.entries(STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </Select>
        {Object.entries(q.data?.counts ?? {}).map(([k, n]) => (
          <Badge key={k} variant={STATUS[k]?.variant ?? "outline"}>
            {n} {STATUS[k]?.label.toLowerCase() ?? k}
          </Badge>
        ))}
      </div>
      {q.isLoading && <LoadingBlock rows={6} />}
      {q.error && <ErrorBlock error={q.error} />}
      {q.data && docs.length === 0 && <EmptyState icon={FileStack} title="No documents" description="Upload documents on a deal's Documents tab; they'll appear here." />}
      {docs.length > 0 && (
        <Card>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                {canEdit && (
                  <TH className="w-8 pl-4">
                    <input type="checkbox" aria-label="Select all (up to 100)" checked={allSel} onChange={(e) => setSel(e.target.checked ? docs.slice(0, 100).map((d) => d.id) : [])} />
                  </TH>
                )}
                <TH>Document</TH>
                <TH>Deal</TH>
                <TH>Status</TH>
                <TH>Uploaded</TH>
              </TR>
            </THead>
            <TBody>
              {docs.map((d) => (
                <TR key={d.id}>
                  {canEdit && (
                    <TD className="pl-4">
                      <input type="checkbox" aria-label={`Select ${d.name}`} checked={sel.includes(d.id)} onChange={(e) => setSel(e.target.checked ? [...sel, d.id].slice(-100) : sel.filter((x) => x !== d.id))} />
                    </TD>
                  )}
                  <TD>
                    <Link href={`/deals/${d.property_id}/documents/${d.id}`} className="font-medium hover:underline">
                      {d.name}
                    </Link>
                    {d.error && <div className="text-xs text-warning">{d.error}</div>}
                  </TD>
                  <TD>
                    <Link href={`/deals/${d.property_id}/documents`} className="hover:underline">
                      {stripDemo(d.property_name)}
                    </Link>
                    <div className="text-xs text-muted-foreground">{STATUS_LABELS[d.property_stage] ?? d.property_stage}</div>
                  </TD>
                  <TD>
                    <Badge variant={STATUS[d.status]?.variant ?? "outline"}>{STATUS[d.status]?.label ?? d.status}</Badge>
                  </TD>
                  <TD className="text-xs text-muted-foreground">{relativeTime(d.created_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
    </>
  );
}
