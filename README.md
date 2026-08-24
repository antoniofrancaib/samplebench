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

The active r5 release contains 24 models and 960 samples (40 per model):
7 LM1B models and 17 OWT models. Every one of the 66 inspected canonical
source corpora is classified by `scripts/arm-evidence-r5.json`; 42 legacy,
locally extrapolated, unsupported, insufficiently documented, or non-headline
arms are excluded. The public release contains only the reviewed Primary set
of author-rational headline operating points across selected families, scales,
and one-step regimes.

`src/data-release.json` records the paper/configuration evidence, exact
checkpoint revision and digest, source corpus and manifest digests, declared
limitations, exclusion reasons, cohort membership, deterministic selected
source IDs, and safety-screen counts for every inspected arm. Included arms
must pass the catalog builder's checkpoint/config/NFE identity checks; the
repaired SDTT and CoBit arms have additional decoder or stochastic-sampler
manifest requirements. Excluded corpora must not be reintroduced without a
new study version and review.

The comparison and sample-browser views render each selected decoded text in
full. Whitespace, special-token strings, and decoding artifacts are preserved;
the scrollable cards provide the presentation boundary instead of modifying
the sample.
