import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

/** The accent stripe Sprints puts across the top of a stat card. Carries
 *  categorical meaning without tinting the whole surface. */
type Accent = "none" | "brand" | "teal" | "amber";

const ACCENTS: Record<Accent, string> = {
  none: "",
  brand: "before:bg-brand",
  teal: "before:bg-teal",
  amber: "before:bg-amber",
};

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  accent?: Accent;
  children: ReactNode;
}

export function Card({ accent = "none", className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-card bg-surface shadow-raised",
        "border border-line/70",
        accent !== "none" &&
          "before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:content-['']",
        ACCENTS[accent],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardBody({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("p-5 sm:p-6", className)} {...rest}>
      {children}
    </div>
  );
}
