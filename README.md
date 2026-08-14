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
- `src/data.js`: committed deployment snapshot of model metadata and curated samples.
- `api/`: Vercel functions for votes and the leaderboard.
- `server/`: shared Supabase configuration.
- `supabase.sql`: database schema.
- `vercel.json`: build, routing, and CORS configuration.

## Deployment

Connect this repository directly to the SampleBench Vercel project with the
repository root as its Root Directory. Configure `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` in Vercel; never commit their values.

Updating `src/data.js` is an explicit website-data release. The committed
`scripts/build_catalog.py` command validates the canonical dLMbench corpus
contract and deterministically selects the deployment snapshot. Commit both
`src/data.js` and `src/data-release.json` for every release.

The comparison and sample-browser views render each selected decoded text in
full. Whitespace, special-token strings, and decoding artifacts are preserved;
the scrollable cards provide the presentation boundary instead of modifying
the sample.
