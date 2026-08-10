import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

/**
 * A drawer that hangs off the right edge behind a permanently visible tab.
 *
 * The tab is a real button rather than a hover target: a panel you can only
 * reach with a mouse is a panel keyboard users do not have. Escape closes it
 * and returns focus to the tab, which is the one interaction people try
 * without being told.
 *
 * WHY THIS IS PORTALLED TO <body>
 * ------------------------------
 * `position: fixed` is only relative to the viewport while no ancestor has a
 * transform, filter, backdrop-filter, perspective or containment — any of those
 * makes that ancestor the containing block instead. `AppLayout`'s <main> runs
 * `animate-fade-rise`, whose keyframes animate `transform`, so the scrim's
 * `inset-0` resolved against main's padded, max-w-content box: it stopped short
 * of the top and bottom of the window and inset from the sides.
 *
 * Rendering into <body> removes the ancestor entirely, so no future transform
 * anywhere up the tree can trap this again. That is worth more than fixing the
 * one animation currently at fault — this is the second time a transform in the
 * shell has broken a fixed overlay here.
 */
export function SidePanel({
  label,
  title,
  description,
  open,
  onOpenChange,
  children,
}: {
  /** Short text on the tab itself. Set vertically, so keep it to a few words. */
  label: string;
  title: string;
  description?: string;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  children: ReactNode;
}) {
  const tabRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChange(false);
    }

    // Moving focus into the panel means the next Tab lands inside it rather
    // than continuing through the page behind the scrim.
    panelRef.current?.focus();
    document.addEventListener("keydown", onKeyDown);

    const previousOverflow = document.body.style.overflow;
    const previousPadding = document.body.style.paddingRight;

    // Locking the background scroll removes the scrollbar, which widens the
    // viewport by its width and shoves the whole centered layout sideways —
    // the "clunk" when the drawer opens. Replacing the lost gutter with padding
    // keeps the page still.
    //
    // The delta is measured across the change rather than assumed: `scrollbar-
    // gutter: stable`, an overlay scrollbar, or a page that never scrolled all
    // give zero, and padding those by a hardcoded 15px would introduce the very
    // shift this is here to prevent.
    //
    // Scrollbars are currently hidden site-wide (see styles/index.css), so the
    // delta is zero and this adds nothing. That is the measurement doing its
    // job, not dead code — it is what keeps the drawer correct if the bars are
    // ever turned back on, and a hardcoded value would be actively wrong today.
    const widthBefore = document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    const gutter = document.documentElement.clientWidth - widthBefore;
    if (gutter > 0) {
      document.body.style.paddingRight = `${gutter}px`;
    }

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPadding;
    };
  }, [open, onOpenChange]);

  // Returning focus to the tab on close keeps the keyboard position stable;
  // without it focus falls back to <body> and the next Tab starts from the top.
  useEffect(() => {
    if (!open) tabRef.current?.focus({ preventScroll: true });
  }, [open]);

  return createPortal(
    <>
      <button
        ref={tabRef}
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-controls="side-panel"
        className={cn(
          "fixed right-0 top-1/2 z-30 -translate-y-1/2",
          "flex items-center gap-2 rounded-l-card border border-r-0 border-line",
          "bg-surface py-5 pl-3 pr-2.5 text-body-sm font-semibold text-ink-muted shadow-raised",
          "transition-all duration-state ease-enter hover:pr-4 hover:text-brand",
          open && "pointer-events-none opacity-0",
        )}
      >
        <span style={{ writingMode: "vertical-rl" }} className="rotate-180">
          {label}
        </span>
      </button>

      {/* The scrim is a sibling rather than a wrapper so the panel is not
          nested inside a fading element; opacity on an ancestor would take the
          panel's own shadow down with it. */}
      <div
        onClick={() => onOpenChange(false)}
        aria-hidden="true"
        className={cn(
          "fixed inset-0 z-30 bg-ink/25 transition-opacity ease-enter",
          open ? "opacity-100 duration-enter" : "pointer-events-none opacity-0 duration-exit",
        )}
      />

      <div
        id="side-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          "fixed inset-y-0 right-0 z-40 flex w-full max-w-[34rem] flex-col",
          "border-l border-line bg-surface shadow-lifted outline-none",
          "transition-transform ease-enter",
          open ? "translate-x-0 duration-enter" : "translate-x-full duration-exit",
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-4 py-4 sm:px-6 sm:py-5">
          <div>
            <h2 className="text-subtitle font-bold text-ink">{title}</h2>
            {description && <p className="mt-1 text-body-sm text-ink-muted">{description}</p>}
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="-mr-1 grid h-9 w-9 shrink-0 place-items-center rounded-control text-ink-muted transition-colors duration-state ease-enter hover:bg-surface-hero hover:text-brand"
          >
            <span aria-hidden="true" className="text-lg leading-none">
              &times;
            </span>
            <span className="sr-only">Close</span>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">{children}</div>
      </div>
    </>,
    document.body,
  );
}
