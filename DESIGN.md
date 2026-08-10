---
name: Sprints Career Coach
description: A job-matching interface where every score arrives with its reasoning attached.
colors:
  signal-blue: "#1A5FEE"
  signal-blue-deep: "#3B55E6"
  signal-blue-bright: "#2AA0F2"
  mark-blue: "#004eff"
  matched-teal: "#17A79A"
  matched-teal-ink: "#0F766E"
  gap-amber: "#F5B01F"
  gap-amber-ink: "#8A6206"
  chip-fill: "#EAEDF4"
  chip-ink: "#4E639D"
  ink: "#1D1D2B"
  ink-muted: "#64647A"
  paper: "#FFFFFF"
  paper-blue: "#F4F7FE"
  paper-hero: "#E7ECFC"
  line: "#E3E8F5"
typography:
  display:
    fontFamily: "Gilroy, 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "clamp(2.75rem, 5.2vw, 4.5rem)"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Gilroy, 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "clamp(1.875rem, 2.6vw, 2.75rem)"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  subtitle:
    fontFamily: "Gilroy, 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "clamp(1.25rem, 1.5vw, 1.5rem)"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  lead:
    fontFamily: "Gilroy, 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.65
  body:
    fontFamily: "Gilroy, 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Gilroy, 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.025em"
  figure:
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace"
    fontSize: "1.25rem"
    fontWeight: 700
    fontFeature: "tabular-nums"
rounded:
  card: "16px"
  control: "8px"
  chip: "999px"
spacing:
  chip-gap: "6px"
  stack: "16px"
  card: "24px"
  gutter: "24px"
  gutter-wide: "40px"
  band: "96px"
components:
  button-primary:
    backgroundColor: "{colors.signal-blue}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.signal-blue-deep}"
    textColor: "{colors.paper}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "44px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "44px"
  button-teal:
    backgroundColor: "{colors.matched-teal}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "0 20px"
    height: "44px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "24px"
  badge-matched:
    backgroundColor: "rgba(23,167,154,0.10)"
    textColor: "{colors.matched-teal}"
    rounded: "{rounded.chip}"
    padding: "2px 10px"
  badge-gap:
    backgroundColor: "rgba(245,176,31,0.14)"
    textColor: "{colors.gap-amber-ink}"
    rounded: "{rounded.chip}"
    padding: "2px 10px"
  chip-skill:
    backgroundColor: "{colors.chip-fill}"
    textColor: "{colors.chip-ink}"
    rounded: "{rounded.chip}"
    padding: "4px 4px 4px 10px"
  badge-neutral:
    backgroundColor: "{colors.paper-blue}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.chip}"
    padding: "2px 10px"
  input-control:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
    width: "100%"
---

# Design System: Sprints Career Coach

## Overview

**Creative North Star: "The Annotated Shortlist"**

This is an interface built around a single conviction: a ranked list that does not
justify itself is broken. Every match arrives with its reasoning attached — the
strengths that earned it, the gaps that cost it, and the number that summarizes
both. The design's entire job is to make that annotation as readable as the rank
it explains, so the system reads less like a job board and more like a shortlist
someone competent has already marked up in the margin.

The register is calm and load-bearing. Surfaces are white cards on a cool blue-grey
paper, raised by soft low-contrast shadow rather than outlined by hard rules.
Nothing in the chrome competes for attention, because the content is dense and
argumentative and needs the room: a job title, a fit score, a required-skills row,
a paragraph of alignment, and four separate bullet lists can all appear inside one
card. Components stay quiet so that hierarchy inside the card does the work.

The system runs two registers off the same tokens. A **marketing register** —
wide bands, display type up to 4.5rem, generous vertical air — carries the landing
page. A **product register** — tighter rhythm, denser cards, tabular figures —
carries the app. They share every color, radius, and shadow; they differ only in
scale and spacing. The one thing the system refuses is decoration that implies a
judgment the model did not make.

**Key Characteristics:**

- Explanation is a first-class visual element, never a disclosure or a tooltip
- Blue is identity and interaction only; match quality runs teal to amber
- Raised surfaces, not ruled ones — soft shadow over hard borders
- Tabular figures everywhere a number sits in a ranked list
- Every data-bearing component ships loading, empty, and error states
- Motion is transform and opacity only, and never exceeds 300ms

## Colors

A cool, high-key palette: one confident blue carrying identity and action, a
categorical teal/amber pair carrying match quality, and a blue-tinted neutral
ramp that keeps white cards from floating on grey.

### Primary

- **Signal Blue** (`{colors.signal-blue}`): Every primary button, active nav item,
  focus ring, slider fill, and fit-score figure. The interface's one voice for
  "this is interactive" and "this is us."
