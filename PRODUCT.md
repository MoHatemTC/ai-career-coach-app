# Product

## Platform

web

## Users

**Primary: job seekers finishing the Sprints training program.** Three profiles,
served by the same core flows and differing mainly in what skill-gap analysis and
match explanations need to say:

- **Fresh graduate** — degree or bootcamp just completed, little to no
  professional experience. Needs entry-level roles and a clear read on what they
  lack.
- **Junior professional** — 0–2 years in. Needs the noise filtered and roles
  targeted at skills that are still growing.
- **Career shifter** — moving between fields (e.g. marketing → data). Needs
  transferable skills named and the distance to the new field quantified.

The situation is the same across all three: mid-search, on a laptop, with a CV
file on hand and a finite amount of patience for rewriting it per application.
They also arrive cold from an email digest, meaning a match has to be legible
without the context of the session that produced it.

**Secondary: the reviewers of an internship deliverable.** The project is built
by a Sprints internship cohort and is assessed in a final demo. That is a real
audience with real expectations, not a footnote — see Operating Context.

## Product Purpose

Move a learner from *"I finished my training"* to *"I got a relevant job."*

The user uploads a CV and states their preferences; the system parses a
structured profile, ingests postings from ToS-compliant sources, ranks them
against the profile, explains why each one fits or doesn't, names the missing
skills, and drafts tailored application materials for the user to review. A
daily job re-runs matching and sends an email digest, so the search continues
between sessions.

Success is a user who gets to a relevant shortlist fast, understands *why* each
job is on it, and knows what to learn next. Success is explicitly **not**
auto-applying on the user's behalf, and not replacing the user's judgment on
anything the model wrote.

## Positioning

Most job tools return a ranked list and stop. This one is built so that the
ranking has to justify itself:

- **Every score carries a written explanation** that cites specific profile
  elements ("strong on Python, missing SQL"). An opaque number is a defect here,
  not a simplification.
- **The gap analysis is the second product.** Missing skills are computed against
  both the user's target roles and the postings actually being ingested, so the
  learning roadmap tracks live market demand rather than a static curriculum.
  This closes a loop a standalone job board has no reason to close, and one a
  standalone course platform has no job data to close.
- **The human approves; the machine drafts.** Generated CV summaries, skills
  highlights, and cover letters are drafts requiring explicit review. Prompts
  forbid inventing experience the user does not have.
- **Regional coverage.** Sources are chosen for MENA reach plus remote roles,
  not US-default listings.

## Operating Context

**Two lanes, and the design has to serve both.** An interactive lane where the
user is present (upload, review, chat, shortlist, prep) and an unattended daily
lane (scheduled matching, threshold check, email digest). The digest is a real
entry point, not a notification — users act on jobs they first see in email.

**Runs entirely locally, through the demo.** FastAPI on `localhost:8000`, the
React dev server on `5173` proxying `/api`, SQLite (`career_coach.db`), and
Qdrant embedded against a local directory. LLM calls go through a shared LiteLLM
gateway. No hosted deployment, no auth, no accounts — confirmed for v1, so the
laptop is the delivery environment and screens should be designed for it rather
than for a hosted future.

**Two clients against one HTTP surface.** `frontend/` (React) is the going-forward
UI; `streamlit_app/` remains in place until cutover so both can be compared
against the same backend. Neither imports backend code — everything is HTTP.

**The delivery frame is an internship.** Work lands through branches and pull
requests with a ~400-line ceiling, sprint by sprint, and ends in a demo. This
constrains scope more than it constrains quality: it means a screen is judged on
whether it is finished — real states, real data, real errors — not on how much of
it exists.

**The real evaluation scene for matching is comparison.** Users read several
ranked results side by side and decide which to spend an application on. Ranked
lists, fit scores, and matched-vs-missing splits are the product surface, not
decoration.

## Capabilities and Constraints

**Working end to end today.** CV upload and parsing (PDF/DOCX), an editable
parsed profile, vector retrieval of candidate jobs, LLM re-ranking, per-job match
explanations, skill-gap analysis, a conversational agent, job ingestion with
normalization and dedupe, ingestion run monitoring, and persisted notification
settings.

**Constraints that shape the interface:**

- **No user accounts and no auth.** Everything is stored under
  `user_id="default"`, threaded through the API as a parameter so real users
  become a UI change rather than a schema change. Nothing may imply a signed-in
  identity that does not exist.
- **Matching is slow by construction.** One pipeline run is four sequential model
  calls. Any screen that waits on it needs a loading state that says what is
  happening, not a bare spinner.
- **Degraded states are visible, never hidden.** When the conversational endpoint
  is unreachable, keyword routing takes over *and says so*. When a ranked job is
  missing from SQLite, the placeholder explanation returns **empty** strengths,
  gaps, recommendations, and next steps rather than fabricated analysis, because
  invented analysis is indistinguishable from the real agent's output. Any UI must
  preserve this distinction rather than smoothing it away.
- **Parser output is a draft.** Extracted fields are presented for correction, and
  editing the profile clears prior results so what is on screen always corresponds
  to the profile that produced it.
- **Match quality is graded and explained**, never binary and never a bare number.
  Matched and missing skills are a paired split, and both halves must be readable.
- **Job postings carry structured metadata** — job type, work mode, career level,
  experience range, salary where available — deliberately separated from real
  skills so the gap analysis is not polluted by chips like "Full Time".
- **Notification channels** are constrained to email and WhatsApp in storage;
  PRD v1 specifies email only, and which channels are honoured is the sender's
  call.

