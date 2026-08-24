import { getSupabaseConfig } from '../server/supabase.js';
import {
  ACTIVE_CATALOG_VERSION,
  getCatalogSample,
} from '../server/catalog.js';

const VALID_CHOICES = new Set(['left', 'right', 'tie', 'both_bad']);
const VALID_DATASETS = new Set(['lm1b', 'owt']);
const VALID_COHORTS = new Set(['primary']);
const MAX_VOTES_PER_SESSION_24H = 200;
const MIN_DWELL_MS = 1000;
const ACTIVE_APP_VERSION = `samplebench-web/${ACTIVE_CATALOG_VERSION}`;
const ACTIVE_RUBRIC_VERSION = 'categorical-overall-v1';
const PRODUCTION_ORIGIN = 'https://samplebench.vercel.app';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
      ...extraHeaders,
    },
  });
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validViewport(value) {
  return isRecord(value) &&
    Number.isInteger(value.width) && value.width > 0 && value.width <= 10000 &&
    Number.isInteger(value.height) && value.height > 0 && value.height <= 10000;
}

function sanitizePayload(payload, dataset, cohort) {
  const sanitized = {
    dataset,
    cohort,
    study_version: ACTIVE_CATALOG_VERSION,
  };
  if (Number.isInteger(payload.vote_number) && payload.vote_number > 0 && payload.vote_number <= 1_000_000)
    sanitized.vote_number = payload.vote_number;
  if (typeof payload.client_time === 'string' && payload.client_time.length <= 64)
    sanitized.client_time = payload.client_time;
  if (payload.viewport !== undefined) {
    if (!validViewport(payload.viewport)) return null;
    sanitized.viewport = payload.viewport;
  }
  return sanitized;
}

export const config = { runtime: 'edge' };

