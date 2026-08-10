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
        //
        // Both halves carry an `ink` for text on their own tinted wash, because
        // neither hue passes contrast against a 10% tint of itself. Amber
        // already had one; teal did not, so "Strengths" rendered at 2.69:1
        // against "Gaps" at 5.02:1 — one half of a split the design system
        // insists is equal-weight was failing AA while the other passed.
        // 4.93:1 is chosen to sit level with amber's 5.02:1 rather than as dark
        // as possible: parity between the two is the point.
        teal: {
          DEFAULT: "#17A79A",
          ink: "#0F766E",
        },
        amber: {
          DEFAULT: "#F5B01F",
          // DESIGN.md already named this value; it was living as a bare
          // `text-[#8A6206]` in five places instead of as a token, so the two
          // halves of the split were asymmetric in the code as well as on
          // screen.
          ink: "#8A6206",
        },
        // The skill chip. Forty parsed skills tinted at brand/8% made every
        // token read as a call to action; these are the same hues pulled most
        // of the way back to neutral, so the chips read as parsed content and
        // blue keeps meaning "interactive".
        chip: {
          DEFAULT: "#EAEDF4",
          ink: "#4E639D",
        },
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
        // THE ROLE SCALE. Every text role in the product has a token here, and
        // nothing outside this list should appear in a className. The four
        // small roles used to be improvised per-site from raw Tailwind classes,
        // which is how one match card ended up with 15px, 14px, 12px AND 11px
        // text — two of those doing the same job.
        //
        // Steps are carried by size *and* weight together, not size alone:
        // `heading-sm` and `lead` share 18px and are told apart by weight,
        // leading and tracking, which is cheaper than inventing a size for it.

        // -- Marketing register -------------------------------------------
        display: ["clamp(2.75rem, 5.2vw, 4.5rem)", { lineHeight: "1.02", letterSpacing: "-0.035em" }],
        title: ["clamp(1.875rem, 2.6vw, 2.75rem)", { lineHeight: "1.1", letterSpacing: "-0.025em" }],
        subtitle: ["clamp(1.25rem, 1.5vw, 1.5rem)", { lineHeight: "1.25", letterSpacing: "-0.015em" }],
        lead: ["1.125rem", { lineHeight: "1.65" }],

        // -- Shared -------------------------------------------------------
        // Card and section headings: below `subtitle`, above running text.
        "heading-sm": ["1.125rem", { lineHeight: "1.3", letterSpacing: "-0.01em" }],
        // The default for running text. 15px rather than 16px because the
        // product register is dense by design; the marketing register reaches
        // for `lead` instead of scaling this up.
        body: ["0.9375rem", { lineHeight: "1.6" }],
        // Dense secondary text: explanation bullets, metadata rows, and prose
        // in a narrow column. Narrower measure earns smaller type, not larger.
        "body-sm": ["0.875rem", { lineHeight: "1.6" }],
        // The ONE micro-label size. Uppercase, tracked out.
        label: ["0.75rem", { lineHeight: "1.4", letterSpacing: "0.025em" }],
        // Fit scores. Pair with `.tabular`; see styles/index.css.
        figure: ["1.25rem", { lineHeight: "1.1", letterSpacing: "-0.01em" }],
      },
      fontFamily: {
        // Gilroy is the brand face, licensed, and now actually on disk — all
        // five weights are self-hosted from public/fonts/ as .woff2. Plus
        // Jakarta Sans stays as a shape-compatible fallback for the swap
        // window; the system stack backs that up.
        sans: [
          "Gilroy",
          "'Plus Jakarta Sans'",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        // Code only — inline `<code>` in rendered markdown, and nothing else.
        //
        // This used to lead with JetBrains Mono, which was never loaded: no
        // @font-face, no package, no CDN. So every fit score fell through to
        // whatever mono the OS had (Consolas, SF Mono, DejaVu) — making the one
        // role that must stay stable down a ranked column the one role that
        // changed per machine. Figures now use Gilroy's own `tnum` feature
        // instead, which is verified present in the shipped font files.
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
