"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/overlays";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Notes {
  unread: number;
  items: { id: string; kind: string; title: string; body: string | null; link: string | null; read: boolean; created_at: string }[];
}

/** Top-bar bell: approvals waiting on you, IC outcomes and other workspace events. */
export function NotificationBell() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const router = useRouter();
  const { data } = useQuery({
    queryKey: [org, "notifications"],
    queryFn: () => api<Notes>("/api/notifications?limit=20"),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
  const read = useMutation({
    mutationFn: (ids?: string[]) => api("/api/notifications/read", { body: ids ? { ids } : {} }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "notifications"] }),
  });
  const unread = data?.unread ?? 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="relative" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
          <Bell />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between pr-2">
          <DropdownMenuLabel>Notifications</DropdownMenuLabel>
          {unread > 0 && (
            <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => read.mutate(undefined)}>
              Mark all read
            </button>
          )}
        </div>
        <DropdownMenuSeparator />
        {!data?.items.length && <p className="px-3 py-6 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>}
        <div className="max-h-96 overflow-y-auto">
          {data?.items.map((n) => (
            <DropdownMenuItem
              key={n.id}
              className="flex-col items-start gap-0.5 whitespace-normal"
              onSelect={() => {
                if (!n.read) read.mutate([n.id]);
                if (n.link) router.push(n.link);
              }}
            >
              <span className="flex w-full items-start gap-2">
                <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-accent")} aria-hidden />
                <span className={cn("flex-1 text-sm", !n.read && "font-medium")}>{n.title}</span>
              </span>
              {n.body && <span className="pl-3.5 text-xs text-muted-foreground">{n.body}</span>}
              <span className="pl-3.5 text-[11px] text-muted-foreground">{relativeTime(n.created_at)}</span>
            </DropdownMenuItem>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
