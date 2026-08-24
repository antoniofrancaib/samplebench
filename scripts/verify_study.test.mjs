import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const { models, studyVersion } = await import('../src/data.js');
const { samples, availableDatasets } = await import('../src/data-public.js');
const release = JSON.parse(fs.readFileSync(new URL('../src/data-release.json', import.meta.url), 'utf8'));
const {
  CATALOG,
  ACTIVE_CATALOG_VERSION,
  getCatalogEntry,
  getCatalogSample,
} = await import('../server/catalog.js');

test('reviewed release is balanced, safe-screened, opaque, and server-bound', () => {
  assert.equal(studyVersion, ACTIVE_CATALOG_VERSION);
  assert.equal(release.release_id, ACTIVE_CATALOG_VERSION);
  assert.deepEqual(availableDatasets, ['lm1b', 'owt']);
  assert.equal(models.length, 57);
  assert.equal(samples.length, 2280);
  assert.equal(models.reduce((total, model) => total + model.samples.length, 0), 2280);
  assert.equal(CATALOG.size, models.length);
  assert.deepEqual(release.dataset_counts, { lm1b: 8, owt: 49 });
  assert.equal(release.source_corpus_count, 65);
  assert.equal(release.corpora.filter((corpus) => corpus.deployment_excluded === true).length, 8);
  assert.equal(release.selection.safety_policy, 'samplebench-public-safety-v1');

  const publicIds = new Set();
  const publicSafetyPatterns = [
    /�/,
    /\b(?:https?:\/\/|www\.)\S+/i,
    /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
    /(?:\+\d{1,3}[ .-]?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,4}[ .-]\d{3,4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b)/,
    /<\/?[a-z][^>]*>/i,
    /\b(?:porn|pornographic|blowjob|masturbat\w*|semen|ejaculat\w*|genital\w*|penetrat\w*|nude|nudity|anal sex|oral sex|intercourse|prostitut\w*|rape\w*|molest\w*|pedophil\w*|child porn)\b/i,
    /\b(?:nigger|nigga|faggot|kike|chink|spic|wetback|retard(?:ed)?)\b/i,
    /\b(?:suicide|suicidal|self[- ]harm|kill myself|take my own life)\b/i,
    /\b(?:beheaded|decapitat\w*|dismember\w*|gore\w*|mutilat\w*|disembowel\w*|bloodbath|massacre\w*|tortur\w*)\b/i,
    /\b(?:fuck(?:ing|ed)?|shit|cunt|slut|whore|bitch|dick|pussy|cock|asshole|motherfucker)\b/i,
  ];
  for (const sample of samples) {
    assert.match(sample.id, /^s-[0-9a-f]{24}$/);
    assert.match(sample.group, /^g-[0-9a-f]{16}$/);
    assert.ok(!publicIds.has(sample.id), `duplicate public sample ${sample.id}`);
    publicIds.add(sample.id);
    const mapped = getCatalogSample(sample.id);
    assert.ok(mapped, `unmapped public sample ${sample.id}`);
    assert.equal(mapped.dataset, sample.dataset);
    assert.equal(getCatalogEntry(mapped.modelId).dataset, sample.dataset);
    assert.equal(getCatalogEntry(mapped.modelId).publicGroupId, sample.group);
    for (const pattern of publicSafetyPatterns)
      assert.equal(pattern.test(sample.text), false, `safety policy hit in ${sample.id}`);
  }

  for (const model of models) {
    const entry = CATALOG.get(model.id);
    assert.ok(entry, `missing server catalog entry for ${model.id}`);
    assert.equal(entry.sourceIds.length, 40);
    assert.equal(entry.sampleIds.length, 40);
    assert.deepEqual(entry.sourceIds, model.samples.map((sample) => sample.sourceId));
    assert.deepEqual(entry.sampleIds, model.samples.map((sample) => sample.id));
    for (const sample of model.samples) {
      assert.equal(getCatalogSample(sample.id)?.modelId, model.id);
      assert.equal(getCatalogSample(sample.id)?.sourceId, sample.sourceId);
    }
  }

  const releaseById = new Map(release.corpora.map((corpus) => [corpus.generator_id, corpus]));
  for (const model of models) {
    const corpus = releaseById.get(model.id);
    assert.equal(corpus.selected_sample_count, 40);
    assert.equal(corpus.safety_screen.policy, 'samplebench-public-safety-v1');
    assert.equal(corpus.selected_source_ids.length, 40);
  }

  // The public module must not carry model labels or generator IDs.
  const publicSource = fs.readFileSync(new URL('../src/data-public.js', import.meta.url), 'utf8');
  assert.equal(publicSource.includes('Duo LM1B'), false);
  assert.equal(publicSource.includes('owt_v2_sedd_8_nfe'), false);
  assert.equal(publicSource.includes('corpusSha256'), false);
});

