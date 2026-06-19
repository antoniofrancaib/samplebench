import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { models } from './data.js';
import './index.css';
import { cn } from '@/lib/utils';
import { ArrowLeftRight, Ban, ChevronRight, Copy, Check } from 'lucide-react';

const STORAGE_KEYS = {
  voterId: 'samplebench:voter_id',
  queuedVotes: 'samplebench:queued_votes',
  voteCount: 'samplebench:vote_count',
};

const APP_VERSION = 'samplebench-web/core-feedback-2026-06-11';
const RUBRIC_VERSION = 'preference-strength-v1';

/* 4 choices — matches arena.ai battle UX.
   On mobile the two middle choices collapse to icon-only buttons (image copy 2). */
const CHOICES = [
  { value: 'left',     label: 'A is better',  key: 'a', icon: null },
  { value: 'tie',      label: 'Both are good', key: 't', icon: ArrowLeftRight },
  { value: 'both_bad', label: 'Both are bad',  key: 'n', icon: Ban },
  { value: 'right',    label: 'B is better',  key: 'b', icon: null },
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
async function insertVote(row) {
  const response = await fetch('/api/vote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(row),
  });
  // 4xx = intentional rejection (dupe, rate-limit, bad input) — don't retry
  if (response.status >= 400 && response.status < 500) return { queued: false };
  // 5xx / network error → throw → caller queues for retry
  if (!response.ok) throw new Error(`vote API ${response.status}`);
  return { queued: false };
}

function readQueuedVotes() { return safeReadJson(STORAGE_KEYS.queuedVotes, []); }
function writeQueuedVotes(votes) { safeWriteJson(STORAGE_KEYS.queuedVotes, votes.slice(-200)); }
function queueVote(row) { writeQueuedVotes([...readQueuedVotes(), row]); }

async function flushQueuedVotes() {
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

/* ── Reveal overlay ───────────────────────────────────────────── */
function revealText(choice, lName, rName) {
  if (choice === 'left')     return { headline: lName, sub: `is better than ${rName}` };
  if (choice === 'right')    return { headline: rName, sub: `is better than ${lName}` };
  if (choice === 'tie')      return { headline: 'Equally good', sub: `${lName} · ${rName}` };
  if (choice === 'both_bad') return { headline: 'Both bad', sub: `${lName} · ${rName}` };
  return null;
}

function RevealOverlay({ reveal, fading }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    setShown(false);
    if (!reveal) return;
    const id1 = requestAnimationFrame(() => {
      const id2 = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(id2);
    });
    return () => cancelAnimationFrame(id1);
  }, [reveal]);

  if (!reveal) return null;
  const visible = shown && !fading;
  const { pair, choice } = reveal;
  const txt = revealText(choice, pair.left.modelName, pair.right.modelName);
  if (!txt) return null;

  return (
    <div
      aria-live="polite"
      className={cn(
        'fixed inset-0 z-50 grid place-items-center pointer-events-none',
        'transition-opacity duration-300',
        visible ? 'opacity-100' : 'opacity-0',
      )}
    >
      <div className={cn(
        'flex flex-col items-center gap-1 px-8 py-5 rounded-2xl max-w-xs w-[calc(100vw-3rem)] text-center',
        'bg-card border border-border shadow-2xl',
        'transition-transform duration-300',
        visible ? 'scale-100' : 'scale-95',
      )}>
        <span className="text-[15px] font-semibold text-foreground leading-snug">{txt.headline}</span>
        <span className="text-[12px] text-muted-foreground/70 leading-snug">{txt.sub}</span>
      </div>
    </div>
  );
}

