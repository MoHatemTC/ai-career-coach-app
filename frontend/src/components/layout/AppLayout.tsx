import { NavLink, Outlet, useLocation } from "react-router-dom";

import { Logo } from "@/components/brand/Logo";
import { cn } from "@/lib/cn";

import { BackendStatus } from "./BackendStatus";

const NAV = [
  // The conversation is the Upload screen now, so it has no separate
  // destination. /app/chat still resolves, but it redirects.
  { to: "/app/upload", label: "Coach" },
  { to: "/app/matches", label: "Matches" },
  { to: "/app/settings", label: "Notifications" },
  { to: "/app/ingestion", label: "Ingestion" },
];

export function AppLayout() {
  const location = useLocation();

  return (
    // The shell fades in once, on arrival from the landing page. Keying the
    // main element on the path re-runs the entrance per route without taking
    // the header with it, which would read as a flicker rather than a
    // transition. Both collapse to instant under prefers-reduced-motion.
    <div className="min-h-dvh animate-fade-in bg-surface-sunken">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-content items-center gap-4 px-4 py-2.5 sm:gap-8 sm:px-6 sm:py-3 lg:px-10">
          <NavLink to="/" className="shrink-0" aria-label="Sprints home">
            <Logo />
          </NavLink>

          <nav className="flex flex-1 gap-1 overflow-x-auto" aria-label="Product">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "whitespace-nowrap rounded-control px-3 py-2 text-body-sm font-semibold",
                    "transition-colors duration-state ease-enter",
                    isActive
                      ? "bg-brand/[0.08] text-brand"
                      : "text-ink-muted hover:bg-surface-hero hover:text-brand",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <BackendStatus />
        </div>
      </header>

      <main
        key={location.pathname}
        className="mx-auto max-w-content animate-fade-rise px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10"
      >
        <Outlet />
      </main>
    </div>
  );
}
