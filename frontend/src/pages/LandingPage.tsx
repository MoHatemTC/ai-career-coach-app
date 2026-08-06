import { Link } from "react-router-dom";

import { Logo } from "@/components/brand/Logo";
import { JobPoolVisual } from "@/components/landing/JobPoolVisual";

/**
 * The public entry point.
 *
 * Marketing register: wide, generous, one idea per band. The product register
 * at /app/* is deliberately denser, because ranked lists are the product and
 * whitespace there costs the user scrolling.
 *
 * The CTA goes to /app/upload rather than a dashboard: landing a first-time
 * visitor on an empty dashboard is an empty state pretending to be a product.
 *
 * Setup instructions deliberately live in README.md, not here. A landing page
 * carrying pip commands reads as a scaffold rather than a product.
 */

const STAGES = [
  {
    title: "Ingest",
    body: "Postings pulled from multiple boards, normalised to one schema and deduplicated on a deterministic id, so the same job never lands twice.",
  },
  {
    title: "Embed",
    body: "Each posting becomes a vector. Embeddings whose posting is gone are pruned on every run, so the index and the database cannot drift apart.",
  },
  {
    title: "Retrieve",
    body: "Your profile is embedded the same way and used to pull the closest postings, across the whole collection rather than a filtered slice.",
  },
  {
    title: "Re-rank",
    body: "A language model re-reads that shortlist and reorders it on reasoning a vector cannot capture: seniority fit, whether one skill substitutes for another.",
  },
  {
    title: "Explain",
    body: "Every job returned carries matched skills and real gaps, scored against the requirements actually written in the posting.",
  },
];