/* ── App ──────────────────────────────────────────────────────── */
function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = (e) => setMatches(e.matches);
    setMatches(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

function App() { return <VotePage />; }

function VotePage() {
  const isDesktop        = useMediaQuery('(min-width: 768px)');
  const [voterId]        = useState(getVoterId);
  const [pair, setPair]  = useState(() => createPair());
  const [voteCount, setVoteCount] = useState(getVoteCount);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastChoice, setLastChoice] = useState(null);
  const [reveal, setReveal] = useState(null);   // { pair, choice }
  const [revealFading, setRevealFading] = useState(false);
  const startedAt = useRef(performance.now());

  useEffect(() => {
    flushQueuedVotes().catch(console.error);
  }, []);

  const advancePair = useCallback((currentPairId) => {
    setPair(createPair(currentPairId));
    setLastChoice(null);
    startedAt.current = performance.now();
  }, []);

  // Reveal lifecycle: hold 1700ms → fade 400ms → advance
  useEffect(() => {
    if (!reveal) return;
    const fadeId    = setTimeout(() => setRevealFading(true), 1700);
    const advanceId = setTimeout(() => {
      const pairId = reveal.pair.id;
      setReveal(null);
      setRevealFading(false);
      setIsSubmitting(false);
      advancePair(pairId);
    }, 2100);
    return () => { clearTimeout(fadeId); clearTimeout(advanceId); };
  }, [reveal, advancePair]);

  const submitChoice = useCallback((choiceValue) => {
    if (!pair || isSubmitting) return;
    setIsSubmitting(true);
    setLastChoice(choiceValue);
    const capturedPair = pair;
    const nextCount = voteCount + 1;
    const row = buildVoteRow({
      pair: capturedPair, choice: choiceValue, voterId,
      voteNumber: nextCount,
      responseTimeMs: Math.max(0, Math.round(performance.now() - startedAt.current)),
    });
    setStoredVoteCount(nextCount);
    setVoteCount(nextCount);
    insertVote(row).catch(() => { queueVote(row); });
    setReveal({ pair: capturedPair, choice: choiceValue });
  }, [isSubmitting, pair, voteCount, voterId]);

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
    <main className="h-dvh flex flex-col overflow-hidden bg-background">
      <div className="flex flex-col flex-1 min-h-0 w-full max-w-[1480px] mx-auto px-3 pt-3 pb-3 md:px-10 md:pt-9 md:pb-6 lg:px-16">
        {isDesktop ? (
          <DesktopDeck pair={pair} />
        ) : (
          <MobileDeck key={pair.id} pair={pair} />
        )}

        <Choices
          isDesktop={isDesktop}
          lastChoice={lastChoice}
          isSubmitting={isSubmitting}
          onPick={submitChoice}
        />
      </div>
      <RevealOverlay reveal={reveal} fading={revealFading} />
    </main>
  );
}

/* ── Desktop: two cards side by side ───────────────────────────── */
function DesktopDeck({ pair }) {
  return (
    <section className="flex flex-1 min-h-0 gap-4" aria-label="Generated text samples">
      <SampleCard label="A" sample={pair.left} />
      <SampleCard label="B" sample={pair.right} />
    </section>
  );
}

/* ── Mobile: swipeable carousel (A ⇄ B) ────────────────────────── */
function MobileDeck({ pair }) {
  const scrollerRef = useRef(null);
  const [active, setActive] = useState(0);

  const handleScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const idx = Math.round(el.scrollLeft / el.clientWidth);
    setActive((prev) => (prev === idx ? prev : idx));
  }, []);

  const goTo = useCallback((idx) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTo({ left: idx * el.clientWidth, behavior: 'smooth' });
  }, []);

  return (
    <section className="relative flex flex-1 min-h-0 flex-col" aria-label="Generated text samples">
      <div
        ref={scrollerRef}
        onScroll={handleScroll}
        className="flex flex-1 min-h-0 overflow-x-auto overflow-y-hidden snap-x snap-mandatory no-scrollbar"
      >
        <div className="w-full shrink-0 snap-center flex min-w-0">
          <SampleCard label="A" sample={pair.left} />
        </div>
        <div className="w-full shrink-0 snap-center flex min-w-0">
          <SampleCard label="B" sample={pair.right} />
        </div>
      </div>

      {/* Swipe-to-B hint — fades once you reach B */}
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center',
          'h-7 w-7 rounded-full bg-card/90 border border-border shadow-sm text-muted-foreground',
          'transition-opacity duration-300',
          active === 0 ? 'opacity-100' : 'opacity-0',
        )}
      >
        <ChevronRight className="h-4 w-4" strokeWidth={2} />
      </div>

      {/* Pagination dots */}
      <div className="flex-none flex items-center justify-center gap-1.5 pt-2.5">
        {[0, 1].map((i) => (
          <button
            key={i}
            type="button"
            aria-label={`View sample ${i === 0 ? 'A' : 'B'}`}
            onClick={() => goTo(i)}
            className={cn(
              'h-1.5 rounded-full transition-all duration-200',
              active === i ? 'w-5 bg-foreground/70' : 'w-1.5 bg-foreground/25',
            )}
          />
        ))}
      </div>
    </section>
  );
}

