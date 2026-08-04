# Frontend Migration Plan: Streamlit to React

**Owner:** Omar Yahia Zahran (Pipeline/UI Orchestrator)
**Status:** Approved stack, design direction pending Gate 1
**Revised:** re-checked against the codebase after the matching integration
landed. Sections 1, 2, 8 and PR 1 changed as a result; see "What changed in this
revision" at the bottom.

---

## 1. Scope and framing

This is a delivery-layer change. The pipeline, the ingestion logic and the
vector store are not touched.

**The HTTP contract already exists.** `streamlit_app/` contains no
`from backend.` imports: every call goes over HTTP through
`streamlit_app/api_client.py` to FastAPI. The Streamlit app is already a client
rather than an in-process caller, which means React is a second client of a
surface that is proven in use, not a reason to build that surface from scratch.

What remains on the backend is narrower than a from-scratch contract: one
missing router, one untyped response, CORS, versioning, an error envelope,
and one genuine model conflict. Those are itemised in PR 0 and PR 1.

The model conflict is the one that hardens from annoyance into blocker the
moment responses are serialised to JSON. PR 0 exists to force that conversation
before it costs anyone a sprint.

**Non-goals:** changing pipeline behavior, changing ingestion or vector-store
logic, redesigning the API's semantics.

---

## 2. Stack

| Layer | Choice |
|---|---|
| Build | Vite |
| Framework | React + TypeScript |
| Styling | Tailwind |
| Components | shadcn/ui (copy-in source) |
| Routing | React Router, `/` public, `/app/*` product |
| Server state | TanStack Query |
| API types | `openapi-typescript`, generated from FastAPI's OpenAPI schema |
| Mocking | MSW |
| Location | `frontend/` (see note) |

**Note on location.** `frontend/` already exists in the repo as an empty
scaffold: `README.md`, `public/.gitkeep`, `src/.gitkeep`, nothing else. Its
README already proposes `src/pages/`, `src/components/`, `src/api/`. Building
into `frontend/` directly reuses that placeholder rather than leaving a dead
directory beside a new `frontend/web/`. If a second frontend target is ever
expected, `frontend/web/` is the better choice and the placeholder should be
deleted in the same PR. Pick one in PR 2 and do not leave both.

### Rejected, with reasons

**Next.js.** Backend is FastAPI, there is no SSR requirement, and it adds a Node
deployment surface to a compose file that is currently Python-only.

**Radix directly, no shadcn.** Would buy a more distinct shell but transfers
ownership of focus traps, portal positioning, and keyboard navigation. Those
bugs are silent, browser-specific, and unsearchable because they are ours.
Rejected on debuggability grounds, not aesthetics.

**Note on the "shadcn looks generic" concern:** the genericness lives in the
*default theme*, not the components. The look is a thin layer: color, type,
radius, density, spacing. Replacing that layer costs nothing and preserves every
debugging advantage. See section 5.

---

## 3. PR ladder

Each PR below is independently reviewable and independently revertable. Do not
combine them.

### PR 0: Contract freeze
Backend only. Zero frontend files.

- **Retire the duplicate `JobPosting`.** See the analysis below; this is not the
  mechanical swap it looks like.
- Version routes under `/api/v1`.
- No behavior changes.

**The duplicate, precisely.** Two classes carry the name:

| | `backend/models/job.py` | `backend/models/job_posting.py` |
|---|---|---|
| Status | Canonical | Duplicate |
| Skills field | `skills` | `required_skills` |
| Experience | `experience_years: str` | `min_experience: int` |
| Salary | `salary: Optional[str]` | `salary: int` |
| Also requires | `source`, `url`, `date` | none of these |
| Validators | title/company non-blank, url is http | none |
| Used by | ingestion, vector store, scorer, explanation, ORM | `backend/features/matching/schema.py` only |

They are **not interchangeable**. Repointing the duplicate's one consumer at the
canonical model is not an import change: the canonical model requires three
fields the duplicate has no source for, and renames two others.