- **Signal Blue Deep** (`{colors.signal-blue-deep}`): The hover state of every
  primary surface. Deeper rather than lighter, so pressing feels like committing.
- **Signal Blue Bright** (`{colors.signal-blue-bright}`): Reserved for gradient
  and illustration accents where a second blue is needed for depth.
- **Mark Blue** (`{colors.mark-blue}`): The logo only. It is a purer blue than the
  CTA, read directly out of the supplied Sprints asset. Sampling it for buttons
  would shift every interactive surface in the product.

### Secondary

- **Matched Teal** (`{colors.matched-teal}`): Skills the candidate has, strengths
  in an explanation, the confirm action on a destructive-adjacent flow. Paired
  with **Matched Teal Ink** (`{colors.matched-teal-ink}`) for text, for the same
  reason amber has one: teal on a 10% teal wash measures 2.69:1 and fails AA.
- **Gap Amber** (`{colors.gap-amber}`): Skills the candidate lacks, gaps in an
  explanation, and the error-state surface. Paired with **Gap Amber Ink**
  (`{colors.gap-amber-ink}`) for text, because amber on light amber fails contrast.

Both inks are tuned to the same measured contrast — 4.93:1 for teal against
5.02:1 for amber — rather than each being pushed as dark as it could go. The
Paired Split Rule below requires the two halves to carry equal weight, and a
matched pair where one side is visibly heavier than the other breaks that as
surely as a missing half would.

### Neutral

- **Ink** (`{colors.ink}`): All primary text and headings.
- **Ink Muted** (`{colors.ink-muted}`): Body copy inside cards, metadata, labels,
  and every explanation bullet. The majority of running text is this color.
- **Paper** (`{colors.paper}`): Card and header surfaces.
- **Paper Blue** (`{colors.paper-blue}`): The application background. Cards read as
  raised against it without needing a border.
- **Paper Hero** (`{colors.paper-hero}`): Marketing hero bands and the hover wash
  on ghost buttons and inactive nav items.
- **Line** (`{colors.line}`): Dividers, input strokes, and card hairlines — usually
  at 70% opacity so it reads as a seam rather than a rule.
- **Chip Fill** (`{colors.chip-fill}`) and **Chip Ink** (`{colors.chip-ink}`): The
  editable skill token. Both are Signal Blue pulled most of the way back to
  neutral — a parsed CV yields forty of these at once, and at full brand tint the
  form read as forty calls to action.

### Named Rules

**The Blue Is Never A Status Rule.** Blue is identity and interaction, full stop.
Match quality runs teal to amber, so no blue element may ever be readable as
"good." A blue badge means a category, never a score.

**The Paired Split Rule.** Teal and amber are categorical, not good and bad. They
appear as a pair — matched beside missing, strengths beside gaps — and both halves
get equal typographic weight. Rendering one without the other misrepresents the
analysis.

**The Empty-Not-Invented Rule.** When an explanation list is empty, its heading and
badge do not render at all. A visible heading over nothing implies the system had
an opinion it does not have.

**The Forty Chips Rule.** Style repeated elements for the count they actually
arrive in, not for one specimen. A parsed CV produces forty skill chips at once,
so any treatment that looks confident on a single chip and shouts at forty is
wrong at the only scale that ships.

## Typography

**Display Font:** Gilroy (licensed; with Plus Jakarta Sans and system-ui fallbacks)
**Body Font:** Gilroy — one family across the whole system
**Label/Mono Font:** JetBrains Mono (with ui-monospace fallbacks), figures only

**Character:** A rounded geometric sans doing everything, differentiated by weight
and tracking rather than by family. Display sizes are set at 800 weight with tight
negative tracking (-0.035em) so headlines read as a deliberate mass; body copy sits
at 400 with generous leading so a dense explanation stays readable. The monospace
appears only where digits must align.

> The stack above is wired: `@font-face` in `frontend/src/styles/index.css`
> declares Gilroy at 400/500/600/700/800, and `tailwind.config.ts` leads with it.
> **The `.woff2` files are still missing** — `frontend/public/fonts/` does not
> exist — so the app currently falls through to Plus Jakarta Sans (also absent)
> and renders in the system stack. Dropping the five files in is the only
> remaining step; see PRODUCT.md's Brand Commitments for the exact filenames.

### Hierarchy

- **Display** (800, `clamp(2.75rem, 5.2vw, 4.5rem)`, 1.02): Marketing hero
  headlines only. One per page.
- **Title** (800, `clamp(1.875rem, 2.6vw, 2.75rem)`, 1.1): Band headings on the
  landing page and page titles in the app.
- **Subtitle** (700, `clamp(1.25rem, 1.5vw, 1.5rem)`, 1.25): Section headings
  inside a page.