/* ── SampleCard — shared by desktop + mobile ───────────────────── */
function SampleCard({ label, sample }) {
  return (
    <article className="flex flex-1 min-w-0 min-h-0 flex-col rounded-xl border border-border bg-card overflow-hidden">
      <header className="flex-none flex items-center justify-between h-10 md:h-11 pl-5 pr-2 border-b border-border">
        <span className="text-[11px] font-semibold tracking-[0.12em] uppercase font-mono text-muted-foreground/60">
          Sample {label}
        </span>
        <CopyButton text={sample.text} />
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="px-5 py-5 pb-10 md:px-8 md:py-7 md:pb-12">
          <p className="text-[14.5px] leading-[1.78] text-foreground/80 whitespace-pre-wrap">
            {sample.text}
          </p>
        </div>
      </div>
    </article>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);
  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text || '');
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1400);
    } catch { /* clipboard unavailable */ }
  }, [text]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label="Copy sample text"
      className="grid place-items-center h-7 w-7 rounded-md text-muted-foreground/45 hover:text-foreground hover:bg-accent transition-colors"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

/* ── Choices — 4 text pills on desktop, compact icons on mobile ── */
function Choices({ isDesktop, lastChoice, isSubmitting, onPick }) {
  if (isDesktop) {
    return (
      <footer className="flex-none flex items-center justify-center gap-2.5 pt-5" aria-label="Vote">
        {CHOICES.map((opt) => {
          const selected = lastChoice === opt.value && isSubmitting;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={isSubmitting}
              onClick={() => onPick(opt.value)}
              className={cn(
                'inline-flex items-center justify-center rounded-lg border h-9 px-5 text-[13px] font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none',
                selected
                  ? 'bg-primary border-primary text-primary-foreground opacity-80'
                  : 'bg-background border-input text-foreground/65 hover:bg-accent hover:border-[hsl(30_9%_83%)] hover:text-foreground disabled:opacity-35',
              )}
            >
              {opt.label}
            </button>
          );
        })}
      </footer>
    );
  }

  // Mobile: "A is better" / "B is better" expand to fill; tie + both-bad are icon-only.
  return (
    <footer className="flex-none flex items-stretch justify-center gap-2 pt-3" aria-label="Vote">
      {CHOICES.map((opt) => {
        const selected = lastChoice === opt.value && isSubmitting;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            disabled={isSubmitting}
            onClick={() => onPick(opt.value)}
            aria-label={opt.label}
            title={opt.label}
            className={cn(
              'inline-flex items-center justify-center rounded-lg border h-11 text-[13px] font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none',
              Icon ? 'w-11 shrink-0' : 'flex-1 px-3',
              selected
                ? 'bg-primary border-primary text-primary-foreground opacity-80'
                : 'bg-background border-input text-foreground/70 hover:bg-accent active:bg-accent disabled:opacity-35',
            )}
          >
            {Icon ? <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} /> : opt.label}
          </button>
        );
      })}
    </footer>
  );
}

createRoot(document.getElementById('root')).render(<App />);