test('vote API derives model metadata, canonicalizes pairs, and rejects forged input', async () => {
  process.env.SUPABASE_URL = 'https://db.example.test';
  process.env.SUPABASE_SECRET_KEY = 'test-secret';
  const { default: voteHandler } = await import('../api/vote.js');
  const left = samples.find((sample) => sample.dataset === 'owt');
  const right = samples.find((sample) => sample.dataset === 'owt' && sample.group !== left.group);
  const leftMapped = getCatalogSample(left.id);
  const rightMapped = getCatalogSample(right.id);
  const base = {
    session_id: '11111111-1111-4111-8111-111111111111',
    battle_id: `${left.id}__${right.id}`,
    choice: 'left',
    preference_strength: null,
    rubric_version: 'categorical-overall-v1',
    left_sample_id: left.id,
    right_sample_id: right.id,
    response_time_ms: 1200,
    app_version: `samplebench-web/${studyVersion}`,
    payload: {
      dataset: 'owt',
      study_version: studyVersion,
      viewport: { width: 390, height: 844 },
      page_url: 'https://evil.example/?secret=should-not-be-stored',
    },
  };
  let inserts = 0;
  let lastInserted = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    if (String(url).includes('/rest/v1/sample_votes?')) return new Response('[]', { status: 200 });
    inserts += 1;
    lastInserted = JSON.parse(options.body);
    return new Response('', { status: 201 });
  };
  const call = async (body, origin = 'https://samplebench.vercel.app') => voteHandler(new Request(
    'https://samplebench.vercel.app/api/vote',
    { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin }, body: JSON.stringify(body) },
  ));

  try {
    let response = await call(base);
    assert.equal(response.status, 201);
    assert.equal(inserts, 1);
    assert.equal(lastInserted.left_model_id, leftMapped.modelId);
    assert.equal(lastInserted.right_model_id, rightMapped.modelId);
    assert.equal(lastInserted.winner_model_id, leftMapped.modelId);
    assert.equal(lastInserted.loser_model_id, rightMapped.modelId);
    assert.equal(lastInserted.battle_id, [left.id, right.id].sort().join('__'));
    assert.equal(lastInserted.payload.page_url, undefined);
    assert.equal(lastInserted.payload.consent_version, undefined);

    const fabricated = 's-000000000000000000000000';
    response = await call({ ...base, left_sample_id: fabricated, battle_id: `${fabricated}__${right.id}` });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    response = await call({ ...base, left_model_id: leftMapped.modelId });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    response = await call({ ...base, response_time_ms: 999 });
    assert.equal(response.status, 422);
    assert.equal(inserts, 1);

    response = await call(base, 'https://attacker.example');
    assert.equal(response.status, 403);
    assert.equal(inserts, 1);

    response = await voteHandler(new Request(
      'https://samplebench.vercel.app/api/vote',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(base) },
    ));
    assert.equal(response.status, 403);
    assert.equal(inserts, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('public UI keeps the requested routes and four-choice voting flow', () => {
  const source = fs.readFileSync(new URL('../src/main.jsx', import.meta.url), 'utf8');
  assert.match(source, /<SamplesIndexPage onNavigate=\{navigate\}/);
  assert.match(source, /<LeaderboardPage onNavigate=\{navigate\}/);
  assert.equal(source.includes('StudyConsentPage'), false);
  assert.equal(source.includes('CollectionClosedPage'), false);
  assert.equal(source.includes("value: 'skip'"), false);
  assert.equal(source.includes("s: 'skip'"), false);
  assert.equal(source.includes('Choose the better sample overall'), false);
  assert.match(source, /headline: leftModelName/);
  assert.match(source, /headline: rightModelName/);
  assert.match(source, /headline: 'Equally good'/);
  assert.match(source, /headline: 'Both bad'/);
});
