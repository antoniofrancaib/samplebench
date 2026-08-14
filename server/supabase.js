function cleanEnvironmentValue(value) {
  return value?.replace(/\\n+$/g, '').trim();
}

export function getSupabaseConfig() {
  const serviceKey =
    cleanEnvironmentValue(process.env.SUPABASE_SECRET_KEY) ||
    cleanEnvironmentValue(process.env.SUPABASE_SERVICE_ROLE_KEY);
  const rawUrl = cleanEnvironmentValue(process.env.SUPABASE_URL);

  if (!rawUrl || !serviceKey) return null;

  try {
    const url = new URL(rawUrl);
    if (url.protocol !== 'https:') return null;
    return { baseUrl: url.href.replace(/\/$/, ''), serviceKey };
  } catch {
    return null;
  }
}
