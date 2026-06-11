import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { models } from './data.js';
import './styles.css';

const STORAGE_KEYS = {
  voterId: 'samplebench:voter_id',
  queuedVotes: 'samplebench:queued_votes',
  voteCount: 'samplebench:vote_count',
};

const APP_VERSION = 'samplebench-web/vote-only-2026-06-11';
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, '');
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;
const SUPABASE_TABLE = import.meta.env.VITE_SUPABASE_TABLE || 'sample_votes';

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

function buildVoteRow({ pair, choice, voterId, responseTimeMs, voteNumber }) {
  const winner = choice === 'left' ? pair.left : pair.right;
  const loser = choice === 'left' ? pair.right : pair.left;

  return {
    session_id: voterId,
    battle_id: pair.id,
    choice,
    winner_model_id: winner.modelId,
    loser_model_id: loser.modelId,
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
      left: {
        model_name: pair.left.modelName,
        method: pair.left.method,
        family: pair.left.family,
        nfe: pair.left.nfe,
        sample_index: pair.left.sampleIndex,
        gen_ppl: pair.left.genPpl,
        entropy: pair.left.entropy,
      },
      right: {
        model_name: pair.right.modelName,
        method: pair.right.method,
        family: pair.right.family,
        nfe: pair.right.nfe,
        sample_index: pair.right.sampleIndex,
        gen_ppl: pair.right.genPpl,
        entropy: pair.right.entropy,
      },
      winner: {
        model_id: winner.modelId,
        model_name: winner.modelName,
        sample_id: winner.sampleId,
      },
      loser: {
        model_id: loser.modelId,
        model_name: loser.modelName,
        sample_id: loser.sampleId,
      },
    },
  };
}

function App() {
  return <VotePage />;
}

function VotePage() {
  const [voterId] = useState(getVoterId);
  const [pair, setPair] = useState(() => createPair());
  const [voteCount, setVoteCount] = useState(getVoteCount);
  const [status, setStatus] = useState('');
  const [pendingChoice, setPendingChoice] = useState(null);
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
    startedAt.current = performance.now();
  }, []);

  const submitVote = useCallback(async (choice) => {
    if (!pair || pendingChoice) return;

    setPendingChoice(choice);
    setStatus(choice === 'left' ? 'Saving Sample A' : 'Saving Sample B');

    const nextVoteCount = voteCount + 1;
    const row = buildVoteRow({
      pair,
      choice,
      voterId,
      voteNumber: nextVoteCount,
      responseTimeMs: Math.max(0, Math.round(performance.now() - startedAt.current)),
    });

    try {
      const result = await insertVote(row);

      if (result.queued) {
        queueVote(row);
        setQueuedCount(readQueuedVotes().length);
        setStatus('Preference queued');
      } else {
        setQueuedCount(readQueuedVotes().length);
        setStatus('Preference recorded');
      }
    } catch (error) {
      queueVote(row);
      setQueuedCount(readQueuedVotes().length);
      setStatus('Preference queued');
      console.error('Could not record SampleBench vote', error);
    } finally {
      setStoredVoteCount(nextVoteCount);
      setVoteCount(nextVoteCount);
      setPendingChoice(null);
      advancePair(pair.id);
    }
  }, [advancePair, pair, pendingChoice, voteCount, voterId]);

  if (!pair) {
    return (
      <main className="votePage emptyState">
        <h1>Which sample is better?</h1>
        <p>No sample pairs are available.</p>
      </main>
    );
  }

  return (
    <main className="votePage">
      <section className="questionBlock" aria-labelledby="vote-question">
        <h1 id="vote-question">Which sample is better?</h1>
      </section>

      <section className="sampleGrid" aria-label="Sample preference options">
        <SampleOption
          label="Sample A"
          sample={pair.left}
          pending={pendingChoice === 'left'}
          disabled={Boolean(pendingChoice)}
          onClick={() => submitVote('left')}
        />
        <SampleOption
          label="Sample B"
          sample={pair.right}
          pending={pendingChoice === 'right'}
          disabled={Boolean(pendingChoice)}
          onClick={() => submitVote('right')}
        />
      </section>

      <section className="statusRow" aria-live="polite">
        <span>{status || ' '}</span>
        {queuedCount > 0 && <span>{queuedCount} queued</span>}
      </section>
    </main>
  );
}

function SampleOption({ label, sample, pending, disabled, onClick }) {
  return (
    <article className="sampleOption">
      <span className="sampleTopline">
        <strong>{label}</strong>
        <span>{sample.text.split(/\s+/).length.toLocaleString()} words</span>
      </span>
      <span className="sampleText">{sample.text}</span>
      <button className="sampleAction" type="button" disabled={disabled} onClick={onClick}>
        {pending ? 'Saving...' : `Choose ${label}`}
      </button>
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
