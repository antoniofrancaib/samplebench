import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { models } from './data.js';
import './styles.css';

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
  { value: 'left', label: 'Sample A' },
  { value: 'right', label: 'Sample B' },
  { value: 'tie', label: 'Tie' },
  { value: 'both_bad', label: 'Both bad' },
  { value: 'skip', label: 'Skip' },
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
    modelId: model.id,
    modelName: model.name,
    method: model.method,
    family: model.family,
    nfe: model.nfe,
    sampleId: sample.id,
    sampleIndex,
    text: sample.text,
    genPpl: sample.genPpl,
    entropy: sample.entropy,
  })),
).filter((sample) => sample.text);

function getRandomIndex(max) {
  if (max <= 1) return 0;

  if (globalThis.crypto?.getRandomValues) {
    const values = new Uint32Array(1);
    globalThis.crypto.getRandomValues(values);
    return values[0] % max;
  }

  return Math.floor(Math.random() * max);
}

function createPair(previousPairId) {
  if (samplePool.length < 2) return null;

  let left = samplePool[getRandomIndex(samplePool.length)];
  let right = samplePool[getRandomIndex(samplePool.length)];

  for (let attempt = 0; attempt < 80; attempt += 1) {
    const candidateLeft = samplePool[getRandomIndex(samplePool.length)];
    const candidateRight = samplePool[getRandomIndex(samplePool.length)];
    const pairId = `${candidateLeft.sampleId}__${candidateRight.sampleId}`;

    if (candidateLeft.modelId !== candidateRight.modelId && pairId !== previousPairId) {
      left = candidateLeft;
      right = candidateRight;
      break;
    }
  }

  return {
    id: `${left.sampleId}__${right.sampleId}`,
    left,
    right,
  };
}

function safeReadJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function safeWriteJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage can be unavailable in restrictive browser contexts.
  }
}

function createId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `vote-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getVoterId() {
  try {
    const existing = window.localStorage.getItem(STORAGE_KEYS.voterId);
    if (existing) return existing;

    const voterId = createId();
    window.localStorage.setItem(STORAGE_KEYS.voterId, voterId);
    return voterId;
  } catch {
    return createId();
  }
}

function getVoteCount() {
  try {
    return Number(window.localStorage.getItem(STORAGE_KEYS.voteCount) || 0);
  } catch {
    return 0;
  }
}

function setStoredVoteCount(count) {
  try {
    window.localStorage.setItem(STORAGE_KEYS.voteCount, String(count));
  } catch {
    // Best effort only.
  }
}

function hasSupabaseConfig() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

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

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Supabase insert failed with ${response.status}`);
  }

  return { queued: false };
}

function readQueuedVotes() {
  return safeReadJson(STORAGE_KEYS.queuedVotes, []);
}

function writeQueuedVotes(votes) {
  safeWriteJson(STORAGE_KEYS.queuedVotes, votes.slice(-200));
}

function queueVote(row) {
  writeQueuedVotes([...readQueuedVotes(), row]);
}

async function flushQueuedVotes() {
  if (!hasSupabaseConfig()) return;

  const queuedVotes = readQueuedVotes();
  if (!queuedVotes.length) return;

  const remaining = [];

  for (const vote of queuedVotes) {
    try {
      await insertVote(vote);
    } catch (error) {
      console.error('Could not flush queued SampleBench vote', error);
      remaining.push(vote);
    }
  }

  writeQueuedVotes(remaining);
}

function isBinaryChoice(choice) {
  return choice === 'left' || choice === 'right';
}

function buildVoteRow({ pair, choice, strength, voterId, responseTimeMs, voteNumber }) {
  const winner = choice === 'left' ? pair.left : choice === 'right' ? pair.right : null;
  const loser = choice === 'left' ? pair.right : choice === 'right' ? pair.left : null;
  const preferenceStrength = isBinaryChoice(choice) ? strength : null;

  return {
    session_id: voterId,
    battle_id: pair.id,
    choice,
    preference_strength: preferenceStrength,
    rubric_version: RUBRIC_VERSION,
    winner_model_id: winner?.modelId ?? null,
    loser_model_id: loser?.modelId ?? null,
    left_model_id: pair.left.modelId,
    right_model_id: pair.right.modelId,
    left_sample_id: pair.left.sampleId,
    right_sample_id: pair.right.sampleId,
    response_time_ms: responseTimeMs,
    app_version: APP_VERSION,
    payload: {
      vote_number: voteNumber,
      client_time: new Date().toISOString(),
      page_url: window.location.href,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
      left: samplePayload(pair.left),
      right: samplePayload(pair.right),
      winner: winner && samplePayload(winner),
      loser: loser && samplePayload(loser),
    },
  };
}