export function LandingPage() {
  return (
    <div className="min-h-dvh animate-fade-in bg-surface">
      {/* `shell-rule` draws the bottom hairline in over the first 72px of
          scroll: at the very top the header is sitting on the hero rather than
          over it, so there are not yet two surfaces for a seam to separate.
          Static default keeps the rule, so nothing depends on the effect. */}
      <header className="shell-rule sticky top-0 z-20 border-b border-line/60 bg-surface/80 backdrop-blur-md">
        {/* Full-bleed wash in the hero's own tone, sitting over the header's
            white surface. At rest it hides that white strip so the mark reads
            as part of the hero; it fades out over the first 96px of scroll and
            the real bar arrives underneath. The bottom hairline is already
            handled by `shell-rule`, which holds it transparent to 72px. */}
        <div className="relative">
          <div
            aria-hidden="true"
            className="bar-wash pointer-events-none absolute inset-0 bg-surface-hero opacity-0"
          />
          {/* A three-track grid rather than flex: collapsing the first track
              from 1fr to 0fr walks the mark from centre to left without any
              viewport arithmetic, and it scrubs because fr units interpolate.
              Base state is the SCROLLED state (0fr), so a browser with no
              scroll timelines gets an ordinary left-aligned header instead of
              a logo stranded in the middle. */}
          <div className="bar-grid relative mx-auto grid max-w-content grid-cols-[0fr_auto_1fr] items-center px-6 py-4 lg:px-10">
            <span aria-hidden="true" />
            <Logo />
            <Link
              to="/app/upload"
              className="bar-cta inline-flex h-10 items-center justify-self-end rounded-control bg-brand px-5 text-body-sm font-semibold text-white transition-all duration-state ease-enter hover:bg-brand-deep hover:shadow-lifted"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* Hero. Asymmetric on purpose: a 50/50 split with a card on the right is
          the layout every template ships with.

          Sized to a full viewport minus the 4.5rem header, and centred, so the
          headline is the only thing on screen at rest. `min-h` rather than `h`:
          a short landscape window or a stacked mobile column still grows and
          scrolls instead of clipping the CTA off the bottom.

          `overflow-clip` for the same reason as the pipeline band below —
          `hidden` would make this a scroll container and trap any view()
          timeline inside it. */}
      <section className="relative flex min-h-[calc(100dvh-4.5rem)] items-center overflow-clip border-b border-line/60 bg-surface-hero">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-40 -top-40 h-[36rem] w-[36rem] rounded-full bg-brand/[0.07] blur-3xl"
        />
        <div className="relative mx-auto w-full max-w-content px-6 py-16 lg:px-10">
          <div className="grid items-center gap-16 lg:grid-cols-12">
            <div className="lg:col-span-7">
              {/* No manual <br>. A hard break is correct at exactly one
                  viewport width — the one the author had open — and ragged at
                  every other; `text-wrap: balance` in the base layer sets the
                  line lengths per width instead.

                  "and why." carries the whole product claim, so it takes the
                  emphasis. Solid brand rather than the gradient that was here:
                  a gradient makes the phrase a texture, and the phrase should
                  read as a statement. */}
              <h1 className="max-w-[19ch] text-display font-extrabold text-ink">
                Find the jobs you actually fit,{" "}
                <span className="text-brand">and why.</span>
              </h1>
              <p className="mt-7 max-w-prose text-lead text-ink-muted">
                Upload your CV once. Every match comes back ranked, with the
                skills you have, the ones you are missing, and what to do about
                them, drawn from the requirements in the posting itself.
              </p>
              <div className="mt-10 flex flex-wrap items-center gap-4">
                <Link
                  to="/app/upload"
                  className="inline-flex h-13 items-center rounded-control bg-brand px-7 text-body font-semibold text-white shadow-raised transition-all duration-state ease-enter hover:bg-brand-deep hover:shadow-lifted"
                  style={{ height: "3.25rem" }}
                >
                  Upload your CV
                </Link>
                <a
                  href="#pipeline"
                  className="text-body font-semibold text-ink-muted underline-offset-4 transition-colors duration-state hover:text-brand hover:underline"
                >
                  See how it works
                </a>
              </div>
            </div>

            {/* The signature, and the page's only evidence: a live count of
                what this instance has actually ingested. It replaced a radar of
                invented candidate scores — a hero that asserts the product
                works is worth less than one that shows the pipeline's real
                output, and it avoids the big-number-and-a-gradient hero every
                AI-assisted landing page converges on. */}
            <div className="lg:col-span-5">

              {/* Sized to the illustration, not to the column. `max-w-md` and
                  the tighter padding stop the card stretching to fill five of
                  twelve columns, which made a supporting visual outweigh the
                  headline it supports.

                  Two corrections for how loudly it sat on the unscrolled hero:

                  White at 80% over the lavender band resolved to #FAFBFE — a
                  near-white slab on a tinted ground, and the brightest object
                  in the first viewport. At 60% it resolves to #F5F7FE, which
                  is `surface-sunken` to within a rounding step, so the card now
                  sits on a tone the palette already contains instead of one
                  invented by an alpha value.

                  And `shadow-lifted` was drift: DESIGN.md reserves Lifted for
                  hover, on marketing calls to action. This card is neither, and
                  it was the only place in the page using it at rest. `raised`
                  is the resting elevation the system actually specifies. */}
              <div className="mx-auto w-full max-w-md rounded-card border border-line/70 bg-surface/60 p-5 shadow-raised backdrop-blur-sm sm:p-6">
                <JobPoolVisual />
              </div>

            </div>
          </div>
        </div>
      </section>

      {/* Value, as prose rather than three identical cards. */}

      {/* Was three columns of ~28 words inside 192px of padding — a whole
          screen for three claims the hero has already made and the pipeline
          band below is about to make properly.

          It now spends horizontal space, which the 1560px shell has spare,
          instead of vertical space, which the reader pays for: the heading
          holds a column of its own and the claims sit beside it, each cut to
          roughly a third of its former length. The concrete detail survived
          the cut because that is the part carrying information; the
          restatement did not.

          4.375rem is the band height chosen on the slider (1.25x the 3.5rem
          base), kept exactly rather than rounded onto the spacing scale. */}
      <section className="mx-auto max-w-content px-6 py-[4.375rem] lg:px-10">
        <div className="grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,22rem)_1fr]">
          <h2 className="text-subtitle font-bold text-ink">
            What it does that a job board does not.
          </h2>
          <dl className="grid gap-x-10 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Reads your actual CV", "PDF or DOCX in, structured profile out."],
              ["Explains the ranking", "Strengths, gaps and next steps, never a bare score."],
              ["Keeps finding new work", "Fresh postings each run, so the pool grows."],
            ].map(([term, detail]) => (
              <div key={term}>
                <dt className="text-body-sm font-semibold text-ink">{term}</dt>
                <dd className="mt-1 text-body-sm text-ink-muted">{detail}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Pipeline, as a horizontal progression rather than a card grid. */}
      <section id="pipeline" className="border-y border-line/60 bg-surface-sunken">
        <div className="mx-auto max-w-content px-6 py-24 lg:px-10">
          <h2 className="max-w-prose text-title font-extrabold text-ink">
            Five stages between a CV and a shortlist you can trust.
          </h2>

          {/* Five across only once there is width for it. At `md` this was
              five 143px columns, which after padding left each caption about
              twelve characters per line — narrow enough that "deduplicated"
              did not fit on one. The sequence still reads in order when it
              wraps to two or three rows. */}
          {/* Every class below renders its FINISHED state by default. The
              scroll choreography in index.css only exists inside @supports and
              only when reduced motion is not requested, so an unsupporting
              browser gets this band complete rather than blank. */}
          {/* `overflow-clip`, NOT `overflow-hidden`. Hidden creates a scroll
              container, and `animation-timeline: view()` resolves against the
              nearest ancestor scroll container rather than the document — so
              the stages were measuring their visibility against this <ol>,
              inside which they are permanently in view and never move. The
              timeline had no progress to report and nothing animated. Clip
              clips the same rounded corners without becoming a scroller. */}
          <ol className="mt-14 grid gap-px overflow-clip rounded-card border border-line/70 bg-line/70 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {STAGES.map((stage, index) => (
              <li key={stage.title} className="stage relative bg-surface p-6">
                {/* The rail the pipeline draws along. 2px so it reads as a
                    track being filled rather than a border being decorated. */}
                <span
                  aria-hidden="true"
                  className="stage-rail absolute inset-x-0 top-0 h-0.5 bg-brand"
                />
                {/* The sequence is the information here — a CV reaches a
                    shortlist through these five in this order — so the numbers
                    earn their place rather than decorating the band. */}
                <span className="stage-num tabular text-label font-bold text-brand">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="stage-body">
                  <h3 className="mt-2 text-heading-sm font-bold text-ink">{stage.title}</h3>
                  {/* `body-sm`, and deliberately the smallest prose on the page:
                      five columns give each of these a ~38ch measure, and narrow
                      lines want smaller type, not the same type set narrower. */}
                  <p className="mt-2.5 text-body-sm text-ink-muted">{stage.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Close */}
      <section className="mx-auto max-w-content px-6 py-28 text-center lg:px-10">
        <h2 className="mx-auto max-w-prose text-title font-extrabold text-ink">
          Stop guessing which roles are worth the application.
        </h2>
        <Link
          to="/app/upload"
          className="mt-10 inline-flex items-center rounded-control bg-brand px-8 text-body font-semibold text-white shadow-raised transition-all duration-state ease-enter hover:bg-brand-deep hover:shadow-lifted"
          style={{ height: "3.25rem" }}
        >
          Upload your CV
        </Link>
      </section>

      <footer className="border-t border-line/60">
        <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-4 px-6 py-10 lg:px-10">
          <Logo className="h-6" />
          <p className="text-body-sm text-ink-muted">Sprints Career Coach</p>
        </div>
      </footer>
    </div>
  );
}
