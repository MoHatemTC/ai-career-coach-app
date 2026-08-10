import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "teal";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  // Blue is identity and interaction, never status. See the tokens note.
  primary: "bg-brand text-white hover:bg-brand-deep shadow-raised",
  secondary: "bg-surface text-ink border border-line hover:border-brand hover:text-brand",
  ghost: "bg-transparent text-ink-muted hover:text-brand hover:bg-surface-hero",
  teal: "bg-teal text-white hover:brightness-95 shadow-raised",
};

const SIZES: Record<Size, string> = {
  sm: "h-9 px-3.5 text-body-sm",
  md: "h-11 px-5 text-body",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      // A loading button stays disabled so a slow pipeline call cannot be
      // fired twice by an impatient second click.
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-control font-semibold",
        "transition-colors duration-state ease-enter",
        "disabled:cursor-not-allowed disabled:opacity-55",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}
