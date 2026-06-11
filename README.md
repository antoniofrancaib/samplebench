# SampleBench

Human preference collection for likelihood-free language model evaluation.

SampleBench is a vote-only frontend where humans choose the better sample from a blind A/B pair and add a 1-5 preference strength for downstream correlation studies against generation-quality metrics.

## Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Supabase

Create the table and insert policy with `supabase.sql`, then configure these Vite environment variables in Vercel:

```bash
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_SUPABASE_TABLE=sample_votes
```

Each annotation stores the overall preference, optional 1-5 preference strength, sample/model ids, timing, and app/rubric version metadata.
