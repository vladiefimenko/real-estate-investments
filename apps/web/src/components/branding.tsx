"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/common";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api, rawFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export interface Branding {
  brand_name: string | null;
  accent_color: string | null;
  report_footer: string | null;
  logo_version: number | null;
  has_logo: boolean;
}

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Black or white text, whichever reads better on the color (WCAG relative luminance). */
export function contrastText(hex: string) {
  const lin = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  return lum > 0.4 ? "#1a1404" : "#ffffff";
}

export function useBranding() {
  const org = useOrgKey();
  const { org: membership } = useAuth();
  return useQuery({
    queryKey: [org, "branding"],
    queryFn: () => api<Branding>("/api/org/branding"),
    enabled: !!membership,
    staleTime: 5 * 60_000,
  });
}

/** The logo fetched with the session's credentials, as a blob URL. */
function useLogoUrl(b: Branding | undefined) {
  const org = useOrgKey();
  const q = useQuery({
    queryKey: [org, "branding-logo", b?.logo_version],
    queryFn: async () => {
      const r = await rawFetch("/api/org/branding/logo");
      if (!r.ok) return null;
      return URL.createObjectURL(await r.blob());
    },
    enabled: !!b?.has_logo,
    staleTime: Infinity,
  });
  const url = b?.has_logo ? (q.data ?? null) : null;
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  return url;
}

/** Applies the workspace's brand color to the app's accent and focus ring. Renders nothing. */
export function BrandStyle() {
  const { data } = useBranding();
  const color = data?.accent_color;
  useEffect(() => {
    const root = document.documentElement.style;
    if (!color || !HEX.test(color)) return;
    root.setProperty("--accent", color);
    root.setProperty("--ring", color);
    root.setProperty("--accent-foreground", contrastText(color));
    return () => {
      root.removeProperty("--accent");
      root.removeProperty("--ring");
      root.removeProperty("--accent-foreground");
    };
  }, [color]);
  return null;
}

/** Sidebar header: the workspace's logo and name when set, otherwise the Axiom logo. */
export function SidebarBrand() {
  const { data } = useBranding();
  const logo = useLogoUrl(data);
  if (!data?.brand_name && !logo) return <Logo light />;
  return (
    <span className="flex min-w-0 flex-col gap-1">
      <span className="flex min-w-0 items-center gap-2.5">
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element -- a blob URL, not an optimizable asset
          <img src={logo} alt={data?.brand_name ?? "Workspace logo"} className="max-h-8 max-w-[96px] shrink-0 rounded-sm object-contain" />
        ) : null}
        {data?.brand_name && (
          <span className="truncate text-[15px] font-semibold text-white" title={data.brand_name}>{data.brand_name}</span>
        )}
      </span>
      <span className="text-[10px] uppercase tracking-[0.18em] text-white/50">Powered by Axiom</span>
    </span>
  );
}

