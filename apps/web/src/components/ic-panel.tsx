"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gavel } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SectionCard } from "@/components/deal-widgets";
import { Button } from "@/components/ui/button";
import { Badge, Label, Select, Textarea } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type VoteKey = "approve" | "conditional" | "decline" | "abstain";

interface IcState {
  stage: string;
  round: number;
  open: boolean;
  votes: { user_id: string; name: string; vote: VoteKey; comment: string | null; updated_at: string }[];
  tally: Record<VoteKey, number>;
  decision: { decision: "approved" | "declined" | "conditional"; notes: string | null; by: string; at: string; round: number } | null;
  my_vote: { vote: VoteKey; comment: string | null } | null;
  chain:
    | {
        name: string;
        approver_names: string[];
        min_approvals: number;
        status: "pending" | "approved" | "declined";
        actions: { user_id: string; name: string; action: "approve" | "decline"; comment: string | null; at: string }[];
      }[]
    | null;
  chain_status: "pending" | "approved" | "declined" | null;
  current_step: number | null;
  can_approve: boolean;
}

const VOTE_LABELS: Record<VoteKey, string> = { approve: "Approve", conditional: "Approve with conditions", decline: "Decline", abstain: "Abstain" };
const VOTE_TONE: Record<VoteKey, "success" | "warning" | "danger" | "outline"> = {
  approve: "success",
  conditional: "warning",
  decline: "danger",
  abstain: "outline",
};

