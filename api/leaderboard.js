import { getSupabaseConfig } from '../server/supabase.js';
import { ACTIVE_CATALOG_VERSION, getCatalogEntry } from '../server/catalog.js';

const ACTIVE_APP_VERSION = `samplebench-web/${ACTIVE_CATALOG_VERSION}`;
const VALID_DATASETS = new Set(['lm1b', 'owt']);
const PUBLIC_RESULTS_ENABLED = process.env.PUBLIC_RESULTS_ENABLED === 'true';
const PAGE_SIZE = 1000;
const MAX_ROWS = 100_000;

function json(response, data, status = 200, headers = {}) {
  response.statusCode = status;
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  for (const [name, value] of Object.entries(headers)) response.setHeader(name, value);
  response.end(JSON.stringify(data));
}

export default async function handler(request, response) {
  if (!PUBLIC_RESULTS_ENABLED) {
    return json(response, { error: 'results unavailable while collection is open' }, 404);
  }

  const supabase = getSupabaseConfig();
  if (!supabase) return json(response, { error: 'service not configured' }, 503);

  const dataset = new URL(request.url, 'http://localhost').searchParams.get('dataset') || 'owt';
  if (!VALID_DATASETS.has(dataset)) return json(response, { error: 'invalid dataset' }, 400);

  const headers = {
    apikey: supabase.serviceKey,
    Authorization: `Bearer ${supabase.serviceKey}`,
  };
  const rows = [];

  try {
    for (let offset = 0; offset < MAX_ROWS; offset += PAGE_SIZE) {
      const res = await fetch(
        `${supabase.baseUrl}/rest/v1/sample_votes` +
          `?select=winner_model_id,loser_model_id,left_model_id,right_model_id,choice` +
          `&app_version=eq.${encodeURIComponent(ACTIVE_APP_VERSION)}` +
          `&limit=${PAGE_SIZE}&offset=${offset}`,
        { headers },
      );
      if (!res.ok) {
        console.error('Supabase leaderboard request failed', res.status);
        return json(response, { error: 'upstream error' }, 502);
      }
      const page = await res.json();
      if (!Array.isArray(page)) return json(response, { error: 'invalid upstream response' }, 502);
      rows.push(...page);
      if (page.length < PAGE_SIZE) break;
      if (rows.length >= MAX_ROWS) {
        console.error('leaderboard row cap reached');
        return json(response, { error: 'leaderboard too large' }, 503);
      }
    }
  } catch (error) {
    console.error('Supabase leaderboard fetch failed', error);
    return json(response, { error: 'fetch failed' }, 502);
  }

  const stats = new Map();
  function get(id) {
    if (!id) return null;
    if (!stats.has(id)) stats.set(id, { model_id: id, wins: 0, losses: 0, ties: 0, both_bad: 0, battles: 0 });
    return stats.get(id);
  }

  const datasetRows = rows.filter(({ left_model_id, right_model_id }) => {
    const left = getCatalogEntry(left_model_id);
    const right = getCatalogEntry(right_model_id);
    return left?.dataset === dataset && right?.dataset === dataset && left_model_id !== right_model_id;
  });

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
    .map((model) => ({
      ...model,
      decisive_votes: model.wins + model.losses,
      win_rate: model.wins + model.losses > 0 ? model.wins / (model.wins + model.losses) : null,
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
