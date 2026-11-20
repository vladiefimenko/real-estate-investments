"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Share2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch } from "@/components/ui/overlays";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";

interface ShareRow {
  user_id: string;
  name: string;
  email: string;
  shared: boolean;
}

/** Admins: choose which external members (lenders, partners) can see this deal. */
export function ShareDeal({ propertyId, dealName }: { propertyId: string; dealName: string }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const shares = useQuery({
    queryKey: [org, "shares", propertyId],
    queryFn: () => api<ShareRow[]>(`/api/properties/${propertyId}/shares`),
    enabled: open,
  });
  const toggle = useMutation({
    mutationFn: ({ userId, on }: { userId: string; on: boolean }) =>
      on
        ? api(`/api/properties/${propertyId}/shares`, { body: { user_id: userId } })
        : api(`/api/properties/${propertyId}/shares/${userId}`, { method: "DELETE" }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: [org, "shares", propertyId] });
      toast.success(v.on ? "Deal shared" : "Access removed");
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <>
      <Button variant="outline" size="icon" aria-label="Share with external members" title="Share with external members" onClick={() => setOpen(true)}>
        <Share2 />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Share with external members"
          description={`Lenders and partners with the External role see only the deals you share with them, read-only: ${dealName}'s overview, documents, scenarios, financing, valuation and reports.`}
        >
          {shares.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {shares.data?.length === 0 && (
            <p className="text-sm">
              No external members yet. Invite a lender or partner with the <span className="font-medium">External</span> role in{" "}
              <Link href="/settings?tab=members" className="text-accent underline-offset-2 hover:underline">
                Settings → Members
              </Link>
              , then share this deal with them here.
            </p>
          )}
          <ul className="space-y-2">
            {shares.data?.map((s) => (
              <li key={s.user_id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{s.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{s.email}</div>
                </div>
                <Switch
                  checked={s.shared}
                  disabled={toggle.isPending}
                  onCheckedChange={(on) => toggle.mutate({ userId: s.user_id, on })}
                  aria-label={`Share with ${s.name}`}
                />
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
