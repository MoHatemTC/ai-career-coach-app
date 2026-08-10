# Frontend

The React interface for the AI Career Coach. Replaces the Streamlit apps in
`streamlit_app/`, which stay in place until cutover so the two can be compared
against the same backend.

## Running it

The backend must be running first:

```bash
uvicorn backend.main:app --reload        # terminal 1, from the repo root
```

Then:

```bash
cd frontend
npm install
npm run dev                              # terminal 2, http://localhost:5173
```

`npm run dev` proxies `/api` to `http://127.0.0.1:8000`, so the browser only
talks to one origin. Override the target with `VITE_PROXY_TARGET`. CORS is also
configured backend-side (`CORS_ORIGINS`), because a production build served
from nginx does not go through the dev proxy.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on 5173 with the API proxy |
| `npm run build` | Typecheck, then production build into `dist/` |
| `npm run typecheck` | Types only, no build |
| `npm run gen:api` | Regenerate `src/services/schema.d.ts` from `backend/openapi.json` |

## Layers

```
src/
  services/    Everything that touches the network. Nothing above this layer
               calls fetch directly.
    http.ts      Fetch wrapper: error detail extraction, per-call timeouts
    api.ts       One function per endpoint
    types.ts     Domain types, taken from the generated schema where possible
    schema.d.ts  GENERATED. Do not edit; run `npm run gen:api`
  components/  Presentational. No data fetching.
    ui/          Primitives: Button, Card, Field, Badge, TagInput, States
    chat/        Chat transcript and composer
    match/       Match card
    profile/     Editable profile form
    landing/     The signature match visualization
    layout/      App shell, nav, backend status
    brand/       Logo
  pages/       One per route. Owns data fetching and page state.
  state/       Cross-route session state (profile, matches, chat, digest)
  lib/         Pure helpers with no React and no network
```

The rule that keeps this honest: a page may call `services`, a component may
not. If a component needs data, the page passes it in.

## Regenerating API types

`src/services/schema.d.ts` is generated from the backend's own OpenAPI schema,
so a backend change becomes a build error here rather than a blank screen at
runtime. To refresh it after changing a route:

```bash
# from the repo root, with the backend importable
python -c "import json, backend.main as m; json.dump(m.app.openapi(), open('backend/openapi.json','w'), indent=2)"
cd frontend && npm run gen:api
```

## The Sprints logo

`public/sprints_logo.svg` is a **placeholder**: the company name set in type,
nothing more. It is deliberately not an attempt to reproduce the Sprints mark,
because a hand-drawn approximation of a logo is subtly wrong in ways that are
obvious to the people who own it.

To use the real one, export it as SVG and overwrite that file, keeping the
name. Nothing in the code changes. Note the supplied wordmark is black, so it
needs a light background; `Logo` inverts it for use on dark sections via the
`onDark` prop.

`public/favicon.svg` is likewise a generic mark, not the Sprints one.

## Fonts

`src/styles/index.css` expects a variable font at
`public/fonts/PlusJakartaSans-Variable.woff2` and falls back to the system sans
until it exists, which is close enough in shape that layout does not shift when
the real face arrives.

Plus Jakarta Sans is a free lookalike for the rounded geometric sans on
sprints.ai, chosen because identifying a face from a screenshot is a guess. If
the real family turns out to be licensed (Greycliff, Gilroy and Circular all
look close), that is a licensing conversation before shipping, not a quiet
substitution.

## Design tokens

In `tailwind.config.ts`, with the reasoning in
`docs/frontend-migration-plan.md`. Colours are sampled from screenshots and are
close, not exact; replace them with the real `:root` custom properties when
someone can read them out of devtools.

One rule that is easy to break by accident: **blue is never a status.** It is
identity and interaction only. Match quality runs teal to amber, so no blue
element should ever read as "good".

## Streamlit parity

Everything the Streamlit apps did, and where it went:

| Streamlit | React |
|---|---|
| Backend health banner | Status dot in the app header |
| CV upload and Parse CV | `/app/upload` |
| Chat transcript, avatars, fixed-height scroll | `/app/chat` |
| Keyword fallback when `/chat` is absent | `lib/profile.ts`, same word list |
| Editable profile form with skills multiselect | `/app/upload`, `TagInput` |
| Match cards with links and explanations | `/app/matches` |
| Notification settings (Contract 6) | `/app/settings` |
| Trigger Now digest | `/app/settings` |
| `ingestion_dashboard.py` runs and jobs tables | `/app/ingestion` |
