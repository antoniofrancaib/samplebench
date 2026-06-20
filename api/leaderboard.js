export const config = { runtime: 'edge' };

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export default async function handler() {
  const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/$/, '');
  const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!SUPABASE_URL || !SERVICE_KEY) return json({ error: 'service not configured' }, 503);

  const headers = {
    apikey: SERVICE_KEY,
    Authorization: `Bearer ${SERVICE_KEY}`,
  };

  const ROW_CAP = 20000;
  let rows;
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/sample_votes` +
        `?select=winner_model_id,loser_model_id,left_model_id,right_model_id,choice` +
        `&limit=${ROW_CAP}`,
      { headers },
    );
    if (!res.ok) return json({ error: 'upstream error' }, 502);
    rows = await res.json();
  } catch {
    return json({ error: 'fetch failed' }, 502);
  }

  const stats = new Map();
  function get(id) {
    if (!id) return null;
    if (!stats.has(id)) stats.set(id, { model_id: id, wins: 0, losses: 0, ties: 0, both_bad: 0, battles: 0 });
    return stats.get(id);
  }

  for (const { winner_model_id, loser_model_id, left_model_id, right_model_id, choice } of rows) {
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

  return new Response(JSON.stringify({ total_votes: rows.length, models }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, s-maxage=30, stale-while-revalidate=60',
    },
  });
}
