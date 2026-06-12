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

const CHOICES = [
  { value: 'left',     label: 'Sample A', key: 'a' },
  { value: 'right',    label: 'Sample B',  key: 'b' },
  { value: 'tie',      label: 'Tie',       key: 't' },
  { value: 'both_bad', label: 'Both bad',  key: 'n' },
  { value: 'skip',     label: 'Skip',      key: 's' },
];

const STRENGTHS = [
  { value: 1, label: 'Barely' },
  { value: 2, label: 'Slightly' },
  { value: 3, label: 'Clearly' },
  { value: 4, label: 'Much' },
  { value: 5, label: 'Overwhelmingly' },
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

function buildVoteRow({ pair, choice, strength, voterId, responseTimeMs, voteNumber }) {
  const winner = choice === 'left' ? pair.left : choice === 'right' ? pair.right : null;
  const loser  = choice === 'left' ? pair.right : choice === 'right' ? pair.left : null;
  return {
    session_id: voterId, battle_id: pair.id, choice,
    preference_strength: isBinaryChoice(choice) ? strength : null,
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

/* ── Vote button ─────────────────────────────────────────────── */
function VoteBtn({ selected, className, ...props }) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center rounded-lg border text-[13px] font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
        'disabled:pointer-events-none disabled:opacity-35',
        selected
          ? 'bg-primary border-primary text-primary-foreground'
          : 'bg-background border-input text-foreground/60 hover:bg-accent hover:border-[hsl(30_9%_83%)] hover:text-foreground',
        className,
      )}
      {...props}
    />
  );
}

/* ── App ──────────────────────────────────────────────────────── */
function App() { return <VotePage />; }