function samplePayload(sample) {
  return {
    model_id: sample.modelId,
    model_name: sample.modelName,
    sample_id: sample.sampleId,
    method: sample.method,
    family: sample.family,
    nfe: sample.nfe,
    sample_index: sample.sampleIndex,
    gen_ppl: sample.genPpl,
    entropy: sample.entropy,
  };
}

function App() {
  return <VotePage />;
}

function VotePage() {
  const [voterId] = useState(getVoterId);
  const [pair, setPair] = useState(() => createPair());
  const [choice, setChoice] = useState(null);
  const [strength, setStrength] = useState(3);
  const [voteCount, setVoteCount] = useState(getVoteCount);
  const [status, setStatus] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [queuedCount, setQueuedCount] = useState(() => readQueuedVotes().length);
  const startedAt = useRef(performance.now());

  useEffect(() => {
    flushQueuedVotes().catch((error) => {
      console.error('Could not flush queued SampleBench votes', error);
    }).finally(() => {
      setQueuedCount(readQueuedVotes().length);
    });
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
    setStatus('Saving response');

    const nextVoteCount = voteCount + 1;
    const row = buildVoteRow({
      pair,
      choice,
      strength,
      voterId,
      voteNumber: nextVoteCount,
      responseTimeMs: Math.max(0, Math.round(performance.now() - startedAt.current)),
    });

    try {
      const result = await insertVote(row);

      if (result.queued) {
        queueVote(row);
        setQueuedCount(readQueuedVotes().length);
        setStatus('Response queued');
      } else {
        setQueuedCount(readQueuedVotes().length);
        setStatus('Response recorded');
      }
    } catch (error) {
      queueVote(row);
      setQueuedCount(readQueuedVotes().length);
      setStatus('Response queued');
      console.error('Could not record SampleBench response', error);
    } finally {
      setStoredVoteCount(nextVoteCount);
      setVoteCount(nextVoteCount);
      setIsSubmitting(false);
      advancePair(pair.id);
    }
  }, [advancePair, choice, isSubmitting, pair, strength, voteCount, voterId]);

  if (!pair) {
    return (
      <main className="page emptyState">
        <h1>Which sample is better?</h1>
        <p>No sample pairs are available.</p>
      </main>
    );
  }

  const strengthEnabled = isBinaryChoice(choice);
  const selectedChoiceLabel = CHOICES.find((option) => option.value === choice)?.label;

  return (
    <main className="page">
      <section className="heading">
        <div>
          <span className="eyebrow">SampleBench</span>
          <h1>Which sample is better?</h1>
        </div>
        <div className="sessionMeta">
          <span>{voteCount.toLocaleString()} submitted</span>
          {queuedCount > 0 && <span>{queuedCount} queued</span>}
        </div>
      </section>

      <section className="samples" aria-label="Generated samples">
        <SamplePane label="Sample A" sample={pair.left} selected={choice === 'left'} />
        <SamplePane label="Sample B" sample={pair.right} selected={choice === 'right'} />
      </section>

      <section className="controlDock" aria-label="Preference controls">
        <div className="controlHeader">
          <div>
            <h2>Preference</h2>
            <p>{selectedChoiceLabel ? `${selectedChoiceLabel} selected` : 'Choose the better sample, or mark no clear winner.'}</p>
          </div>
          <button className="submitButton" type="button" disabled={!choice || isSubmitting} onClick={submitVote}>
            {isSubmitting ? 'Saving...' : 'Submit'}
          </button>
        </div>

        <div className="choiceGrid">
          {CHOICES.map((option) => (
            <button
              key={option.value}
              className={choice === option.value ? 'choiceButton selected' : 'choiceButton'}
              type="button"
              disabled={isSubmitting}
              onClick={() => setChoice(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className={strengthEnabled ? 'strengthBlock' : 'strengthBlock disabled'}>
          <div className="strengthTop">
            <span>Preference strength</span>
            <strong>{strengthEnabled ? `${strength}/5` : 'Only for A/B'}</strong>
          </div>
          <div className="strengthGrid">
            {STRENGTHS.map((option) => (
              <button
                key={option.value}
                className={strengthEnabled && strength === option.value ? 'strengthButton selected' : 'strengthButton'}
                type="button"
                disabled={!strengthEnabled || isSubmitting}
                onClick={() => setStrength(option.value)}
              >
                <strong>{option.value}</strong>
                <span>{option.label}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="statusRow" aria-live="polite">
        <span>{status || ' '}</span>
      </section>
    </main>
  );
}

function SamplePane({ label, sample, selected }) {
  return (
    <article className={selected ? 'samplePane selected' : 'samplePane'}>
      <span className="sampleTopline">
        <strong>{label}</strong>
        <span>{sample.text.split(/\s+/).length.toLocaleString()} words</span>
      </span>
      <span className="sampleText">{sample.text}</span>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