/** Settings → Branding: firm name, brand color, report footer and logo. */
export function BrandingTab() {
  const org = useOrgKey();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin");
  const { data, isLoading, error } = useBranding();
  const logo = useLogoUrl(data);
  const [draft, setDraft] = useState<Partial<Branding> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const v = { ...data, ...draft };
  const colorOk = !v.accent_color || HEX.test(v.accent_color);

  const done = (msg: string) => (b: Branding) => {
    qc.setQueryData([org, "branding"], b);
    setDraft(null);
    toast.success(msg);
  };
  const save = useMutation({
    mutationFn: () =>
      api<Branding>("/api/org/branding", {
        method: "PUT",
        body: { brand_name: v.brand_name ?? null, accent_color: v.accent_color || null, report_footer: v.report_footer ?? null },
      }),
    onSuccess: done("Branding saved"),
    onError: (e) => toast.error(e.message),
  });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<Branding>("/api/org/branding/logo", { form });
    },
    onSuccess: (b) => {
      qc.setQueryData([org, "branding"], b);
      toast.success("Logo uploaded");
    },
    onError: (e) => toast.error(e.message),
  });
  const removeLogo = useMutation({
    mutationFn: () => api("/api/org/branding/logo", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "branding"] }),
    onError: (e) => toast.error(e.message),
  });

  if (isLoading) return <LoadingBlock rows={3} />;
  if (error) return <ErrorBlock error={error} />;
  if (!data) return null;
  const set = (k: keyof Branding, val: string) => setDraft({ ...draft, [k]: val });
  const preview = colorOk && v.accent_color ? v.accent_color : "#0B1F3A";

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_360px]">
      <Card>
        <CardHeader>
          <CardTitle>Branding</CardTitle>
          <CardDescription>
            Put your firm&apos;s name, logo and color on the app and on every PDF report: one-pager, IC memo, junior pack, summary pack and client
            presentation. Demo watermarks and the calculation disclaimer always stay on reports.
            {!canEdit && " Only admins can change branding."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (colorOk) save.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="brand-name">Firm name</Label>
              <Input id="brand-name" value={v.brand_name ?? ""} onChange={(e) => set("brand_name", e.target.value)} maxLength={60} placeholder="e.g. Summit Capital Partners" disabled={!canEdit} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="brand-color">Brand color</Label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  aria-label="Pick brand color"
                  value={colorOk && v.accent_color ? v.accent_color : "#c9a227"}
                  onChange={(e) => set("accent_color", e.target.value.toUpperCase())}
                  disabled={!canEdit}
                  className="h-9 w-12 cursor-pointer rounded-md border bg-card p-1 disabled:cursor-not-allowed"
                />
                <Input
                  id="brand-color"
                  value={v.accent_color ?? ""}
                  onChange={(e) => set("accent_color", e.target.value.trim())}
                  placeholder="#C9A227 (Axiom gold)"
                  maxLength={7}
                  className="max-w-40 font-mono"
                  aria-invalid={!colorOk}
                  disabled={!canEdit}
                />
                {v.accent_color && canEdit && (
                  <Button type="button" variant="ghost" size="sm" onClick={() => set("accent_color", "")}>
                    Use default
                  </Button>
                )}
              </div>
              {!colorOk && <p className="text-xs text-destructive">Use a hex color like #1F6FEB.</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="brand-footer">Report footer (optional)</Label>
              <Input id="brand-footer" value={v.report_footer ?? ""} onChange={(e) => set("report_footer", e.target.value)} maxLength={200} placeholder="e.g. Confidential. Prepared by Summit Capital Partners." disabled={!canEdit} />
              <p className="text-xs text-muted-foreground">Printed at the bottom of every page of your PDF reports.</p>
            </div>
            {canEdit && (
              <div className="flex justify-end gap-2">
                {draft && (
                  <Button type="button" variant="outline" onClick={() => setDraft(null)}>
                    Discard
                  </Button>
                )}
                <Button type="submit" disabled={!draft || !colorOk} loading={save.isPending}>
                  Save branding
                </Button>
              </div>
            )}
          </form>

          <div className="mt-6 border-t pt-5">
            <Label>Logo</Label>
            <p className="mb-3 mt-1 text-xs text-muted-foreground">PNG, JPEG or WebP up to 2 MB. A wide logo on a transparent background works best; it&apos;s resized to fit.</p>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-16 w-48 items-center justify-center rounded-md border bg-muted/40 p-2">
                {logo ? (
                  // eslint-disable-next-line @next/next/no-img-element -- a blob URL
                  <img src={logo} alt="Current logo" className="max-h-full max-w-full object-contain" />
                ) : (
                  <span className="text-xs text-muted-foreground">No logo</span>
                )}
              </div>
              {canEdit && (
                <>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) upload.mutate(f);
                      e.target.value = "";
                    }}
                  />
                  <Button type="button" variant="outline" size="sm" loading={upload.isPending} onClick={() => fileRef.current?.click()}>
                    <ImageUp /> {data.has_logo ? "Replace logo" : "Upload logo"}
                  </Button>
                  {data.has_logo && (
                    <Button type="button" variant="ghost" size="sm" loading={removeLogo.isPending} onClick={() => confirm("Remove the logo?") && removeLogo.mutate()}>
                      <Trash2 /> Remove
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="h-fit">
        <CardHeader>
          <CardTitle className="text-sm">Report preview</CardTitle>
          <CardDescription>How the top and bottom of your PDF pages will look.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-md border bg-white text-[10px] text-[#101828] shadow-sm">
            <div className="flex items-center justify-between gap-2 px-3 py-2" style={{ background: preview, color: v.accent_color && colorOk ? contrastText(preview) : "#fff" }}>
              <span className="flex min-w-0 items-center gap-2 font-bold">
                {logo && (
                  // eslint-disable-next-line @next/next/no-img-element -- a blob URL
                  <img src={logo} alt="" className="h-4 max-w-16 object-contain" />
                )}
                <span className="truncate">{v.brand_name || "AXIOM"}</span>
              </span>
              <span className="shrink-0 opacity-90">One-Pager</span>
            </div>
            <div className="h-0.5" style={{ background: v.accent_color && colorOk ? "#0B1F3A" : "#C9A227" }} />
            <div className="space-y-1.5 px-3 py-4">
              <div className="h-2 w-2/3 rounded bg-[#E4E7EC]" />
              <div className="h-2 w-1/2 rounded bg-[#E4E7EC]" />
              <div className="h-2 w-3/4 rounded bg-[#E4E7EC]" />
            </div>
            <div className="space-y-0.5 border-t px-3 py-2 text-[8px] text-[#667085]">
              {v.report_footer && <p className="truncate">{v.report_footer}</p>}
              <p className="truncate">Calculations by the Axiom deterministic financial engine…</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