**On this branch both files are already dead.**
`backend/features/matching/schema.py` is imported by nothing;
`backend/features/matching/routes.py` defines its own `MatchRequest`
(`profile` + `top_k`), and `scorer.py` imports the canonical `JobPosting`. So
the cleanup here is a deletion, not a migration.

**But it is not ours to delete yet.** `feature/sprint-2` (open, PR #11) has 6
unmerged commits and still imports both files from `scorer.py`, `routes.py` and
`db_models.py`. `feature/rag-retriever` and `feature/matching` also reference
them, but both are fully contained in this branch, so those references are
historical.

**Therefore:** raise it with the owner of PR #11 and delete after that PR merges
or closes. Deleting first turns an existing content conflict into a
delete/modify conflict in someone else's open PR, which is a worse trade than
waiting. The divergence already exists either way, because this branch moved
`scorer.py` and `db_models.py` onto the canonical model.

**Deliberately not doing:** a full consolidation of every lane's models into
`backend/schemas/`. The duplicate above is the only one that actually blocks
serialisation, and a four-lane refactor needs four owners in the review.

**Merge when:** every lane owner has reviewed the schema that affects them.
**Why it's first:** everything downstream depends on it, and it surfaces
cross-lane divergence in public rather than in a merge conflict.

### PR 1: HTTP surface
Smaller than originally scoped, because most of it already exists.

Already present and exercised by Streamlit today:

| Screen need | Endpoint |
|---|---|
| Job listing / search | `GET /ingestion/jobs` |
| CV upload | `POST /upload` |
| Match results | `POST /matching/pipeline` |
| Conversational agent | `POST /conversation` |
| Ingestion trigger and status | `POST /ingestion/run`, `GET /ingestion/runs/{id}` |
| Notification settings | `GET`/`POST /notifications/settings` |

What this PR actually adds:

- **A recommendations router.** The only genuinely missing one. The logic
  already exists in `streamlit_app/digest.py::build_notification_recommendations`
  and has no Streamlit import, so it lifts into a router almost unchanged.
- **`response_model` on `POST /upload`.** It declares none, so the generated
  client gets an empty schema for the CV response that a core screen depends
  on. This is a prerequisite for PR 4, not a nicety. It is the only endpoint
  with this problem: `POST /ingestion/run` returns 202 rather than 200 and is
  fully described by `RunIngestionResponse`.
- **CORS configuration.** `backend/main.py` installs no middleware today, so a
  Vite dev server is blocked on request one.
- **A consistent error envelope** (`status`, `code`, `message`, `request_id`).
  FastAPI's default is `{"detail": ...}` only. Note that
  `api_client._backend_error` already extracts `detail`, so whatever shape is
  chosen here should keep that path working until cutover.

**Also decide here:** `backend/routes/job_insight.py` and
`backend/routes/skill_gap.py` exist and import cleanly but are not registered in
`backend/main.py`, so they are absent from the OpenAPI schema entirely. Nothing
calls them, and the skill-gap logic is imported directly by
`matching_pipeline.py`. Either register them or delete them, with their owner.
Leaving them unregistered means React cannot see them and no one knows why.

**Merge when:** Streamlit still runs unchanged, and every screen's data is
reachable via `curl`. If you can't curl it, React can't render it.

### PR 2: Frontend scaffold, no features
Keep this one small. Pure infrastructure, fast review, unblocks everything after
it.

```
frontend/
  package.json  vite.config.ts  tsconfig.json  tailwind.config.ts
  .env.example        -> VITE_API_BASE_URL
  src/main.tsx  src/App.tsx  src/lib/api.ts   (fetch wrapper only)
  Dockerfile          -> node build -> nginx
+ compose service `web`, /api proxied to backend
+ CI job: install -> typecheck -> lint -> build
```

**Merge when:** CI is green, the container builds, and one page renders data
from `/api/v1/health`.
**Too big if:** it touches `src/components/`.

> **GATE 1: design direction.** See section 5. Blocks PR 3.

### PR 3: Tokens, shell, and primitives

- Design tokens from Gate 1 (color, type scale, spacing, radius, density)
- shadcn installed and **re-themed** to those tokens
- App shell: navigation, layout, responsive behavior
- State primitives: loading skeletons, empty states, error states
- `/_kitchen-sink` route rendering every component in every state

**Merge when:** kitchen-sink route is complete and screenshotted.
**Excludes:** all data fetching, all business screens.

### PR 3.5: Landing page and public shell

No API dependency. Built entirely against the Gate 1 tokens, which makes it the
cheapest possible validation of the design direction: if the tokens are wrong,
you find out on a page with no data plumbing to unpick.

- Route split: `/` public, `/app/*` product
- Explainer sections: what the system does, how the pipeline works
- Documentation section, anchored at the bottom of the page
- Primary CTA to `/app/upload`, **not** the dashboard

**Merge when:** the page is complete, responsive, and visually consistent with
the kitchen-sink route.
**Runs in parallel with:** PR 4.

**Why the CTA skips the dashboard:** landing a first-time visitor on an empty
dashboard is an empty state pretending to be a product. Sending them into upload
means the demo starts with something happening.

> **GATE 2: review the kitchen-sink route.** See section 5. Blocks PR 5.

### PR 4: Typed API client
No screens.

- `openapi-typescript` generation wired into the build
- TanStack Query hooks per endpoint
- MSW handlers mirroring every endpoint
- Query devtools enabled in dev builds

**Blocked by:** the `response_model` work in PR 1. Generating types against a
schema where `/upload` returns `unknown` produces a client that compiles and
still tells you nothing about the one payload a core screen depends on.

**Merge when:** the app runs fully against mocks with the backend stopped.
**Why it matters:** after this PR, backend schema drift is a build error rather
than a blank screen at runtime.

### PR 5 to N: One screen per PR

Build in this order. Each ships its screen, its hooks, its states, and a
Streamlit parity checklist in the PR body.

1. **Job browse / ingestion.** Your lane, lowest risk, exercises the full stack
   end to end.
2. **CV upload and parsed view.**
3. **Match results.** Split into list PR and detail-drawer PR if over ~400 lines.
4. **Recommendations / generated output.** Needs streaming; approach decided in
   PR 4.

**Logic that lives in the Streamlit layer and has no endpoint behind it.** Each
of these has to be either promoted to the backend or reimplemented in React.
Decide which per screen, and say so in the PR body:

- `streamlit_app/digest.py::build_notification_recommendations` (promoted in
  PR 1)
- `streamlit_app/pipeline_stub.py::placeholder_explanation`, plus the
  `MATCH_RESULT_KEYS` and `EXPLANATION_KEYS` contract constants
- `streamlit_app/chatbot_ui.py::summarise_parsed_profile`
- `streamlit_app/chatbot_ui.py::_route_by_keyword`, the fallback used when the
  conversational endpoint is unreachable

### PR N+1: Cutover
Flip the compose default to `web`. Update README and docs. Mark Streamlit
deprecated but leave the files in place.

### PR N+2: Remove Streamlit
One sprint after cutover. Separate PR so it reverts cleanly.

---

## 4. PR size rules

- ~400 changed lines is the ceiling. Over that, find the seam.
- If a PR needs two different reviewers to approve it, it is two PRs.
- No drive-by refactors.
- Every screen PR states what is **not** done yet, so reviewers aren't guessing.

---

## 5. Design gates

### Gate 1: Direction (before PR 3)

Input: annotated reference screenshots, tagged by what is being taken from each:
type, density, color, or data-viz treatment. Include at least one anti-reference.

**Collect two separate reference sets.** This product has two visual registers
and one set cannot drive both:

- **`/`, marketing register.** Explainer page, generous spacing, large type, one
  strong idea per section.
- **`/app/*`, product register.** Dense tables, ranked lists, upload states.
  Source these from real product UI, not from design showcases.

A product-UI reference applied to `/` produces a lifeless landing page. A
marketing reference applied to `/app` produces an app that is all whitespace and
no density. Tag each screenshot with which register it belongs to.

**Feasibility filter:**

| Cost | Scope |
|---|---|
| Nearly free | color, type, spacing, radius, borders, density, theme |
| Cheap | custom layouts, unusual navigation, asymmetric grids |
| Expensive | bespoke animation sequences, canvas/WebGL, hand-rolled charts, drag-and-drop |

Be generous with static appearance. Be skeptical of custom behavior.

**Directions to actively avoid.** These are where AI-assisted design currently
converges and will read as templated to reviewers:

- cream background, high-contrast serif, terracotta accent
- near-black background with a single bright acid-green or vermilion accent
- broadsheet layout, hairline rules, zero border-radius

**Output of Gate 1.** Direction decided: track the Sprints brand visibly, but
refine it. Their palette and logo, our spacing, radius and motion. This should
read as an internal Sprints project, which is what an internship deliverable
ought to look like.

```
COLOR       Sampled from sprints.ai screenshots. These are
            eyedropper estimates, not the brand's exact values.
            Confirm against :root in devtools before PR 3.

            Core
              --surface          #FFFFFF   cards, raised
              --surface-sunken   #F4F7FE   section bands
              --surface-hero     #E7ECFC   hero only, deeper
              --border           #E3E8F5   hairlines
              --text             #1D1D2B   headings
              --text-muted       #64647A   body
            Brand
              --brand            #1A5FEE   CTAs, links, focus
              --brand-deep       #3B55E6   full-bleed sections
              --brand-bright     #2AA0F2   emphasis words only
              --brand-mark       #0B44F5   the logo only

            --brand-mark is separate on purpose. The mark reads
            as a purer, more electric blue than the CTA blue,
            so pulling one value off the logo and using it for
            buttons would shift every interactive surface. Take
            the exact value from the logo file, and use it
            nowhere except the logo.
            Categorical (Sprints uses these for kind, not state)
              --teal             #17A79A   matched skills
              --amber            #F5B01F   gaps, "fully funded"

            Eleven values, where the block above asked for six.
            Deliberate: Sprints leans on teal and amber as
            categorical accents, and our match/gap split needs
            exactly that pair. The six-value discipline still
            applies to the core; do not add a twelfth.

            One rule the brand implies: blue is never a status.
            It is identity and interaction only. Match quality
            reads teal to amber, so a blue element never means
            "good".
            ________________________________________

TYPE        Sprints uses a rounded geometric sans throughout,
            headings and body, differing only by weight.

            Identifying a face from a screenshot is a guess,
            so this is a recommendation, not a match:
              display + body   Plus Jakarta Sans (SIL OFL, free)
              data             JetBrains Mono or Roboto Mono,
                               tabular figures on

            Confirm the real family in devtools first. If it is
            a licensed webfont (Greycliff, Gilroy and Circular
            all look close), that is a licensing question for
            someone at Sprints before PR 3, not a substitution
            to make quietly.

            The data face is not optional: fit scores sit in
            ranked lists and misalign badly in proportional
            figures.

            Weights   700 display, 600 subheads, 400 body.
                      Sprints sets emphasis words inside
                      headings in --brand-bright rather than
                      bolder. Worth keeping; it is distinctive
                      and cheap.
            ________________________________________

LAYOUT      DECIDED.
            Radius   generous and consistent; one value for
                     cards and controls, half it for inline
                     chips. No mixed radii on one surface.
            Border   prefer a raised surface over a drawn line.
                     Borders only where two surfaces of the
                     same elevation meet.
            Density  two registers, deliberately.
                     `/`      loose, one idea per section.
                     `/app/*` dense. Ranked lists and tables
                              are the product; whitespace here
                              costs the user scrolling.
            Grid     12-col on `/`, content-width capped.
                     `/app/*` fills available width.
            ________________________________________

SIGNATURE   The match/gap visualization. See below.
            ________________________________________

MOTION      DECIDED. This is the "smoother than theirs" axis.
            Duration 150ms for state changes (hover, focus),
                     250ms for entrances, 200ms for exits.
                     Nothing over 300ms; past that it reads
                     as lag rather than polish.
            Easing   ease-out for entrances, ease-in for
                     exits. Never linear on anything a person
                     watches.
            Animate  opacity and transform only. Animating
                     height, width or top forces layout on
                     every frame and is where smooth becomes
                     janky on a mid-range laptop.
            Never    no motion on the ranked list reordering
                     after a re-rank. Watching rows slide is
                     slower to read than seeing the new order.
            Honour   `prefers-reduced-motion: reduce` drops
                     every duration to 0ms. This is on the
                     Gate 2 checklist and is not optional.
            ________________________________________
```

**Why motion is the right thing to smooth.** Colour and spacing are where a
theme announces itself, and the brief is to stay recognisably Sprints on both.
Motion is the one layer that can be refined without diverging from the brand at
all, because it is the layer a static brand guide does not specify.

**Recommended signature:** the match/gap visualization. It is the core of the
product, inherently visual (ranked, comparative), and the screen a reviewer will
remember. Spend the boldness there and keep everything around it quiet.

**Sprints has already built this idiom, and we should echo it.** Their "Leave
With Proof, Not Just a Certificate" section pairs a pentagon radar chart with a
column of labelled horizontal bars and a percentage per row, scoring five
capability dimensions. That is structurally the same problem as ours: a profile
measured against several axes, shown both as a shape and as readable numbers.

Reusing that pairing means the signature screen looks native to Sprints rather
than borrowed, and it is a pattern their reviewers already read fluently. The
adaptation is direct: their five capability dimensions become our matched and
missing skills, the radar becomes profile against role requirement, and the bars
carry the per-skill detail with the fit score where their percentage sits.

**Two card patterns worth taking from the same source:**

- **Coloured top edge on stat cards.** A 2-3px bar in teal, amber or blue across
  the top of an otherwise plain white card. Cheap, distinctive, and it carries
  categorical meaning without tinting the whole surface.
- **Accent-tinted card**, as on their "Talk to an Expert" and "Chat on WhatsApp"
  pair: 1px border and a very faint background wash in the same hue, with a
  matching icon tile. This is the right treatment for a matched-versus-gap split
  on a job card.

**Brand assets: status.**

- **Palette.** Sampled from screenshots. Good enough to build against, not exact.
  Replace with the `:root` custom properties from devtools before PR 3.
- **Logo.** Seen, not yet in the repo. Save it to
  `frontend/public/sprints_logo.svg`. The mark is a blue glyph plus a black
  "Sprints" wordmark, so it needs a light background or a light-on-dark variant;
  do not place the supplied version on `--brand-deep`.
  A PNG will do to start, but the header renders it small and an SVG is the
  difference between crisp and slightly soft on a standard display.
- **Typefaces.** Still unidentified. Naming a face from a screenshot is a guess,
  so confirm in devtools.

Do not approximate the mark itself. Redrawing a company's logo by hand produces
something subtly wrong, and subtly wrong is worse than an obvious placeholder in
front of the people who own it.

**Tie the two registers together with it.** Make the landing hero the match
visualization itself, live or animated with sample data. One signature serves
both pages, and it avoids the hero-with-a-big-number-and-a-gradient pattern that
nearly every AI-assisted landing page converges on.

### Gate 2: Kitchen sink review (after PR 3, before PR 5)

Review the built `/_kitchen-sink` route, not a mockup. Real components, real
states. This is the cheapest possible moment to reject the direction.

**Checklist:**
- [ ] Every component matches the Gate 1 tokens, no stock shadcn defaults left
- [ ] Empty, loading, and error states exist for every data-bearing component
- [ ] Error copy states what broke and what to do, in the interface's voice
- [ ] Layout works down to mobile width
- [ ] Keyboard focus is visible throughout
- [ ] Reduced-motion preference respected

The unglamorous half of this list is what separates a finished-looking project
from an amateur one, more than palette choice does.

---

## 6. Debuggability kit

1. **MSW mock toggle** (PR 4). Flip mocks on. Bug disappears means backend, bug
   persists means frontend.
2. **Generated types** (PR 4). Schema drift fails the build instead of rendering
   blank.
3. **Query devtools** (PR 4). Identifies the failing query, its key, and its
   payload.
4. **Error envelope surfaced in dev** (PR 1 + PR 3). Status, endpoint, and
   request id rendered in the error component. Never debug a blank card.
5. **Two clients, one endpoint.** Already true today: Streamlit reaches the
   backend over the same HTTP surface React will use. If both break, it is the
   backend, no argument. Keeping Streamlit alive until cutover preserves this.

---

## 7. Definition of done, per screen PR

- [ ] Screen renders against mocks with the backend stopped
- [ ] Loading, empty, and error states implemented
- [ ] Types generated from the current OpenAPI schema, not hand-written
- [ ] Streamlit parity checklist in the PR body
- [ ] Screenshot attached
- [ ] Under ~400 changed lines

---

## 8. Open risks

| Risk | Impact | Handled by |
|---|---|---|
| Duplicate `JobPosting` across two modules | Ambiguous response shapes once serialised. Both copies are dead on this branch but live on open PR #11, so deletion is blocked on that PR | PR 0, after PR #11 resolves |
| `/upload` has no `response_model` | The generated client gets an empty schema for the CV response, so a core screen is untyped | PR 1, blocks PR 4 |
| `job_insight` and `skill_gap` routers unregistered | Invisible to the OpenAPI schema, so React cannot consume them and the reason is not obvious | Decide in PR 1 with the owning lane |
| Streaming approach for LLM responses undecided | Blocks PR 5.4 | Decide during PR 4 (SSE vs polling) |
| Tokens decided screen-by-screen instead of at Gate 1 | Every later PR reopens the design argument | Gate 1 is a hard block on PR 3 |
| Documentation section: inline vs `/docs` route | Inline is less work and reads as more finished; a route rendering `docs/*.md` scales better but adds a markdown pipeline | Decide at Gate 1, inline recommended for the demo |
| Landing page drifts visually from the app | Reads as two different products, a common tell of a rushed project | Both built from the same Gate 1 tokens; checked at Gate 2 |
| Matching latency | One pipeline run is four sequential model calls. A screen that waits on it needs a real loading state, not a spinner with no explanation | PR 5.3; consider parallelising the explanation calls backend-side first |
| No user/session concept yet | CTA goes straight to `/app/upload` with no auth | Fine for now; auth would insert at this boundary |

---

## What changed in this revision

The original draft was written before the matching integration merged. Checked
against the codebase, these claims no longer held:

- **"The Streamlit app calls the pipeline in-process"** and the derived estimate
  that "roughly 60% of this migration is backend work". `streamlit_app/` has no
  `from backend.` imports; it has gone over HTTP since the integration work.
  This resized PR 0 and PR 1 substantially.
- **"Missing `sentence-transformers` dependency"** as an open risk. It is pinned
  at `5.6.1` in `requirements.txt`, deliberately, because the embedding contract
  in `docs/vector-store.md` is frozen and both lanes must produce comparable
  vectors.
- **"CV lane bypassing the LiteLLM gateway"** as an open risk.
  `backend/services/llm_service.py` goes through `llm_client`, so every lane
  shares one provider switch and one error path.
- **PR 1's router list.** Three of the four already exist.

Added, having been missed the first time: the untyped-response problem and its
blocking relationship to PR 4, the unregistered routers, the inventory of
UI-side logic with no endpoint behind it, and the `frontend/` location conflict.
