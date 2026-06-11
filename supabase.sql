create table if not exists public.sample_votes (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  session_id text not null,
  battle_id text not null,
  choice text not null,
  preference_strength smallint,
  rubric_version text not null default 'preference-strength-v1',
  winner_model_id text,
  loser_model_id text,
  left_model_id text not null,
  right_model_id text not null,
  left_sample_id text not null,
  right_sample_id text not null,
  response_time_ms integer not null,
  app_version text not null,
  payload jsonb not null default '{}'::jsonb,
  constraint sample_votes_choice_check check (choice in ('left', 'right', 'tie', 'both_bad', 'skip')),
  constraint sample_votes_preference_strength_check check (
    preference_strength is null or preference_strength between 1 and 5
  )
);

alter table public.sample_votes
  add column if not exists preference_strength smallint,
  add column if not exists rubric_version text not null default 'preference-strength-v1';

alter table public.sample_votes
  alter column winner_model_id drop not null,
  alter column loser_model_id drop not null;

alter table public.sample_votes drop constraint if exists sample_votes_choice_check;
alter table public.sample_votes drop constraint if exists sample_votes_preference_strength_check;

alter table public.sample_votes
  add constraint sample_votes_choice_check check (choice in ('left', 'right', 'tie', 'both_bad', 'skip')),
  add constraint sample_votes_preference_strength_check check (
    preference_strength is null or preference_strength between 1 and 5
  );

alter table public.sample_votes enable row level security;

drop policy if exists "sample_votes_insert_anon" on public.sample_votes;

create policy "sample_votes_insert_anon"
on public.sample_votes
for insert
to anon
with check (
  choice in ('left', 'right', 'tie', 'both_bad', 'skip')
  and (preference_strength is null or preference_strength between 1 and 5)
  and response_time_ms >= 0
);

create index if not exists sample_votes_created_at_idx on public.sample_votes (created_at desc);
create index if not exists sample_votes_battle_id_idx on public.sample_votes (battle_id);
create index if not exists sample_votes_models_idx on public.sample_votes (winner_model_id, loser_model_id);
