import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

import { Button } from "./Button";

/** Every data-bearing component needs all three of these. Gate 2 checks it. */

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block h-5 w-5 animate-spin rounded-full border-2 border-brand/25 border-t-brand",
        className,
      )}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-control bg-line/70", className)} aria-hidden="true" />;
}

export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-card border border-line bg-surface p-6 text-ink-muted">
      <Spinner />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-line bg-surface/60 p-8 text-center">
      <p className="font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-prose text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

/**
 * Error copy states what broke and what to do, in the interface's voice.
 *
 * The backend's own words are shown rather than a generic apology: the API
 * puts the real cause in `detail`, and that sentence is usually the whole
 * diagnosis (a missing key, an unseeded collection, a model the gateway will
 * not serve).
 */
export function ErrorState({
  title = "That did not work",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-card border border-amber/40 bg-amber/[0.06] p-5" role="alert">
      <p className="font-semibold text-ink">{title}</p>
      <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-ink-muted">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