**Out of scope for v1:** auto-submitting applications, interview prep or mock
interviews, salary-negotiation coaching, a native mobile app, scraping sources
whose Terms of Service prohibit it, payments or subscriptions, multi-language
generation beyond the primary language, and **any hosted deployment — with the
auth and real accounts it would require.** The demo is given from the local
stack; this is a confirmed decision, not a state the project is waiting to
outgrow.

**Explicitly undecided:** the `job_insight` and `skill_gap` routers exist and
import cleanly but are not registered, so they are absent from the OpenAPI schema
— register or delete is an open decision with the owning lane. Streaming for
generated materials (SSE vs polling) is likewise undecided. Documentation
placement — inline on the landing page vs a `/docs` route — is open.

## Brand Commitments

**Sprints.** The product ships under the Sprints brand as "Sprints Career Coach",
and should read as an internal Sprints project. The mark and the typeface are
settled; the palette is not. Assets land by overwriting the placeholder files in
place, keeping their names, so nothing referencing them has to change.

- **The logo is real and in the repo.** `frontend/public/sprints_logo.svg` is the
  supplied Sprints asset, not a placeholder. **Do not redraw, retrace, recolor, or
  rebuild the mark in code** — a hand-approximated logo is subtly wrong in ways
  obvious to the people who own it. Use the file.
- **It is a two-color horizontal lockup**, `viewBox="0 0 300 70"` (roughly 4.3:1):
  the wordmark "Sprints" in black `#000`, and the glyph in blue `#004eff`. Both
  facts constrain placement. The black wordmark still needs a light background or
  a light variant, which is what `Logo`'s `onDark` prop exists for — but **any
  dark-background treatment must preserve the glyph's blue.** A blanket filter
  that lightens the wordmark also flattens the glyph to a solid, which discards
  the only brand color in the mark.
- **`#004eff` is an exact brand value**, read out of the supplied asset rather
  than sampled. It supersedes the `brand.mark` estimate in
  `frontend/tailwind.config.ts` and is the logo's color, not a UI color — the
  existing rule that blue is identity and interaction only, never a status, is
  unchanged.
- **The rest of the palette is still eyedropper estimates** sampled from
  screenshots, not the brand's exact values. Replace with the real `:root` custom
  properties when someone can read them out of devtools.
  `frontend/public/favicon.svg` is likewise still generic.
- **The typeface is Gilroy, and we are licensed for it.** The licensing question
  this record previously flagged is closed, and the code is now pointed at it:
  `frontend/src/styles/index.css` declares five `@font-face` weights and
  `frontend/tailwind.config.ts` leads its sans stack with Gilroy. **The font files
  are still outstanding.** Drop these five into `frontend/public/fonts/`, which
  does not exist yet and must be created:
  `Gilroy-Regular.woff2` (400), `Gilroy-Medium.woff2` (500),
  `Gilroy-SemiBold.woff2` (600), `Gilroy-Bold.woff2` (700), and
  `Gilroy-ExtraBold.woff2` (800). Until they land, the stack falls through to
  Plus Jakarta Sans — also absent — and then to the system sans, so the app
  renders in a close shape rather than shifting layout when the real face arrives.

**Voice.** Honest about what the system does and does not know. Errors state what
broke and what to do. Fallbacks announce themselves. Nothing generated is
presented as final.

## Evidence on Hand

**Real:**

- `data/sample_jobs_mena.json` — sample postings for local development.
- Live ingestion from Arbeitnow, Wuzzuf, and a Mock-MENA source, normalized into
  the canonical `JobPosting` model (`backend/models/job.py`).
- `career_coach.db` — local SQLite carrying actually-ingested postings, ingestion
  runs, and saved notification settings.
- A working pipeline whose output can be screenshotted as it really is.
- `frontend/public/sprints_logo.svg` — the real Sprints mark, supplied.
- `docs/` — PRD, architecture, ingestion pipeline, matching engine, vector store,
  notification parameters, API, setup, deployment, plus `frontend-migration-plan.md`,
  which is the authority for the Streamlit cutover sequence and the Gate 1 tokens.

**Absent, and not to be invented:** no testimonials, no named customers, no
usage numbers, no benchmark results, no pricing, no uptime or deployment claims,
no press. There are no real user photographs or brand photography. The palette
and the favicon are still placeholders (see Brand Commitments), and Gilroy is
licensed but not yet on disk: `frontend/public/fonts/` does not exist and the CSS
falls back to system sans.

## Product Principles

1. **Explain, never score silently.** A number without a reason is a bug. Every
   ranking, gap, and recommendation traces back to something in the user's actual
   profile.
2. **The machine drafts, the human approves.** Generated materials are always
   presented as editable drafts pending explicit review, and never as finished
   output.
3. **Empty beats invented.** When the system does not know, it shows nothing and
   says why. Fabricated content that is indistinguishable from real output is the
   worst available failure.
4. **Correction is part of the flow, not an error path.** Parsed profiles, skill
   lists, and preferences are expected to be wrong on first pass; editing them is
   a designed step with first-class affordances.
5. **Degradation is stated, not disguised.** Fallbacks, stale data, unreachable
   services, and slow pipelines are surfaced in the interface's own voice.

## Accessibility & Inclusion

- **WCAG 2.1 AA is the baseline** for the UI. Contrast, visible keyboard focus,
  and `prefers-reduced-motion` are requirements, not polish.
- **Fairness is a product requirement.** Matching and recommendations must not
  discriminate on protected characteristics (gender, age, nationality, and
  similar), and the interface must not surface or invite signals that could
  encode such bias.
- **PII is sensitive by default.** CVs carry personal data; storage is limited,
  retention is bounded, and users can delete their data and generated materials.