- **Lead** (400, `1.125rem`, 1.65): The paragraph under a hero or band heading.
  Capped at 68ch.
- **Body** (400, `0.9375rem`, 1.6): Controls, buttons, and card copy. Explanation
  bullets drop to `0.875rem` at the same leading.
- **Label** (600, `0.75rem`, uppercase, `0.025em`): Field labels, the "Required
  skills" eyebrow, and the "fit" caption under a score.
- **Figure** (700, monospace, tabular): Fit scores, dates, and slider values.

### Named Rules

**The Tabular Figures Rule.** Any number that appears in a ranked or repeating
context — a fit score, a rank index, a date, a threshold — carries the `.tabular`
treatment (monospace, `font-variant-numeric: tabular-nums`). Proportional figures
misalign down a column and make a ranked list look broken.

**The Measure Rule.** Prose is capped at 68ch by its own measure, never by the
width of its container. The shell is free to run to 1560px around it.

## Layout

The shell is a centered column with a **1560px** maximum, gutters of 24px rising to
40px at `lg`. The cap is deliberately wide: an app capped at 1200px leaves a third
of a 1600px display as dead margin and reads as a phone layout stretched onto a
desktop. Width is spent on content, and only prose is constrained, by measure.

A **sticky header** (`z-20`) carries the logo, a horizontally scrolling nav, and the
backend status indicator on a 90%-opacity paper surface with a backdrop blur, over a
hairline bottom border.

The **product register** uses `py-10` page padding and a 16px vertical stack inside
cards. Upload runs two columns from `lg` so the form is not pushed below the fold;
matches go two-up from `xl`. The **marketing register** is built from full-width
bands alternating paper, hero, and sunken backgrounds, each separated by a hairline
and padded `py-24` to `py-28` — one idea per band, never a uniform grid of identical
cards.

Breakpoints follow Tailwind defaults; the ones this system actually uses are `sm`
(640px) for card padding, `lg` (1024px) for gutters and the upload split, and `xl`
(1280px) for the matches grid.

## Elevation & Depth

Tonal layering first, shadow second, borders last. Depth comes from three stacked
surface values — sunken page, paper card, hero band — and the shadows are soft and
low-contrast on top of that. Cards carry a hairline border at 70% opacity as a seam
rather than an outline. Nothing in the system uses a hard 1px rule to separate two
surfaces of the same tone.

### Shadow Vocabulary

- **Raised** (`box-shadow: 0 1px 2px rgba(29,29,43,0.04), 0 8px 24px rgba(29,29,43,0.06)`):
  The resting state of every card and primary button. Ambient, not structural.
- **Lifted** (`box-shadow: 0 2px 4px rgba(29,29,43,0.06), 0 16px 40px rgba(29,29,43,0.10)`):
  Hover only, and only on marketing calls to action. The product register does not
  lift on hover; it changes color instead.

### Named Rules

**The Raised, Not Ruled Rule.** Surfaces are separated by tone and shadow, not by
lines. Reach for a border only where a genuine seam exists — a card edge, an input
stroke, a divider inside a card between two content classes.

## Shapes

One radius for cards (16px), one for controls and inputs (8px), and a full pill for
chips (999px). The ratio is deliberate: controls read as half a card, which keeps a
button inside a card from looking like a card inside a card.

The recurring silhouette is the **accent stripe** — a 3px full-bleed bar across the
top of a card, in brand, teal, or amber. It carries categorical meaning without
tinting the whole surface, and it is the system's one piece of pure decoration.
Empty states invert the form language with a dashed border on a 60%-opacity paper
surface, which reads as a slot waiting to be filled rather than a card that failed.

## Components

### Buttons

- **Shape:** Gently rounded (8px), 44px tall at default size, 36px at small.
  Semibold label, 8px gap to an optional icon or spinner.
- **Primary:** Signal Blue on white text with the raised shadow.
- **Hover / Focus:** Background deepens to Signal Blue Deep over 150ms
  (`cubic-bezier(0.16, 1, 0.3, 1)`). Focus shows a 2px Signal Blue ring, offset 2px
  from a paper background, via `:focus-visible` only.
- **Secondary:** Paper surface, ink text, hairline border; on hover the border and
  the label both go Signal Blue.
- **Ghost:** Transparent with muted ink; on hover the label goes Signal Blue over a
  Paper Hero wash.
- **Teal:** Matched Teal on white, for the affirmative action in a paired choice.
- **Loading:** A spinning ring in `currentColor` replaces nothing — it is prepended,
  and the button disables itself so a slow pipeline call cannot be fired twice.
- **Disabled:** 55% opacity, `not-allowed` cursor.

### Chips

- **Style:** Pill (999px), 12px semibold, 1px border, tinted background at 8–14%
  of the tone's own hue.
