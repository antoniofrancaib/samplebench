import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { models } from './data.js';
import './index.css';
import { cn } from '@/lib/utils';

const STORAGE_KEYS = {
  voterId: 'samplebench:voter_id',
  queuedVotes: 'samplebench:queued_votes',
  voteCount: 'samplebench:vote_count',
};

const APP_VERSION = 'samplebench-web/core-feedback-2026-06-11';
const RUBRIC_VERSION = 'preference-strength-v1';
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, '');
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;
const SUPABASE_TABLE = import.meta.env.VITE_SUPABASE_TABLE || 'sample_votes';

/* 4 choices — matches arena.ai battle UX */
const CHOICES = [
  { value: 'left',     label: 'A is better',  key: 'a' },
  { value: 'tie',      label: 'Both are good', key: 't' },
  { value: 'both_bad', label: 'Both are bad',  key: 'n' },
  { value: 'right',    label: 'B is better',  key: 'b' },
];

const samplePool = models.flatMap((model) =>
  (model.samples || []).map((sample, sampleIndex) => ({
    modelId: model.id, modelName: model.name, method: model.method,
    family: model.family, nfe: model.nfe, sampleId: sample.id,
    sampleIndex, text: sample.text, genPpl: sample.genPpl, entropy: sample.entropy,
  })),
).filter((s) => s.text);

function getRandomIndex(max) {
  if (max <= 1) return 0;
  if (globalThis.crypto?.getRandomValues) {
    const v = new Uint32Array(1); globalThis.crypto.getRandomValues(v); return v[0] % max;
  }
  return Math.floor(Math.random() * max);
}

function createPair(previousPairId) {
  if (samplePool.length < 2) return null;
  let left = samplePool[getRandomIndex(samplePool.length)];
  let right = samplePool[getRandomIndex(samplePool.length)];
  for (let i = 0; i < 80; i++) {
    const l = samplePool[getRandomIndex(samplePool.length)];
    const r = samplePool[getRandomIndex(samplePool.length)];
    const id = `${l.sampleId}__${r.sampleId}`;
    if (l.modelId !== r.modelId && id !== previousPairId) { left = l; right = r; break; }
  }
  return { id: `${left.sampleId}__${right.sampleId}`, left, right };
}

function safeReadJson(key, fallback) {
  try { const r = window.localStorage.getItem(key); return r ? JSON.parse(r) : fallback; } catch { return fallback; }
}
function safeWriteJson(key, value) {
  try { window.localStorage.setItem(key, JSON.stringify(value)); } catch {}
}
function createId() {
  return globalThis.crypto?.randomUUID?.() ?? `vote-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function getVoterId() {
  try {
    const existing = window.localStorage.getItem(STORAGE_KEYS.voterId);
    if (existing) return existing;
    const id = createId();
    window.localStorage.setItem(STORAGE_KEYS.voterId, id);
    return id;
  } catch { return createId(); }
}
function getVoteCount() {
  try { return Number(window.localStorage.getItem(STORAGE_KEYS.voteCount) || 0); } catch { return 0; }
}
function setStoredVoteCount(count) {
  try { window.localStorage.setItem(STORAGE_KEYS.voteCount, String(count)); } catch {}
}
function hasSupabaseConfig() { return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY); }

async function insertVote(row) {
  if (!hasSupabaseConfig()) return { queued: true };
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${SUPABASE_TABLE}`, {
    method: 'POST',
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      'Content-Type': 'application/json',
      Prefer: 'return=minimal',
    },
    body: JSON.stringify(row),
  });
  if (!response.ok) { const d = await response.text(); throw new Error(d || `Supabase ${response.status}`); }
  return { queued: false };
}

function readQueuedVotes() { return safeReadJson(STORAGE_KEYS.queuedVotes, []); }
function writeQueuedVotes(votes) { safeWriteJson(STORAGE_KEYS.queuedVotes, votes.slice(-200)); }
function queueVote(row) { writeQueuedVotes([...readQueuedVotes(), row]); }

async function flushQueuedVotes() {
  if (!hasSupabaseConfig()) return;
  const queued = readQueuedVotes();
  if (!queued.length) return;
  const remaining = [];
  for (const vote of queued) {
    try { await insertVote(vote); } catch (e) { console.error(e); remaining.push(vote); }
  }
  writeQueuedVotes(remaining);
}

function isBinaryChoice(choice) { return choice === 'left' || choice === 'right'; }

function buildVoteRow({ pair, choice, voterId, responseTimeMs, voteNumber }) {
  const winner = choice === 'left' ? pair.left : choice === 'right' ? pair.right : null;
  const loser  = choice === 'left' ? pair.right : choice === 'right' ? pair.left : null;
  return {
    session_id: voterId, battle_id: pair.id, choice,
    preference_strength: null,
    rubric_version: RUBRIC_VERSION,
    winner_model_id: winner?.modelId ?? null, loser_model_id: loser?.modelId ?? null,
    left_model_id: pair.left.modelId, right_model_id: pair.right.modelId,
    left_sample_id: pair.left.sampleId, right_sample_id: pair.right.sampleId,
    response_time_ms: responseTimeMs, app_version: APP_VERSION,
    payload: {
      vote_number: voteNumber, client_time: new Date().toISOString(),
      page_url: window.location.href,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      left: samplePayload(pair.left), right: samplePayload(pair.right),
      winner: winner && samplePayload(winner), loser: loser && samplePayload(loser),
    },
  };
}

