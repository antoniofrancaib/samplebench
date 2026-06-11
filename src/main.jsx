import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { models } from './data.js';
import './styles.css';

const STORAGE_KEYS = {
  voterId: 'samplebench:voter_id',
  queuedVotes: 'samplebench:queued_votes',
  voteCount: 'samplebench:vote_count',
};

const APP_VERSION = 'samplebench-web/feedback-v2-2026-06-11';
const RUBRIC_VERSION = 'preference-rubric-v1';
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, '');
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;
const SUPABASE_TABLE = import.meta.env.VITE_SUPABASE_TABLE || 'sample_votes';

const CHOICE_OPTIONS = [
  { value: 'left', label: 'Sample A' },
  { value: 'right', label: 'Sample B' },
  { value: 'tie', label: 'Tie' },
  { value: 'both_bad', label: 'Both bad' },
  { value: 'skip', label: 'Skip' },
];

const STRENGTH_OPTIONS = [
  { value: 1, label: 'Barely' },
  { value: 2, label: 'Slightly' },
  { value: 3, label: 'Clearly' },
  { value: 4, label: 'Much' },
  { value: 5, label: 'Overwhelmingly' },
];

const REASON_OPTIONS = [
  { value: 'more_coherent', label: 'Coherence' },
  { value: 'more_fluent_grammar', label: 'Grammar' },
  { value: 'less_repetitive', label: 'Less repetition' },
  { value: 'better_vocabulary_naturalness', label: 'Vocabulary' },
  { value: 'better_topic_flow', label: 'Topic flow' },
  { value: 'fewer_artifacts', label: 'Fewer artifacts' },
  { value: 'more_human_like', label: 'Human-like' },
];

const AXES = [
  { id: 'overall_quality', label: 'Overall quality' },
  { id: 'coherence', label: 'Coherence' },
  { id: 'fluency_grammar', label: 'Grammar / fluency' },
  { id: 'repetition', label: 'Low repetition' },
  { id: 'vocabulary_naturalness', label: 'Vocabulary / naturalness' },
  { id: 'artifacts', label: 'Fewer artifacts' },
];

const AXIS_CHOICES = [
  { value: 'left', label: 'A' },
  { value: 'same', label: 'Same' },
  { value: 'right', label: 'B' },
  { value: 'not_sure', label: '?' },
];

