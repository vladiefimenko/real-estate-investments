import { ApiError } from "@/lib/api";

/** A stage change refused by the workspace's stage requirements (HTTP 422 with `unmet` or `blocked`). */
export interface GateError {
  message: string;
  unmet: string[];
  blocked: Record<string, string[]>;
  canOverride: boolean;
}

export function gateError(e: unknown): GateError | null {
  if (!(e instanceof ApiError) || e.status !== 422 || !e.detail || typeof e.detail !== "object") return null;
  const d = e.detail as { message?: string; unmet?: string[]; blocked?: Record<string, string[]>; can_override?: boolean };
  if (!d.unmet && !d.blocked) return null;
  return { message: d.message ?? e.message, unmet: d.unmet ?? [], blocked: d.blocked ?? {}, canOverride: !!d.can_override };
}