function samplePayload(s) {
  return {
    model_id: s.modelId, model_name: s.modelName, sample_id: s.sampleId,
    method: s.method, family: s.family, nfe: s.nfe, sample_index: s.sampleIndex,
    gen_ppl: s.genPpl, entropy: s.entropy,
  };
}

/* ── App ──────────────────────────────────────────────────────── */
function App() { return <VotePage />; }

function VotePage() {
  const [voterId]        = useState(getVoterId);
  const [pair, setPair]  = useState(() => createPair());
  const [voteCount, setVoteCount] = useState(getVoteCount);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastChoice, setLastChoice] = useState(null);
  const startedAt = useRef(performance.now());

  useEffect(() => {
    flushQueuedVotes().catch(console.error);
  }, []);

  const advancePair = useCallback((currentPairId) => {
    setPair(createPair(currentPairId));
    setLastChoice(null);
    startedAt.current = performance.now();
  }, []);

  const submitChoice = useCallback(async (choiceValue) => {
    if (!pair || isSubmitting) return;
    setIsSubmitting(true);
    setLastChoice(choiceValue);
    const nextCount = voteCount + 1;
    const row = buildVoteRow({
      pair, choice: choiceValue, voterId,
      voteNumber: nextCount,
      responseTimeMs: Math.max(0, Math.round(performance.now() - startedAt.current)),
    });
    try {
      const result = await insertVote(row);
      if (result.queued) queueVote(row);
    } catch (err) {
      queueVote(row);
      console.error('SampleBench vote error', err);
    } finally {
      setStoredVoteCount(nextCount);
      setVoteCount(nextCount);
      setIsSubmitting(false);
      advancePair(pair.id);
    }
  }, [advancePair, isSubmitting, pair, voteCount, voterId]);

  useEffect(() => {
    function onKey(e) {
      if (e.target.matches('input,textarea,[contenteditable]')) return;
      if (isSubmitting || e.metaKey || e.ctrlKey || e.altKey) return;
      const map = { a: 'left', t: 'tie', n: 'both_bad', b: 'right' };
      const v = map[e.key?.toLowerCase()];
      if (v) { e.preventDefault(); submitChoice(v); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isSubmitting, submitChoice]);

  if (!pair) {
    return (
      <div className="h-dvh grid place-items-center text-muted-foreground text-sm">
        No sample pairs available.
      </div>
    );
  }

  return (
    <main
      className="h-dvh flex flex-col overflow-hidden bg-background"
      style={{ padding: '40px 48px 28px' }}
    >
      {/* ── Two panes in one rounded container ───────────── */}
      <section
        className="flex flex-1 min-h-0 rounded-xl border border-border overflow-hidden"
        aria-label="Generated text samples"
      >
        <SamplePane label="A" sample={pair.left} />
        <div className="w-px bg-border flex-shrink-0" aria-hidden="true" />
        <SamplePane label="B" sample={pair.right} />
      </section>

      {/* ── 4 choice buttons — click = vote ──────────────── */}
      <footer
        className="flex-none flex items-center justify-center gap-3 pt-5 pb-0"
        aria-label="Vote"
      >
        {CHOICES.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={isSubmitting}
            onClick={() => submitChoice(opt.value)}
            className={cn(
              'inline-flex items-center justify-center rounded-lg border px-5 text-[13px] font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
              'disabled:pointer-events-none',
              lastChoice === opt.value && isSubmitting
                ? 'bg-primary border-primary text-primary-foreground opacity-80'
                : 'bg-background border-input text-foreground/65 hover:bg-accent hover:border-[hsl(30_9%_83%)] hover:text-foreground disabled:opacity-35',
            )}
            style={{ height: 36 }}
          >
            {opt.label}
          </button>
        ))}
      </footer>
    </main>
  );
}

/* ── SamplePane ───────────────────────────────────────────────── */
function SamplePane({ label, sample }) {
  return (
    <article className="flex flex-col flex-1 min-w-0 min-h-0">
      {/* Minimal pane header */}
      <div className="flex-none h-10 flex items-center px-6 border-b border-border bg-background">
        <span className="text-[11px] font-semibold tracking-[0.1em] uppercase font-mono text-muted-foreground/50">
          Sample {label}
        </span>
      </div>

      {/* Independently scrollable body */}
      <div className="flex-1 min-h-0 overflow-y-auto bg-background">
        <div className="px-8 py-7 pb-12">
          <p className="text-[14.5px] leading-[1.78] text-foreground/78 whitespace-pre-wrap">
            {sample.text}
          </p>
        </div>
      </div>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
