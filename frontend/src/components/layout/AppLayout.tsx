import { NavLink, Outlet } from "react-router-dom";

import { Logo } from "@/components/brand/Logo";
import { cn } from "@/lib/cn";

import { BackendStatus } from "./BackendStatus";

const NAV = [
  { to: "/app/upload", label: "Upload CV" },
  { to: "/app/chat", label: "Chat" },
  { to: "/app/matches", label: "Matches" },
  { to: "/app/settings", label: "Notifications" },
  { to: "/app/ingestion", label: "Ingestion" },
];

export function AppLayout() {
  return (
    <div className="min-h-dvh bg-surface-sunken">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-content items-center gap-8 px-6 py-3 lg:px-10">
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
                    "whitespace-nowrap rounded-control px-3 py-2 text-sm font-semibold",
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

      <main className="mx-auto max-w-content px-6 py-10 lg:px-10">
        <Outlet />
      </main>
    </div>
  );
}