- **State:** Four tones — neutral for factual metadata (required skills, job type),
  brand for categorical labels, teal for matched, amber for gaps. Amber's label uses
  Gap Amber Ink, not the amber itself, for contrast.
- **Skill token (editable):** The chips in the profile editor are a distinct
  species from read-only badges: they arrive in bulk from the parser and each
  carries a remove control. They use Chip Fill and Chip Ink at 500 weight, and
  their remove button rests at 40% ink, going Signal Blue on white at hover. The
  count is the design constraint — whatever styling they get must survive forty
  of them stacked in one field.

### Cards / Containers

- **Corner Style:** 16px, with `overflow-hidden` so the accent stripe clips to it.
- **Background:** Paper on a Paper Blue page.
- **Shadow Strategy:** Raised at rest; see Elevation.
- **Border:** Hairline Line at 70% opacity.
- **Internal Padding:** 20px, rising to 24px at `sm`.
- **Accent:** Optional 3px top stripe in brand, teal, or amber.

### Inputs / Fields

- **Style:** Full-width, 8px radius, hairline Line stroke on paper, 10px/14px
  padding, placeholder at 60% muted ink.
- **Label:** Medium-weight (500) 14px ink above the control, with an optional 12px
  muted hint line beneath it — the hint sits with the label, not under the input.
  Semibold labels stacked down a long form read as a column of headings.
- **Focus:** Border goes solid Signal Blue; the global focus ring handles the rest.
  Hover brings the border to 40% Signal Blue as a lighter pre-signal.
- **Slider:** Accent-colored track with its current value shown as a tabular
  Signal Blue figure aligned to the label's baseline.

### Navigation

- **Style:** Horizontal pill links, 14px semibold, 8px radius, inside a sticky
  translucent header.
- **States:** Active is Signal Blue on an 8% blue wash; inactive is muted ink going
  Signal Blue on a Paper Hero wash at hover. Transitions run 150ms.
- **Mobile:** The nav row scrolls horizontally rather than collapsing to a menu —
  five destinations do not justify a drawer.

### Match Card (signature)

The system's defining component and the clearest expression of the North Star. A
brand-accented card holding, in order: rank index and job title with company
beneath; the fit score as a large tabular figure with a "fit" label, right-aligned
and never recomputed in the UI; a metadata row; a trimmed description at 400
characters; a neutral chip row of required skills; the alignment summary as rendered
markdown; and then, above a hairline divider, the four explanation lists — Strengths
in teal, Gaps in amber, Recommendations and Next steps in brand. Each list renders
its badge as a heading and suppresses itself entirely when empty. The card enters
with `fade-rise` (8px translate, 250ms).

### State Trio

Every data-bearing surface ships all three:

- **Loading:** A bordered card with a Signal Blue spinner and a label that names the
  work in progress. Matching is four sequential model calls; a bare spinner is not
  acceptable there.
- **Empty:** Dashed-border card, centered, with a bold title, an optional measured
  explanation, and an optional action.
- **Error:** An amber-bordered card on a 6% amber wash with `role="alert"`, carrying
  the backend's own `detail` sentence verbatim and an optional retry button.

## Do's and Don'ts

### Do:

- **Do** use Signal Blue for identity and interaction only, and teal/amber for
  match quality — the Blue Is Never A Status Rule.
- **Do** render matched and missing as a paired split with equal weight.
- **Do** apply `.tabular` to every figure that sits in a ranked or repeating context.
- **Do** separate surfaces with tone and the raised shadow before reaching for a
  border.
- **Do** give every data-bearing component a loading, empty, and error state, and
  make the loading label name the actual work.
- **Do** show the backend's own error sentence; it is usually the whole diagnosis.
- **Do** keep transitions on transform and opacity, at 150ms for state, 250ms for
  enter, 200ms for exit.
- **Do** cap prose at 68ch by measure while letting the shell run to 1560px.

### Don't:

- **Don't** let any blue element read as a quality score, and don't tint a whole
  card surface to signal status — that is the accent stripe's job.
- **Don't** render an explanation heading over an empty list. Suppress the block.
- **Don't** recompute or re-round the fit score in the interface; pass through what
  the re-ranker returned.
- **Don't** animate height, width, or any layout-triggering property, and don't run
  a transition past 300ms — past that it reads as lag, not polish.
- **Don't** use `:focus` where `:focus-visible` belongs; the ring must not appear on
  mouse clicks.
- **Don't** shorten motion for `prefers-reduced-motion` — collapse it to instant.
  A shorter animation is still motion to someone who asked for none.
- **Don't** redraw, retrace, or recolor the Sprints mark in code; use the asset.
- **Don't** apply a blanket inversion filter to the logo on dark surfaces — it
  flattens the Mark Blue glyph along with the black wordmark.
