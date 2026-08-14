import { getSupabaseConfig } from '../server/supabase.js';

const ACTIVE_APP_VERSION = 'samplebench-web/dlmbench-canonical-20260814-r1';
const VALID_DATASETS = new Set(['lm1b', 'owt']);

function json(response, data, status = 200, headers = {}) {
  response.statusCode = status;
  response.setHeader('Content-Type', 'application/json');
  for (const [name, value] of Object.entries(headers)) response.setHeader(name, value);
  response.end(JSON.stringify(data));
}

export default async function handler(request, response) {
  const supabase = getSupabaseConfig();
  if (!supabase) return json(response, { error: 'service not configured' }, 503);

  const dataset = new URL(request.url, 'http://localhost').searchParams.get('dataset') || 'owt';
  if (!VALID_DATASETS.has(dataset)) return json(response, { error: 'invalid dataset' }, 400);

  const headers = {
    apikey: supabase.serviceKey,
    Authorization: `Bearer ${supabase.serviceKey}`,
  };

  const ROW_CAP = 20000;
  let rows;
  try {
    const res = await fetch(
      `${supabase.baseUrl}/rest/v1/sample_votes` +
        `?select=winner_model_id,loser_model_id,left_model_id,right_model_id,choice` +
        `&app_version=eq.${encodeURIComponent(ACTIVE_APP_VERSION)}` +
        `&limit=${ROW_CAP}`,
      { headers },
    );
    if (!res.ok) {
      console.error('Supabase leaderboard request failed', res.status);
      return json(response, { error: 'upstream error' }, 502);
    }
    rows = await res.json();
  } catch (error) {
    const cause = error instanceof Error ? error.cause : null;
    console.error('Supabase leaderboard fetch failed', {
      name: error instanceof Error ? error.name : typeof error,
      message: error instanceof Error ? error.message : String(error),
      causeCode: cause && typeof cause === 'object' && 'code' in cause ? cause.code : null,
      causeMessage: cause instanceof Error ? cause.message : null,
    });
    return json(response, { error: 'fetch failed' }, 502);
  }

  const stats = new Map();
  function get(id) {
    if (!id) return null;
    if (!stats.has(id)) stats.set(id, { model_id: id, wins: 0, losses: 0, ties: 0, both_bad: 0, battles: 0 });
    return stats.get(id);
  }

  const datasetRows = rows.filter(({ left_model_id, right_model_id }) =>
    left_model_id?.startsWith(`${dataset}_`) && right_model_id?.startsWith(`${dataset}_`)
  );

  for (const { winner_model_id, loser_model_id, left_model_id, right_model_id, choice } of datasetRows) {
    if (choice === 'left' || choice === 'right') {
      const w = get(winner_model_id), l = get(loser_model_id);
      if (w) { w.wins++; w.battles++; }
      if (l) { l.losses++; l.battles++; }
    } else if (choice === 'tie') {
      const a = get(left_model_id), b = get(right_model_id);
      if (a) { a.ties++; a.battles++; }
      if (b) { b.ties++; b.battles++; }
    } else if (choice === 'both_bad') {
      const a = get(left_model_id), b = get(right_model_id);
      if (a) { a.both_bad++; a.battles++; }
      if (b) { b.both_bad++; b.battles++; }
    }
  }

  const models = [...stats.values()]
    .map((m) => ({
      ...m,
      win_rate: m.wins + m.losses > 0 ? m.wins / (m.wins + m.losses) : null,
    }))
    .sort((a, b) => {
      if (a.win_rate === null && b.win_rate === null) return b.battles - a.battles;
      if (a.win_rate === null) return 1;
      if (b.win_rate === null) return -1;
      return b.win_rate - a.win_rate || b.battles - a.battles;
    });

  return json(
    response,
    { total_votes: datasetRows.length, dataset, study_version: ACTIVE_APP_VERSION, models },
    200,
    { 'Cache-Control': 'public, s-maxage=30, stale-while-revalidate=60' },
  );
}