export default async function handler(request) {
  const origin = request.headers.get('origin');
  if (origin !== PRODUCTION_ORIGIN) return json({ error: 'origin not allowed' }, 403);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204 });
  if (request.method !== 'POST') return json({ error: 'method not allowed' }, 405);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'invalid body' }, 400);
  }
  if (!isRecord(body)) return json({ error: 'invalid body' }, 400);

  // Model identity is derived server-side from opaque sample tokens. Reject
  // legacy/client-supplied model fields so the public bundle cannot influence
  // the analytical join or accidentally reintroduce unblinding.
  for (const field of ['winner_model_id', 'loser_model_id', 'left_model_id', 'right_model_id']) {
    if (Object.prototype.hasOwnProperty.call(body, field))
      return json({ error: 'model metadata must be omitted' }, 400);
  }

  const {
    session_id,
    battle_id,
    choice,
    preference_strength = null,
    rubric_version,
    left_sample_id,
    right_sample_id,
    response_time_ms,
    app_version,
    payload,
  } = body;

  if (typeof session_id !== 'string' || !UUID_RE.test(session_id))
    return json({ error: 'invalid session_id' }, 400);
  if (typeof battle_id !== 'string' || battle_id.length > 512)
    return json({ error: 'invalid battle_id' }, 400);
  if (!VALID_CHOICES.has(choice)) return json({ error: 'invalid choice' }, 400);
  if (typeof response_time_ms !== 'number' || !Number.isFinite(response_time_ms) ||
      response_time_ms < 0 || response_time_ms > 86_400_000)
    return json({ error: 'invalid response_time_ms' }, 400);
  if (typeof app_version !== 'string' || app_version !== ACTIVE_APP_VERSION)
    return json({ error: 'unsupported app_version' }, 400);
  if (typeof rubric_version !== 'string' || rubric_version !== ACTIVE_RUBRIC_VERSION)
    return json({ error: 'unsupported rubric_version' }, 400);
  if (preference_strength !== null) return json({ error: 'strength not part of active rubric' }, 400);
  if (!isRecord(payload) || JSON.stringify(payload).length > 4096)
    return json({ error: 'invalid payload' }, 400);

  const ids = [
    ['left_sample_id', left_sample_id], ['right_sample_id', right_sample_id],
  ];
  for (const [name, value] of ids) {
    if (typeof value !== 'string' || value.length === 0 || value.length > 160)
      return json({ error: `invalid ${name}` }, 400);
  }
  const dataset = payload.dataset;
  const cohort = payload.cohort;
  if (!VALID_DATASETS.has(dataset) || payload.study_version !== ACTIVE_CATALOG_VERSION)
    return json({ error: 'invalid study metadata' }, 400);
  if (!VALID_COHORTS.has(cohort)) return json({ error: 'invalid cohort' }, 400);

  const leftSample = getCatalogSample(left_sample_id);
  const rightSample = getCatalogSample(right_sample_id);
  if (!leftSample || !rightSample || leftSample.dataset !== dataset || rightSample.dataset !== dataset ||
      leftSample.modelId === rightSample.modelId ||
      !leftSample.cohorts.includes(cohort) || !rightSample.cohorts.includes(cohort))
    return json({ error: 'invalid model pairing' }, 400);
  if (battle_id !== `${cohort}::${left_sample_id}__${right_sample_id}`)
    return json({ error: 'battle_id does not match samples' }, 400);

  if (response_time_ms < MIN_DWELL_MS) return json({ error: 'dwell time too short' }, 422);

  const storedPayload = sanitizePayload(payload, dataset, cohort);
  if (!storedPayload) return json({ error: 'invalid viewport' }, 400);

  const supabase = getSupabaseConfig();
  if (!supabase) return json({ error: 'service not configured' }, 503);

  const authHeaders = {
    apikey: supabase.serviceKey,
    Authorization: `Bearer ${supabase.serviceKey}`,
    'Content-Type': 'application/json',
  };

  // Fail closed if the rate-limit read is unavailable. Accepting without it
  // would make the public endpoint an unbounded ingestion surface.
  try {
    const since = new Date(Date.now() - 86_400_000).toISOString();
    const rateRes = await fetch(
      `${supabase.baseUrl}/rest/v1/sample_votes?select=id` +
        `&session_id=eq.${encodeURIComponent(session_id)}` +
        `&created_at=gt.${encodeURIComponent(since)}` +
        `&limit=${MAX_VOTES_PER_SESSION_24H + 1}`,
      { headers: authHeaders },
    );
    if (!rateRes.ok) {
      console.error('rate-limit check returned', rateRes.status);
      return json({ error: 'service unavailable' }, 503);
    }
    const rows = await rateRes.json();
    if (!Array.isArray(rows)) return json({ error: 'service unavailable' }, 503);
    if (rows.length >= MAX_VOTES_PER_SESSION_24H) return json({ error: 'rate limit exceeded' }, 429);
  } catch (error) {
    console.error('rate-limit check failed', error);
    return json({ error: 'service unavailable' }, 503);
  }

  const left_model_id = leftSample.modelId;
  const right_model_id = rightSample.modelId;
  const winner_model_id = choice === 'left' ? left_model_id : choice === 'right' ? right_model_id : null;
  const loser_model_id = choice === 'left' ? right_model_id : choice === 'right' ? left_model_id : null;
  const canonicalBattleId = `${cohort}::${[left_sample_id, right_sample_id].sort().join('__')}`;
  const row = {
    session_id,
    battle_id: canonicalBattleId,
    choice,
    preference_strength: null,
    rubric_version,
    winner_model_id,
    loser_model_id,
    left_model_id,
    right_model_id,
    left_sample_id,
    right_sample_id,
    response_time_ms: Math.round(response_time_ms),
    app_version,
    payload: storedPayload,
  };

  try {
    const insertRes = await fetch(`${supabase.baseUrl}/rest/v1/sample_votes`, {
      method: 'POST',
      headers: { ...authHeaders, Prefer: 'return=minimal' },
      body: JSON.stringify(row),
    });
    if (insertRes.status === 409) return json({ ok: true, duplicate: true }, 200);
    if (!insertRes.ok) {
      console.error('Supabase insert error', insertRes.status);
      return json({ error: 'upstream error' }, 502);
    }
    return json({ ok: true }, 201);
  } catch (error) {
    console.error('Supabase insert failed', error);
    return json({ error: 'upstream unavailable' }, 503);
  }
}