/** Investment Committee: members vote while a deal is at IC; an admin records the decision. */
export function IcPanel({ propertyId }: { propertyId: string }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const { data } = useQuery({ queryKey: [org, "ic", propertyId], queryFn: () => api<IcState>(`/api/properties/${propertyId}/ic`) });
  const [vote, setVote] = useState<VoteKey | "">("");
  const [comment, setComment] = useState<string | null>(null);
  const [decision, setDecision] = useState<"approved" | "conditional" | "declined">("approved");
  const [notes, setNotes] = useState("");
  const [pass, setPass] = useState(true);
  const refresh = () => qc.invalidateQueries({ queryKey: [org] });
  const [approvalComment, setApprovalComment] = useState("");
  const approve = useMutation({
    mutationFn: (action: "approve" | "decline") =>
      api(`/api/properties/${propertyId}/ic/approval`, { body: { action, comment: approvalComment.trim() || null } }),
    onSuccess: (_d, action) => {
      refresh();
      setApprovalComment("");
      toast.success(action === "approve" ? "Approved. The next step has been notified." : "Declined. The deal owner and admins have been notified.");
    },
    onError: (e) => toast.error(e.message),
  });
  const cast = useMutation({
    mutationFn: () => api(`/api/properties/${propertyId}/ic/vote`, { method: "PUT", body: { vote: vote || data?.my_vote?.vote, comment: (comment ?? data?.my_vote?.comment ?? "") || null } }),
    onSuccess: () => {
      refresh();
      toast.success("Vote recorded");
      setVote("");
      setComment(null);
    },
    onError: (e) => toast.error(e.message),
  });
  const decide = useMutation({
    mutationFn: () => api(`/api/properties/${propertyId}/ic/decision`, { body: { decision, notes: notes.trim() || null, move_to_passed: decision === "declined" && pass } }),
    onSuccess: () => {
      refresh();
      toast.success("Decision recorded");
    },
    onError: (e) => toast.error(e.message),
  });

  if (!data || (data.stage !== "ic" && !data.decision)) return null;
  const myVote = vote || data.my_vote?.vote || "";
  const myComment = comment ?? data.my_vote?.comment ?? "";

  return (
    <SectionCard
      title={`Investment Committee · round ${data.round || 1}`}
      description={data.open ? "Voting is open. Members can change their vote until a decision is recorded." : "This round is decided."}
    >
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          {data.decision && (
            <div
              className={cn(
                "rounded-md border p-3",
                data.decision.decision === "declined" ? "border-destructive/40 bg-destructive/5" : "border-success/40 bg-success/5",
              )}
            >
              <div className="flex items-center gap-2 font-semibold">
                <Gavel className="size-4" /> Decision: {data.decision.decision === "conditional" ? "Approved with conditions" : data.decision.decision === "approved" ? "Approved" : "Declined"}
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Recorded by {data.decision.by} {relativeTime(data.decision.at)}
              </p>
              {data.decision.notes && <p className="mt-2 whitespace-pre-line text-sm">{data.decision.notes}</p>}
            </div>
          )}
          {data.chain && (
            <div className="rounded-md border p-3">
              <div className="mb-2 flex items-center justify-between gap-2 text-sm font-medium">
                Approval chain
                <Badge variant={data.chain_status === "approved" ? "success" : data.chain_status === "declined" ? "danger" : "outline"}>
                  {data.chain_status === "approved" ? "Complete" : data.chain_status === "declined" ? "Declined" : `Step ${(data.current_step ?? 0) + 1} of ${data.chain.length}`}
                </Badge>
              </div>
              <ol className="space-y-2">
                {data.chain.map((st, i) => (
                  <li key={i} className={cn("rounded-md border px-3 py-2 text-sm", i === data.current_step && data.chain_status === "pending" && "border-accent")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">
                        {i + 1}. {st.name}
                      </span>
                      <Badge variant={st.status === "approved" ? "success" : st.status === "declined" ? "danger" : "outline"}>
                        {st.status === "pending" ? (i === data.current_step ? "Waiting" : "Not started") : st.status === "approved" ? "Approved" : "Declined"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {st.min_approvals > 1 ? `${st.min_approvals} of ` : st.approver_names.length > 1 ? "Any 1 of " : ""}
                      {st.approver_names.join(", ")}
                    </p>
                    {st.actions.map((a) => (
                      <p key={a.user_id} className="mt-1 text-xs">
                        <span className="font-medium">{a.name}</span> {a.action === "approve" ? "approved" : "declined"} {relativeTime(a.at)}
                        {a.comment && <span className="text-muted-foreground">: “{a.comment}”</span>}
                      </p>
                    ))}
                  </li>
                ))}
              </ol>
            </div>
          )}
          <div className="flex flex-wrap gap-2 text-xs">
            {(Object.keys(VOTE_LABELS) as VoteKey[]).map((k) => (
              <Badge key={k} variant={VOTE_TONE[k]}>
                {VOTE_LABELS[k]}: {data.tally[k] ?? 0}
              </Badge>
            ))}
          </div>
          {data.votes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No votes yet.</p>
          ) : (
            <ul className="space-y-2">
              {data.votes.map((v) => (
                <li key={v.user_id} className="rounded-md border px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{v.name}</span>
                    <Badge variant={VOTE_TONE[v.vote]}>{VOTE_LABELS[v.vote]}</Badge>
                  </div>
                  {v.comment && <p className="mt-1 text-muted-foreground">{v.comment}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-4">
          {data.can_approve && data.chain && data.current_step !== null && (
            <div className="space-y-2 rounded-md border border-accent p-3">
              <div className="text-sm font-medium">Your approval is needed: {data.chain[data.current_step].name}</div>
              <Textarea value={approvalComment} onChange={(e) => setApprovalComment(e.target.value)} rows={2} maxLength={2000} placeholder="Comment (optional)" aria-label="Approval comment" />
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="outline" loading={approve.isPending && approve.variables === "decline"} onClick={() => confirm("Decline? This stops the approval chain.") && approve.mutate("decline")}>
                  Decline
                </Button>
                <Button size="sm" loading={approve.isPending && approve.variables === "approve"} onClick={() => approve.mutate("approve")}>
                  Approve
                </Button>
              </div>
            </div>
          )}
          {data.open && hasRole("analyst") && (
            <form
              className="space-y-2 rounded-md border p-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (myVote) cast.mutate();
              }}
            >
              <div className="text-sm font-medium">{data.my_vote ? "Change your vote" : "Your vote"}</div>
              <Select value={myVote} onChange={(e) => setVote(e.target.value as VoteKey)} aria-label="Your vote">
                <option value="" disabled>
                  Choose…
                </option>
                {(Object.keys(VOTE_LABELS) as VoteKey[]).map((k) => (
                  <option key={k} value={k}>
                    {VOTE_LABELS[k]}
                  </option>
                ))}
              </Select>
              <Textarea value={myComment} onChange={(e) => setComment(e.target.value)} rows={2} maxLength={2000} placeholder="Reasoning or conditions (optional)" aria-label="Vote comment" />
              <div className="flex justify-end">
                <Button size="sm" type="submit" disabled={!myVote} loading={cast.isPending}>
                  {data.my_vote ? "Update vote" : "Cast vote"}
                </Button>
              </div>
            </form>
          )}
          {data.open && hasRole("admin") && (
            <form
              className="space-y-2 rounded-md border p-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (confirm("Record the committee's decision? Voting closes for this round.")) decide.mutate();
              }}
            >
              <div className="text-sm font-medium">Record the decision</div>
              {data.chain_status === "pending" && <p className="text-xs text-muted-foreground">An approval can be recorded once every step of the chain has approved.</p>}
              <Select value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)} aria-label="Decision">
                <option value="approved">Approved</option>
                <option value="conditional">Approved with conditions</option>
                <option value="declined">Declined</option>
              </Select>
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={4000} placeholder="Conditions or rationale (included in the IC memo)" aria-label="Decision notes" />
              {decision === "declined" && (
                <Label className="flex items-center gap-2 text-xs font-normal">
                  <input type="checkbox" checked={pass} onChange={(e) => setPass(e.target.checked)} /> Also move the deal to Passed
                </Label>
              )}
              <div className="flex justify-end">
                <Button size="sm" type="submit" loading={decide.isPending}>
                  Record decision
                </Button>
              </div>
            </form>
          )}
          {!data.open && data.stage === "ic" && (
            <p className="text-xs text-muted-foreground">To start a new round, move the deal to another stage and back to Investment Committee.</p>
          )}
        </div>
      </div>
    </SectionCard>
  );
}