const RATING_DIMENSIONS = [
  { id: 'overall', label: 'Overall' },
  { id: 'coherence', label: 'Coherence' },
  { id: 'fluency_grammar', label: 'Grammar' },
  { id: 'low_repetition', label: 'Low repetition' },
  { id: 'naturalness', label: 'Naturalness' },
  { id: 'artifact_free', label: 'Artifact-free' },
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

function makeEmptyRatings() {
  return Object.fromEntries(RATING_DIMENSIONS.map((dimension) => [dimension.id, null]));
}

function makeInitialFeedback() {
  return {
    choice: null,
    preferenceStrength: 3,
    reasons: [],
    axisVotes: Object.fromEntries(AXES.map((axis) => [axis.id, 'not_sure'])),
    ratings: {
      left: makeEmptyRatings(),
      right: makeEmptyRatings(),
    },
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

function buildVoteRow({ pair, feedback, voterId, responseTimeMs, voteNumber }) {
  const winner = feedback.choice === 'left' ? pair.left : feedback.choice === 'right' ? pair.right : null;
  const loser = feedback.choice === 'left' ? pair.right : feedback.choice === 'right' ? pair.left : null;
  const preferenceStrength = isBinaryChoice(feedback.choice) ? feedback.preferenceStrength : null;

  return {
    session_id: voterId,
    battle_id: pair.id,
    choice: feedback.choice,
    preference_strength: preferenceStrength,
    reasons: feedback.reasons,
    axis_votes: feedback.axisVotes,
    ratings: feedback.ratings,
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
      winner: winner && {
        model_id: winner.modelId,
        model_name: winner.modelName,
        sample_id: winner.sampleId,
      },
      loser: loser && {
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
  const [feedback, setFeedback] = useState(makeInitialFeedback);
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
    setFeedback(makeInitialFeedback());
    startedAt.current = performance.now();
  }, []);

  const submitFeedback = useCallback(async () => {
    if (!pair || isSubmitting || !feedback.choice) return;

    setIsSubmitting(true);
    setStatus('Saving feedback');

    const nextVoteCount = voteCount + 1;
    const row = buildVoteRow({
      pair,
      feedback,
      voterId,
      voteNumber: nextVoteCount,
      responseTimeMs: Math.max(0, Math.round(performance.now() - startedAt.current)),
    });

    try {
      const result = await insertVote(row);

      if (result.queued) {
        queueVote(row);
        setQueuedCount(readQueuedVotes().length);
        setStatus('Feedback queued');
      } else {
        setQueuedCount(readQueuedVotes().length);
        setStatus('Feedback recorded');
      }
    } catch (error) {
      queueVote(row);
      setQueuedCount(readQueuedVotes().length);
      setStatus('Feedback queued');
      console.error('Could not record SampleBench feedback', error);
    } finally {
      setStoredVoteCount(nextVoteCount);
      setVoteCount(nextVoteCount);
      setIsSubmitting(false);
      advancePair(pair.id);
    }
  }, [advancePair, feedback, isSubmitting, pair, voteCount, voterId]);

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

      <section className="sampleGrid" aria-label="Generated samples">
        <SamplePane label="Sample A" sample={pair.left} />
        <SamplePane label="Sample B" sample={pair.right} />
      </section>

      <FeedbackPanel
        feedback={feedback}
        setFeedback={setFeedback}
        disabled={isSubmitting}
        onSubmit={submitFeedback}
      />

      <section className="statusRow" aria-live="polite">
        <span>{status || `${voteCount.toLocaleString()} submitted`}</span>
        {queuedCount > 0 && <span>{queuedCount} queued</span>}
      </section>
    </main>
  );
}

function SamplePane({ label, sample }) {
  return (
    <article className="samplePane">
      <span className="sampleTopline">
        <strong>{label}</strong>
        <span>{sample.text.split(/\s+/).length.toLocaleString()} words</span>
      </span>
      <span className="sampleText">{sample.text}</span>
    </article>
  );
}

function FeedbackPanel({ feedback, setFeedback, disabled, onSubmit }) {
  const strengthDisabled = disabled || !isBinaryChoice(feedback.choice);
  const canSubmit = Boolean(feedback.choice) && !disabled;

  return (
    <section className="feedbackPanel" aria-label="Feedback details">
      <div className="panelHeader">
        <div>
          <h2>Feedback</h2>
          <p>Primary preference plus short structure for later metric-correlation analysis.</p>
        </div>
        <button className="submitButton" type="button" disabled={!canSubmit} onClick={onSubmit}>
          {disabled ? 'Saving...' : 'Record feedback'}
        </button>
      </div>

      <div className="feedbackGrid">
        <FieldBlock title="Overall preference" detail="Required">
          <SegmentedButtons
            options={CHOICE_OPTIONS}
            value={feedback.choice}
            disabled={disabled}
            onChange={(choice) => setFeedback((current) => ({ ...current, choice }))}
          />
        </FieldBlock>

        <FieldBlock title="Preference strength" detail="Only for A/B preferences">
          <ScaleButtons
            options={STRENGTH_OPTIONS}
            value={feedback.preferenceStrength}
            disabled={strengthDisabled}
            onChange={(preferenceStrength) => setFeedback((current) => ({ ...current, preferenceStrength }))}
          />
        </FieldBlock>

        <FieldBlock title="What made it better?" detail="Optional multi-select" wide>
          <ToggleChips
            options={REASON_OPTIONS}
            values={feedback.reasons}
            disabled={disabled}
            onChange={(reasons) => setFeedback((current) => ({ ...current, reasons }))}
          />
        </FieldBlock>
      </div>

      <div className="detailGrid">
        <AxisVotePanel
          value={feedback.axisVotes}
          disabled={disabled}
          onChange={(axisVotes) => setFeedback((current) => ({ ...current, axisVotes }))}
        />
        <RatingsPanel
          ratings={feedback.ratings}
          disabled={disabled}
          onChange={(ratings) => setFeedback((current) => ({ ...current, ratings }))}
        />
      </div>
    </section>
  );
}

function FieldBlock({ title, detail, wide = false, children }) {
  return (
    <div className={wide ? 'fieldBlock wide' : 'fieldBlock'}>
      <div className="fieldTop">
        <h3>{title}</h3>
        <span>{detail}</span>
      </div>
      {children}
    </div>
  );
}

function SegmentedButtons({ options, value, disabled, onChange }) {
  return (
    <div className="segmentedButtons">
      {options.map((option) => (
        <button
          key={option.value}
          className={value === option.value ? 'selected' : ''}
          type="button"
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function ScaleButtons({ options, value, disabled, onChange }) {
  return (
    <div className="scaleButtons">
      {options.map((option) => (
        <button
          key={option.value}
          className={value === option.value ? 'selected' : ''}
          type="button"
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          <strong>{option.value}</strong>
          <span>{option.label}</span>
        </button>
      ))}
    </div>
  );
}

function ToggleChips({ options, values, disabled, onChange }) {
  return (
    <div className="toggleChips">
      {options.map((option) => {
        const selected = values.includes(option.value);
        return (
          <button
            key={option.value}
            className={selected ? 'selected' : ''}
            type="button"
            disabled={disabled}
            onClick={() => {
              onChange(selected
                ? values.filter((value) => value !== option.value)
                : [...values, option.value]);
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function AxisVotePanel({ value, disabled, onChange }) {
  return (
    <section className="structuredPanel">
      <div className="fieldTop">
        <h3>Per-axis winner</h3>
        <span>A / same / B / unsure</span>
      </div>
      <div className="axisList">
        {AXES.map((axis) => (
          <div className="axisRow" key={axis.id}>
            <span>{axis.label}</span>
            <SegmentedButtons
              options={AXIS_CHOICES}
              value={value[axis.id]}
              disabled={disabled}
              onChange={(axisChoice) => onChange({ ...value, [axis.id]: axisChoice })}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function RatingsPanel({ ratings, disabled, onChange }) {
  const updateRating = (side, dimension, score) => {
    onChange({
      ...ratings,
      [side]: {
        ...ratings[side],
        [dimension]: ratings[side][dimension] === score ? null : score,
      },
    });
  };

  return (
    <section className="structuredPanel">
      <div className="fieldTop">
        <h3>Optional 1-5 ratings</h3>
        <span>Higher is better</span>
      </div>
      <div className="ratingsList">
        {RATING_DIMENSIONS.map((dimension) => (
          <div className="ratingRow" key={dimension.id}>
            <span>{dimension.label}</span>
            <RatingScale
              label="A"
              value={ratings.left[dimension.id]}
              disabled={disabled}
              onChange={(score) => updateRating('left', dimension.id, score)}
            />
            <RatingScale
              label="B"
              value={ratings.right[dimension.id]}
              disabled={disabled}
              onChange={(score) => updateRating('right', dimension.id, score)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function RatingScale({ label, value, disabled, onChange }) {
  return (
    <div className="ratingScale" aria-label={`${label} rating`}>
      <span>{label}</span>
      {[1, 2, 3, 4, 5].map((score) => (
        <button
          key={score}
          className={value === score ? 'selected' : ''}
          type="button"
          disabled={disabled}
          onClick={() => onChange(score)}
        >
          {score}
        </button>
      ))}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