function VotePage() {
  const [voterId]           = useState(getVoterId);
  const [pair, setPair]     = useState(() => createPair());
  const [choice, setChoice] = useState(null);
  const [strength, setStrength] = useState(3);
  const [voteCount, setVoteCount] = useState(getVoteCount);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const startedAt = useRef(performance.now());

  useEffect(() => {
    flushQueuedVotes().catch(console.error);
  }, []);

  const advancePair = useCallback((currentPairId) => {
    setPair(createPair(currentPairId));
    setChoice(null);
    setStrength(3);
    startedAt.current = performance.now();
  }, []);

  const submitVote = useCallback(async () => {
    if (!pair || !choice || isSubmitting) return;
    setIsSubmitting(true);
    const nextCount = voteCount + 1;
    const row = buildVoteRow({
      pair, choice, strength, voterId,
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
  }, [advancePair, choice, isSubmitting, pair, strength, voteCount, voterId]);

  useEffect(() => {
    function onKey(e) {
      if (e.target.matches('input,textarea,[contenteditable]')) return;
      if (isSubmitting || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      if (k === 'Enter' || k === ' ') { if (choice) { e.preventDefault(); submitVote(); } return; }
      const cm = { a: 'left', b: 'right', t: 'tie', n: 'both_bad', s: 'skip' };
      if (cm[k?.toLowerCase()]) { setChoice(cm[k.toLowerCase()]); return; }
      if (isBinaryChoice(choice)) { const n = Number(k); if (n >= 1 && n <= 5) setStrength(n); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [choice, isSubmitting, submitVote]);

  if (!pair) {
    return (
      <div className="h-dvh grid place-items-center text-muted-foreground text-sm">
        No sample pairs available.
      </div>
    );
  }

  const strengthEnabled = isBinaryChoice(choice);
  const strengthLabel = strengthEnabled ? STRENGTHS.find((s) => s.value === strength)?.label : '';

  return (
    <main className="h-dvh flex flex-col overflow-hidden bg-background" style={{ padding: '40px 48px' }}>

      {/* ── Two sample cards ────────────────────────────── */}
      <section className="flex flex-1 min-h-0 gap-4 overflow-hidden" aria-label="Generated text samples">
        <SamplePane
          label="A"
          sample={pair.left}
          selected={choice === 'left'}
          onSelect={() => !isSubmitting && setChoice('left')}
        />
        <SamplePane
          label="B"
          sample={pair.right}
          selected={choice === 'right'}
          onSelect={() => !isSubmitting && setChoice('right')}
        />
      </section>

      {/* ── Controls ────────────────────────────────────── */}
      <footer
        className="flex-none flex items-center justify-center pt-4 pb-0"
        aria-label="Response controls"
      >
        <div className="flex items-center gap-2">
          {/* Choice */}
          <div className="flex gap-2" role="group" aria-label="Your preference">
            {CHOICES.map((opt) => (
              <VoteBtn
                key={opt.value}
                selected={choice === opt.value}
                disabled={isSubmitting}
                style={{ height: 34, padding: '0 14px' }}
                onClick={() => setChoice(opt.value)}
              >
                {opt.label}
              </VoteBtn>
            ))}
          </div>

          {/* Divider */}
          <div className="w-px h-5 bg-border mx-1 flex-shrink-0" aria-hidden="true" />

          {/* Strength */}
          <div
            className={cn('flex items-center gap-2 flex-shrink-0 transition-opacity', !strengthEnabled && 'opacity-25 pointer-events-none')}
            role="group"
            aria-label="Preference strength"
          >
            <span className="text-[12px] text-muted-foreground select-none">Strength</span>
            {STRENGTHS.map((opt) => (
              <VoteBtn
                key={opt.value}
                selected={strengthEnabled && strength === opt.value}
                disabled={!strengthEnabled || isSubmitting}
                title={opt.label}
                style={{ height: 34, width: 34 }}
                aria-label={`${opt.value} — ${opt.label}`}
                onClick={() => setStrength(opt.value)}
              >
                {opt.value}
              </VoteBtn>
            ))}
            <span
              className="text-[12px] text-muted-foreground min-w-[76px] transition-opacity"
              style={{ opacity: strengthEnabled ? 1 : 0 }}
              aria-live="polite"
            >
              {strengthLabel}
            </span>
          </div>

          {/* Divider */}
          <div className="w-px h-5 bg-border mx-1 flex-shrink-0" aria-hidden="true" />

          {/* Submit */}
          <button
            type="button"
            disabled={!choice || isSubmitting}
            onClick={submitVote}
            className={cn(
              'inline-flex items-center justify-center rounded-lg border text-[13px] font-semibold transition-colors flex-shrink-0',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
              choice && !isSubmitting
                ? 'bg-primary border-primary text-primary-foreground hover:opacity-90 cursor-pointer'
                : 'bg-background border-input text-muted-foreground/35 cursor-not-allowed',
            )}
            style={{ height: 34, padding: '0 18px' }}
          >
            {isSubmitting ? 'Saving…' : 'Submit →'}
          </button>
        </div>
      </footer>

    </main>
  );
}

/* ── SamplePane ───────────────────────────────────────────────── */
function SamplePane({ label, sample, selected, onSelect }) {
  return (
    <article
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`Select Sample ${label}`}
      onClick={onSelect}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(); } }}
      className={cn(
        'flex flex-col flex-1 min-w-0 rounded-2xl border cursor-pointer transition-colors duration-150 overflow-hidden',
        selected
          ? 'bg-accent/40 border-[hsl(30_9%_83%)]'
          : 'bg-card border-border hover:border-input hover:bg-accent/10',
      )}
    >
      {/* Label */}
      <div className="flex-none px-7 pt-6 pb-2">
        <span
          className={cn(
            'text-[11px] font-semibold tracking-[0.1em] uppercase font-mono transition-colors',
            selected ? 'text-foreground/70' : 'text-muted-foreground/50',
          )}
        >
          Sample {label}
        </span>
      </div>

      {/* Text body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-7 pb-8 cursor-auto" onClick={(e) => e.stopPropagation()}>
        <p
          className={cn(
            'text-[14.5px] leading-[1.78] whitespace-pre-wrap transition-colors duration-150',
            selected ? 'text-foreground' : 'text-foreground/72',
          )}
        >
          {sample.text}
        </p>
      </div>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
