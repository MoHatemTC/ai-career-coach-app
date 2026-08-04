import type { Config } from "tailwindcss";

/**
 * Gate 1 tokens. See docs/frontend-migration-plan.md for the reasoning.
 *
 * Colours are sampled from sprints.ai screenshots and are close, not exact.
 * Replace them with the real :root custom properties when someone can read
 * them out of devtools.
 *
 * The one rule worth restating here, because it is easy to break by accident:
 * BLUE IS NEVER A STATUS. It is identity and interaction only. Match quality
 * runs teal to amber, so no blue element should ever be read as "good".
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#FFFFFF",
          sunken: "#F4F7FE",
          hero: "#E7ECFC",
        },
        ink: {
          DEFAULT: "#1D1D2B",
          muted: "#64647A",
        },
        line: "#E3E8F5",
        brand: {
          DEFAULT: "#1A5FEE",
          deep: "#3B55E6",
          bright: "#2AA0F2",
          // The logo only. Sampling this for buttons would shift every
          // interactive surface, because the mark is a purer blue than the CTA.
          mark: "#0B44F5",
        },
        // Categorical, not state. Sprints uses these for kind; we map them onto
        // the match/gap split.
        teal: "#17A79A",
        amber: "#F5B01F",
      },
      borderRadius: {
        // One radius for cards and controls, halved for inline chips.
        card: "16px",
        control: "8px",
        chip: "999px",
      },
      boxShadow: {
        // Soft and low-contrast: Sprints raises surfaces rather than drawing
        // lines around them.
        raised: "0 1px 2px rgba(29,29,43,0.04), 0 8px 24px rgba(29,29,43,0.06)",
        lifted: "0 2px 4px rgba(29,29,43,0.06), 0 16px 40px rgba(29,29,43,0.10)",
      },
      transitionDuration: {
        // The motion spec. Nothing over 300ms: past that it reads as lag
        // rather than polish.
        state: "150ms",
        enter: "250ms",
        exit: "200ms",
      },
      transitionTimingFunction: {
        enter: "cubic-bezier(0.16, 1, 0.3, 1)",
        exit: "cubic-bezier(0.4, 0, 1, 1)",
      },
      keyframes: {
        // Transform and opacity only. Animating height or width forces layout
        // on every frame, which is exactly where smooth turns janky.
        "fade-rise": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "none" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "fade-rise": "fade-rise 250ms cubic-bezier(0.16, 1, 0.3, 1) both",
        "fade-in": "fade-in 250ms cubic-bezier(0.16, 1, 0.3, 1) both",
      },
      maxWidth: {
        // 1200 left a third of a 1600px display as dead margin and made the
        // app feel like a phone layout stretched onto a desktop. The product
        // register fills the screen; only prose is capped, and it is capped by
        // measure rather than by the shell.
        content: "1560px",
        prose: "68ch",
      },
      fontSize: {
        // A real display scale. The default jumps from 36 to 48 and lands
        // everything in between at the same visual weight, which is most of
        // what reads as dated.
        display: ["clamp(2.75rem, 5.2vw, 4.5rem)", { lineHeight: "1.02", letterSpacing: "-0.035em" }],
        title: ["clamp(1.875rem, 2.6vw, 2.75rem)", { lineHeight: "1.1", letterSpacing: "-0.025em" }],
        subtitle: ["clamp(1.25rem, 1.5vw, 1.5rem)", { lineHeight: "1.25", letterSpacing: "-0.015em" }],
        lead: ["1.125rem", { lineHeight: "1.65" }],
      },
      fontFamily: {
        // Plus Jakarta Sans is a free lookalike for the rounded geometric sans
        // Sprints uses. Confirm the real family in devtools; if it is licensed
        // (Greycliff, Gilroy, Circular all look close) that is a licensing
        // conversation, not a quiet substitution.
        sans: ["'Plus Jakarta Sans'", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
