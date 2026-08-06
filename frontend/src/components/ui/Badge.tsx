import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "brand" | "teal" | "amber";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-ink-muted border-line",
  brand: "bg-brand/[0.08] text-brand border-brand/20",
  // Teal is matched, amber is a gap. Categorical, not "good" and "bad".
  teal: "bg-teal/[0.10] text-teal-ink border-teal/25",
  amber: "bg-amber/[0.14] text-amber-ink border-amber/35",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-chip border px-2.5 py-0.5 text-label font-semibold",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
