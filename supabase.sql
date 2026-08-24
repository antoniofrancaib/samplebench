create table if not exists public.sample_votes (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  session_id text not null,
  battle_id text not null,
  choice text not null,
  preference_strength smallint,
  rubric_version text not null default 'categorical-overall-v1',
  winner_model_id text,
  loser_model_id text,
  left_model_id text not null,
  right_model_id text not null,
  left_sample_id text not null,
  right_sample_id text not null,
  response_time_ms integer not null,
  app_version text not null,
  payload jsonb not null default '{}'::jsonb,
  constraint sample_votes_choice_check check (
    choice in ('left', 'right', 'tie', 'both_bad') or
    (choice = 'skip' and app_version <> 'samplebench-web/dlmbench-canonical-20260824-r5')
  ),
  constraint sample_votes_preference_strength_check check (
    preference_strength is null or preference_strength between 1 and 5
  )
);

alter table public.sample_votes
  add column if not exists preference_strength smallint,
  add column if not exists rubric_version text not null default 'categorical-overall-v1';

alter table public.sample_votes
  alter column winner_model_id drop not null,
  alter column loser_model_id drop not null;

alter table public.sample_votes drop constraint if exists sample_votes_choice_check;
alter table public.sample_votes drop constraint if exists sample_votes_preference_strength_check;
alter table public.sample_votes drop constraint if exists sample_votes_response_time_check;

alter table public.sample_votes
  add constraint sample_votes_choice_check check (
    choice in ('left', 'right', 'tie', 'both_bad') or
    (choice = 'skip' and app_version <> 'samplebench-web/dlmbench-canonical-20260824-r5')
  ),
  add constraint sample_votes_preference_strength_check check (
    preference_strength is null or preference_strength between 1 and 5
  ),
  add constraint sample_votes_response_time_check check (response_time_ms between 0 and 86400000);

alter table public.sample_votes enable row level security;

drop policy if exists "sample_votes_insert_anon" on public.sample_votes;

-- Votes are accepted only by the server function, which validates the active
-- catalog and sanitizes the payload before using the service role.
-- The browser never talks to PostgREST directly. Remove all table grants from
-- public-facing roles; the server uses the service role key. RLS remains
-- enabled with no public policies as a second deny-by-default boundary.
revoke all privileges on public.sample_votes from anon, authenticated, public;

create index if not exists sample_votes_created_at_idx on public.sample_votes (created_at desc);
create index if not exists sample_votes_battle_id_idx on public.sample_votes (battle_id);
create index if not exists sample_votes_models_idx on public.sample_votes (winner_model_id, loser_model_id);
create index if not exists sample_votes_session_idx on public.sample_votes (session_id);
create index if not exists sample_votes_study_cohort_idx
  on public.sample_votes (app_version, (payload->>'cohort'), created_at desc);

-- Dedup: one vote per (session, battle) pair — enforced at the DB level by api/vote.js
create unique index if not exists sample_votes_session_battle_uniq
  on public.sample_votes (session_id, battle_id);

-- Allow service_role (used by pull_votes.py locally) to select all rows.
drop policy if exists "sample_votes_select_service" on public.sample_votes;
create policy "sample_votes_select_service"
on public.sample_votes
for select
to service_role
using (true);
