const VALID_CHOICES = new Set(['left', 'right', 'tie', 'both_bad', 'skip']);
const MAX_VOTES_PER_SESSION_24H = 200;
const MIN_DWELL_MS = 1000;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export const config = { runtime: 'edge' };

export default async function handler(request) {
    if (request.method !== 'POST') {
      return json({ error: 'method not allowed' }, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: 'invalid body' }, 400);
    }
    if (!body || typeof body !== 'object') {
      return json({ error: 'invalid body' }, 400);
    }

    const {
      session_id,
      battle_id,
      choice,
      preference_strength = null,
      rubric_version = 'preference-strength-v1',
      winner_model_id = null,
      loser_model_id = null,
      left_model_id,
      right_model_id,
      left_sample_id,
      right_sample_id,
      response_time_ms,
      app_version = 'unknown',
      payload = {},
    } = body;

    if (typeof session_id !== 'string' || !session_id || session_id.length > 128)
      return json({ error: 'invalid session_id' }, 400);
    if (typeof battle_id !== 'string' || !battle_id || battle_id.length > 256)
      return json({ error: 'invalid battle_id' }, 400);
    if (!VALID_CHOICES.has(choice))
      return json({ error: 'invalid choice' }, 400);
    if (
      typeof response_time_ms !== 'number' ||
      !Number.isFinite(response_time_ms) ||
      response_time_ms < 0 ||
      response_time_ms > 86_400_000
    )
      return json({ error: 'invalid response_time_ms' }, 400);
    if (!left_model_id || !right_model_id || !left_sample_id || !right_sample_id)
      return json({ error: 'missing model or sample fields' }, 400);
    const MAX_ID = 128;
    for (const [name, val] of [
      ['left_model_id', left_model_id], ['right_model_id', right_model_id],
      ['left_sample_id', left_sample_id], ['right_sample_id', right_sample_id],
      ['winner_model_id', winner_model_id], ['loser_model_id', loser_model_id],
    ]) {
      if (val !== null && val !== undefined && (typeof val !== 'string' || val.length > MAX_ID))
        return json({ error: `invalid ${name}` }, 400);
    }
    if (typeof app_version === 'string' && app_version.length > 128)
      return json({ error: 'invalid app_version' }, 400);
    if (typeof rubric_version === 'string' && rubric_version.length > 64)
      return json({ error: 'invalid rubric_version' }, 400);
    if (payload !== null && typeof payload === 'object' &&
        JSON.stringify(payload).length > 4096)
      return json({ error: 'payload too large' }, 400);
    if (
      preference_strength !== null &&
      (typeof preference_strength !== 'number' ||
        preference_strength < 1 ||
        preference_strength > 5)
    )
      return json({ error: 'invalid preference_strength' }, 400);

    // Minimum dwell time — catches rapid-fire scripts
    if (response_time_ms < MIN_DWELL_MS) {
      return json({ error: 'dwell time too short' }, 422);
    }

    const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/$/, '');
    const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!SUPABASE_URL || !SERVICE_KEY) {
      return json({ error: 'service not configured' }, 503);
    }

    const authHeaders = {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      'Content-Type': 'application/json',
    };

    // Rate limit: max 200 votes per session in 24 h (fail-open on error)
    try {
      const since = new Date(Date.now() - 86_400_000).toISOString();
      const rateRes = await fetch(
        `${SUPABASE_URL}/rest/v1/sample_votes?select=id` +
          `&session_id=eq.${encodeURIComponent(session_id)}` +
          `&created_at=gt.${encodeURIComponent(since)}` +
          `&limit=${MAX_VOTES_PER_SESSION_24H + 1}`,
        { headers: authHeaders },
      );
      if (rateRes.ok) {
        const rows = await rateRes.json();
        if (Array.isArray(rows) && rows.length >= MAX_VOTES_PER_SESSION_24H) {
          return json({ error: 'rate limit exceeded' }, 429);
        }
      }
    } catch (e) {
      console.error('rate-limit check failed', e);
    }

    // Insert — UNIQUE (session_id, battle_id) at the DB layer handles dedup
    const row = {
      session_id,
      battle_id,
      choice,
      preference_strength,
      rubric_version,
      winner_model_id,
      loser_model_id,
      left_model_id,
      right_model_id,
      left_sample_id,
      right_sample_id,
      response_time_ms: Math.round(response_time_ms),
      app_version,
      payload,
    };

    const insertRes = await fetch(`${SUPABASE_URL}/rest/v1/sample_votes`, {
      method: 'POST',
      headers: { ...authHeaders, Prefer: 'return=minimal' },
      body: JSON.stringify(row),
    });

    if (insertRes.status === 409) {
      // Duplicate (session_id, battle_id) — idempotent
      return json({ ok: true, duplicate: true }, 200);
    }
    if (!insertRes.ok) {
      const errBody = await insertRes.text().catch(() => '');
      console.error('Supabase insert error', insertRes.status, errBody);
      return json({ error: 'upstream error' }, 502);
    }

    return json({ ok: true }, 201);
}
