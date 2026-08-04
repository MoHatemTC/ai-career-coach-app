import { useState } from "react";

import { cn } from "@/lib/cn";

/**
 * The Sprints logo.
 *
 * Deliberately loads the real asset rather than reproducing the mark in code.
 * A hand-drawn approximation of a company's logo is subtly wrong in ways that
 * are obvious to the people who own it, and worse than an honest placeholder.
 *
 * Drop the real file at `public/sprints_logo.svg`. Until it exists, this falls
 * back to the wordmark set in type, which reads as a placeholder rather than
 * pretending to be the mark.
 */
export function Logo({
  className,
  onDark = false,
}: {
  className?: string;
  /** The supplied wordmark is black, so it needs a light variant on
   *  --brand-deep sections. */
  onDark?: boolean;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <span
        className={cn(
          "text-lg font-extrabold tracking-tight",
          onDark ? "text-white" : "text-ink",
          className,
        )}
      >
        Sprints
      </span>
    );
  }

  return (
    <img
      src="/sprints_logo.svg"
      alt="Sprints"
      onError={() => setFailed(true)}
      className={cn("h-8 w-auto", onDark && "brightness-0 invert", className)}
    />
  );
}
