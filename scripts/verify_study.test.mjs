import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const dataSource = fs.readFileSync(new URL('../src/data.js', import.meta.url), 'utf8')
  .replace(/^export const /gm, 'const ')
  + '\nexport { models, studyVersion, availableDatasets };';
const { models, studyVersion, availableDatasets } = await import(
  `data:text/javascript;base64,${Buffer.from(dataSource).toString('base64')}`,
);
const release = JSON.parse(fs.readFileSync(new URL('../src/data-release.json', import.meta.url), 'utf8'));
const { CATALOG, ACTIVE_CATALOG_VERSION, isCatalogSample } = await import('../server/catalog.js');

test('active catalog is balanced, deduplicated, and release-bound', () => {
  assert.equal(studyVersion, ACTIVE_CATALOG_VERSION);
  assert.deepEqual(availableDatasets, ['lm1b', 'owt']);
  assert.equal(models.length, 57);
  assert.equal(models.reduce((total, model) => total + model.samples.length, 0), 2280);
  assert.equal(new Set(models.map((model) => model.id)).size, models.length);
  assert.equal(new Set(models.map((model) => model.corpusSha256)).size, models.length);
  assert.equal(CATALOG.size, models.length);
  assert.equal(release.release_id, ACTIVE_CATALOG_VERSION);
  assert.equal(release.model_count, models.length);
  assert.equal(release.sample_count, 2280);
  assert.deepEqual(release.dataset_counts, { lm1b: 8, owt: 49 });
  assert.equal(release.source_corpus_count, 65);
  assert.equal(release.corpora.filter((corpus) => corpus.deployment_excluded === true).length, 8);

  for (const model of models) {
    const entry = CATALOG.get(model.id);
    assert.ok(entry, `missing server catalog entry for ${model.id}`);
    assert.equal(entry.dataset, model.dataset);
    assert.equal(entry.digest, model.corpusSha256);
    assert.deepEqual(entry.sourceIds, model.samples.map((sample) => sample.sourceId));
    for (const sample of model.samples) assert.equal(isCatalogSample(model.id, sample.id), true);
  }
});

test('vote API rejects fabricated metadata and stores only sanitized payloads', async () => {
  process.env.SUPABASE_URL = 'https://db.example.test';
  process.env.SUPABASE_SECRET_KEY = 'test-secret';
  const { default: voteHandler } = await import('../api/vote.js');
  const leftModel = models.find((model) => model.dataset === 'owt');
  const rightModel = models.find((model) => model.dataset === 'owt' && model.id !== leftModel.id);
  const leftSample = leftModel.samples[0];
  const rightSample = rightModel.samples[0];
  const base = {
    session_id: '11111111-1111-4111-8111-111111111111',
    battle_id: `${leftSample.id}__${rightSample.id}`,
    choice: 'left',
    preference_strength: null,
    rubric_version: 'categorical-overall-v1',
    winner_model_id: leftModel.id,
    loser_model_id: rightModel.id,
    left_model_id: leftModel.id,
    right_model_id: rightModel.id,
    left_sample_id: leftSample.id,
    right_sample_id: rightSample.id,
    response_time_ms: 1200,
    app_version: `samplebench-web/${studyVersion}`,
    payload: {
      dataset: 'owt',
      study_version: studyVersion,
      consent_version: 'study-consent-v1',
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
    assert.equal(lastInserted.payload.page_url, undefined);

    const fabricatedSample = `${leftSample.id.slice(0, -6)}999999`;
    response = await call({ ...base, left_sample_id: fabricatedSample, battle_id: `${fabricatedSample}__${rightSample.id}` });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    response = await call({ ...base, winner_model_id: rightModel.id, loser_model_id: leftModel.id });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    response = await call({ ...base, response_time_ms: 999 });
    assert.equal(response.status, 422);
    assert.equal(inserts, 1);

    response = await call(base, 'https://attacker.example');
    assert.equal(response.status, 403);
    assert.equal(inserts, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
