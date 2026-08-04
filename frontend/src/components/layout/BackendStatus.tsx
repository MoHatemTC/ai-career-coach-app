import { useQuery } from "@tanstack/react-query";

import { healthCheck } from "@/services/api";
import { cn } from "@/lib/cn";

/**
 * Whether the backend is reachable, checked on a slow interval.
 *
 * Streamlit showed this as a banner on every rerun. Here it is a dot in the
 * header: the information matters (every screen fails without it) but it does
 * not deserve a full-width alert when everything is fine.
 */
export function BackendStatus() {
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: healthCheck,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const ok = data?.ok ?? true;

  return (
    <div
      className="flex shrink-0 items-center gap-2"
      title={data?.message ?? "Checking the backend…"}
    >
      <span
        aria-hidden="true"
        className={cn(
          "h-2 w-2 rounded-full transition-colors duration-state",
          ok ? "bg-teal" : "bg-amber",
        )}
      />
      <span className="hidden text-xs font-medium text-ink-muted sm:inline">
        {ok ? "Backend up" : "Backend down"}
      </span>
    </div>
  );
}
