# SampleBench

Self-contained source for the blind A/B human-preference website deployed at
[samplebench.vercel.app](https://samplebench.vercel.app/).

This repository contains only the website: the React frontend, its frozen
curated sample catalog, the voting API, and the Supabase schema. It does not
depend on the dLMbench scientific repository at build or deployment time.

## Local development

```bash
npm ci
npm run dev
```

## Build

```bash
npm run build
```

The production build is written to `dist/`.

## Repository layout

- `src/`: React and Vite frontend.
- `src/data-public.js`: generated opaque sample/group catalog used by verification tooling.
- `src/data.js`: curated samples and model metadata used by the arena and sample browser.
- `server/catalog.js`: server-side opaque-ID-to-model join used to validate votes.
- `api/`: Vercel functions for votes and the leaderboard.
- `server/`: shared Supabase configuration.
- `supabase.sql`: database schema.
- `vercel.json`: build, routing, and CORS configuration.

## Deployment

Connect this repository directly to the SampleBench Vercel project with the
repository root as its Root Directory. Configure `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` (or the legacy `SUPABASE_SERVICE_ROLE_KEY`) in Vercel;
never commit their values. Apply `supabase.sql` before enabling collection.
The public leaderboard reads aggregated vote counts through its server-side API.

Updating the catalog is an explicit website-data release. The committed
`scripts/build_catalog.py` command validates the canonical dLMbench corpus
contract, applies the deterministic public-safety screen, and selects the
deployment snapshot by hash. Commit `src/data-public.js`, `src/data.js`,
`server/catalog.js`, and `src/data-release.json` for every release. Model
identity remains hidden in the comparison cards but is visible in the Samples
and Leaderboard views. The automated screen is a conservative first pass and
still requires human review of the selected text before public recruitment.

The active r4 release contains 57 models and 2,280 samples (40 per model):
8 LM1B models and 49 OWT models. It excludes eight byte-identical or
exploratory OWT/LM1B directories and records all 65 inspected source corpora in
`src/data-release.json`. The excluded corpora must not be reintroduced into a
human-comparison release without a new study version and review.

The comparison and sample-browser views render each selected decoded text in
full. Whitespace, special-token strings, and decoding artifacts are preserved;
the scrollable cards provide the presentation boundary instead of modifying
the sample.
