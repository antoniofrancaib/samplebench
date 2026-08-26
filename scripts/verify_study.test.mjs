import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import test from 'node:test';

const dataModule = await import('../src/data.js');
const { models, studyVersion } = dataModule;
const { samples, availableDatasets } = await import('../src/data-public.js');
const release = JSON.parse(fs.readFileSync(new URL('../src/data-release.json', import.meta.url), 'utf8'));
const evidenceBytes = fs.readFileSync(new URL('./arm-evidence-r6.json', import.meta.url));
const {
  CATALOG,
  ACTIVE_CATALOG_VERSION,
  getCatalogEntry,
  getCatalogSample,
} = await import('../server/catalog.js');

test('reviewed release is balanced, safe-screened, opaque, and server-bound', () => {
  const expectedNewModels = new Map([
    ['owt_v2_plaid_256_nfe', '07278858384ee5656b6573a772ba7e338b66fdaae8bb927cad528e2a58a73196'],
    ['owt_v2_plaid_1024_nfe', '1058c429d4fa62f716c3cf08e01976e03e907ab6cb37e2361814ab434d303ecd'],
    ['owt_v2_plaid_4096_nfe', 'bfcc2512c4757d9702a2bf889d77839a27502042811e7afcc50bc8a1a6f9342f'],
    ['owt_v2_replaid_nosc_ddpm_1024_nfe', '518d2d10ce436833160df99bb88e859fee5f2682a79fed3d7431625e5d4424ad'],
  ]);
  const expectedReviewedExclusions = new Map([
    ['owt_v2_plaid_256_nfe', [6, 42, 429, 688, 798, 956, 1013]],
    ['owt_v2_plaid_1024_nfe', [22, 192, 224, 243, 266, 276, 394, 417, 459, 522, 557, 565, 577, 620, 625, 766, 793, 847, 883, 973]],
    ['owt_v2_plaid_4096_nfe', [10, 40, 48, 200, 231, 247, 250, 268, 273, 344, 419, 429, 464, 536, 539, 568, 571, 575, 586, 617, 640, 703, 712, 744, 811, 826, 836, 848, 853, 902, 927, 936, 993, 1005, 1007, 1011]],
    ['owt_v2_replaid_nosc_ddpm_1024_nfe', [17, 25, 47, 48, 57, 61, 73, 100, 101, 111, 121, 136, 150, 163, 164, 166, 174, 176, 186, 200, 203, 205, 212, 219, 223, 235, 260, 274, 279, 299, 331, 334, 338, 341, 356, 367, 369, 372, 391, 392, 404, 418, 425, 429, 455, 473, 481, 510, 514, 530, 535, 548, 551, 554, 561, 568, 592, 598, 609, 610, 620, 632, 636, 639, 647, 663, 675, 700, 707, 716, 727, 730, 734, 736, 737, 747, 755, 756, 763, 778, 783, 787, 793, 827, 835, 868, 876, 890, 892, 895, 907, 908, 910, 913, 915, 921, 925, 926, 930, 942, 956, 962, 968, 993, 999, 1000, 1008, 1010, 1022]],
  ]);
  assert.equal(studyVersion, ACTIVE_CATALOG_VERSION);
  assert.equal(studyVersion, 'dlmbench-canonical-20260826-r6');
  assert.equal(release.release_id, ACTIVE_CATALOG_VERSION);
  assert.deepEqual(availableDatasets, ['lm1b', 'owt']);
  assert.equal('availableCohorts' in dataModule, false);
  assert.equal('cohortLabels' in dataModule, false);
  assert.equal(models.length, 28);
  assert.equal(samples.length, 1120);
  assert.equal(models.reduce((total, model) => total + model.samples.length, 0), 1120);
  assert.equal(CATALOG.size, models.length);
  assert.deepEqual(release.dataset_counts, { lm1b: 7, owt: 21 });
  assert.deepEqual(release.source_dataset_counts, { lm1b: 9, owt: 63 });
  assert.deepEqual(release.cohort_model_counts, { primary: 28 });
  assert.deepEqual(Object.keys(release.cohorts), ['primary']);
  assert.equal(release.source_corpus_count, 72);
  assert.equal(release.corpora.filter((corpus) => corpus.deployment_excluded === true).length, 44);
  assert.deepEqual(release.inventory, {
    inspected_source_counts: { lm1b: 9, owt: 63 },
    deployment_counts: { lm1b: 7, owt: 21 },
    non_canonical_exclusions: [
      'lm1b_phrase_bank_1000', 'lm1b_mirror_5000', 'lm1b_periodic_k_64', 'lm1b_topk_iid_k32',
      'owt_phrase_bank_5000', 'owt_mirror_5000', 'owt_periodic_k_400', 'owt_topk_iid_k64',
    ],
  });
  assert.equal(release.selection.safety_policy, 'samplebench-public-safety-v1');
  assert.equal(
    release.arm_evidence_sha256,
    createHash('sha256').update(evidenceBytes).digest('hex'),
  );

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
    assert.deepEqual(mapped.cohorts, getCatalogEntry(mapped.modelId).cohorts);
    for (const pattern of publicSafetyPatterns)
      assert.equal(pattern.test(sample.text), false, `safety policy hit in ${sample.id}`);
  }

  for (const model of models) {
    const entry = CATALOG.get(model.id);
    assert.ok(entry, `missing server catalog entry for ${model.id}`);
    assert.deepEqual(model.cohorts, ['primary']);
    assert.deepEqual(entry.cohorts, model.cohorts);
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
  assert.equal(releaseById.size, 72);
  assert.deepEqual(
    release.corpora
      .filter((corpus) => corpus.safety_screen.reviewed_source_exclusions.length > 0)
      .map((corpus) => corpus.generator_id)
      .sort(),
    [...expectedReviewedExclusions.keys()].sort(),
  );
  for (const model of models) {
    const corpus = releaseById.get(model.id);
    assert.equal(corpus.selected_sample_count, 40);
    assert.equal(corpus.safety_screen.policy, 'samplebench-public-safety-v1');
    assert.equal(corpus.selected_source_ids.length, 40);
    assert.equal(corpus.arm_evidence.status, 'included');
    assert.deepEqual(corpus.arm_evidence.cohorts, model.cohorts);
    assert.ok(corpus.arm_evidence.paper.url.startsWith('https://'));
    assert.ok(corpus.arm_evidence.checkpoint_record);
    assert.equal(corpus.manifest_identity_matches_arm.generator, true);
    assert.equal(corpus.manifest_identity_matches_arm.nfe, true);
    assert.deepEqual(
      corpus.safety_screen.reviewed_source_exclusions.map(({ source_id }) => source_id).sort((a, b) => a - b),
      [...(expectedReviewedExclusions.get(corpus.generator_id) ?? [])].sort((a, b) => a - b),
    );
    if (corpus.arm_evidence.provenance_tier === 'A' || corpus.arm_evidence.provenance_tier === 'B') {
      assert.equal(corpus.manifest_identity_matches_arm.checkpoint, true);
      assert.equal(corpus.manifest_identity_matches_arm.checkpoint_revision, true);
      assert.equal(corpus.manifest_identity_matches_arm.checkpoint_digest, true);
    } else {
      assert.equal(corpus.manifest_identity_matches_arm.checkpoint, null);
      assert.equal(corpus.manifest_identity_matches_arm.checkpoint_revision, null);
      assert.equal(corpus.manifest_identity_matches_arm.checkpoint_digest, null);
    }
  }

  for (const [modelId, digest] of expectedNewModels) {
    const model = models.find(({ id }) => id === modelId);
    assert.ok(model, `missing newly public model ${modelId}`);
    assert.equal(model.dataset, 'owt');
    assert.equal(model.family, modelId.includes('replaid') ? 'replaid' : 'plaid');
    assert.deepEqual(model.cohorts, ['primary']);
    assert.equal(model.corpusSha256, digest);
    assert.equal(model.samples.length, 40);
    const corpus = releaseById.get(modelId);
    assert.equal(corpus.arm_evidence.status, 'included');
  }
  const newlyPublicSamples = models
    .filter(({ id }) => expectedNewModels.has(id))
    .flatMap(({ samples: modelSamples }) => modelSamples);
  assert.equal(newlyPublicSamples.length, 160);
  assert.equal(models.some(({ id }) => id.includes('candi')), false);
  for (const modelId of ['owt_v2_cobit_m_128_nfe', 'owt_v2_cobit_s_128_nfe', 'owt_v2_cobit_s_512_nfe']) {
    const corpus = release.corpora.find(({ generator_id }) => generator_id === modelId);
    assert.ok(corpus, `missing inventory-only CoBit arm ${modelId}`);
    assert.equal(corpus.deployment_excluded, true);
    assert.equal(corpus.arm_evidence.status, 'excluded');
    assert.deepEqual(corpus.arm_evidence.cohorts, []);
  }
  const replaidCorpus = releaseById.get('owt_v2_replaid_nosc_ddpm_1024_nfe');
  assert.equal(replaidCorpus.source_type, 'dlmbench_author_provided');
  assert.equal(replaidCorpus.arm_evidence.provenance_tier, 'C');
  assert.match(replaidCorpus.arm_evidence.limitations.join(' '), /not recomputed/i);
  for (const modelId of ['owt_v2_plaid_256_nfe', 'owt_v2_plaid_1024_nfe', 'owt_v2_plaid_4096_nfe']) {
    const plaidCorpus = releaseById.get(modelId);
    assert.equal(plaidCorpus.source_type, 'dlmbench_historical_git_recovery');
    assert.equal(plaidCorpus.arm_evidence.provenance_tier, 'historical-recovery');
    assert.match(plaidCorpus.arm_evidence.limitations.join(' '), /Git-recovered/i);
    assert.match(plaidCorpus.arm_evidence.limitations.join(' '), /no inference or regeneration/i);
  }

  assert.equal(new Set(models.map((model) => model.corpusSha256)).size, models.length);

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
  const left = samples.find((sample) => getCatalogSample(sample.id)?.modelId === 'owt_v2_plaid_256_nfe');
  const leftMapped = getCatalogSample(left.id);
  const right = samples.find((sample) => {
    if (sample.dataset !== 'owt' || sample.group === left.group) return false;
    return getCatalogSample(sample.id) !== null;
  });
  const rightMapped = getCatalogSample(right.id);
  const cohort = 'primary';
  assert.deepEqual(leftMapped.cohorts, [cohort]);
  assert.deepEqual(rightMapped.cohorts, [cohort]);
  const base = {
    session_id: '11111111-1111-4111-8111-111111111111',
    battle_id: `${cohort}::${left.id}__${right.id}`,
    choice: 'left',
    preference_strength: null,
    rubric_version: 'categorical-overall-v1',
    left_sample_id: left.id,
    right_sample_id: right.id,
    response_time_ms: 1200,
    app_version: `samplebench-web/${studyVersion}`,
    payload: {
      dataset: 'owt',
      cohort,
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
    assert.equal(lastInserted.battle_id, `${cohort}::${[left.id, right.id].sort().join('__')}`);
    assert.equal(lastInserted.payload.cohort, cohort);
    assert.equal(lastInserted.payload.page_url, undefined);
    assert.equal(lastInserted.payload.consent_version, undefined);

    const fabricated = 's-000000000000000000000000';
    response = await call({ ...base, left_sample_id: fabricated, battle_id: `${cohort}::${fabricated}__${right.id}` });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    response = await call({ ...base, left_model_id: leftMapped.modelId });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    response = await call({ ...base, response_time_ms: 999 });
    assert.equal(response.status, 422);
    assert.equal(inserts, 1);

    response = await call({ ...base, choice: 'skip' });
    assert.equal(response.status, 400);
    assert.equal(inserts, 1);

    const disallowedCohort = 'secondary';
    response = await call({
      ...base,
      battle_id: `${disallowedCohort}::${left.id}__${right.id}`,
      payload: { ...base.payload, cohort: disallowedCohort },
    });
    assert.equal(response.status, 400);
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

    globalThis.fetch = async (url) => {
      if (String(url).includes('/rest/v1/sample_votes?')) return new Response('', { status: 503 });
      throw new Error('insert must not run after rate-limit read failure');
    };
    response = await call(base);
    assert.equal(response.status, 503);

    globalThis.fetch = async (url) => {
      if (String(url).includes('/rest/v1/sample_votes?')) {
        return Response.json(Array.from({ length: 200 }, (_, id) => ({ id })));
      }
      throw new Error('insert must not run after rate limit');
    };
    response = await call(base);
    assert.equal(response.status, 429);

    globalThis.fetch = async (url) => {
      if (String(url).includes('/rest/v1/sample_votes?')) return Response.json([]);
      return new Response('', { status: 409 });
    };
    response = await call(base);
    assert.equal(response.status, 200);
    assert.equal((await response.json()).duplicate, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('leaderboard isolates the active Primary release and rejects unknown cohorts', async () => {
  process.env.SUPABASE_URL = 'https://db.example.test';
  process.env.SUPABASE_SECRET_KEY = 'test-secret';
  const { default: leaderboardHandler } = await import('../api/leaderboard.js');
  const left = models.find((model) => model.dataset === 'owt' && model.cohorts.includes('primary'));
  const right = models.find((model) => model.dataset === 'owt' && model.id !== left.id && model.cohorts.includes('primary'));
  const upstreamRows = [
    {
      winner_model_id: left.id,
      loser_model_id: right.id,
      left_model_id: left.id,
      right_model_id: right.id,
      choice: 'left',
      payload: { cohort: 'primary' },
    },
    {
      winner_model_id: right.id,
      loser_model_id: left.id,
      left_model_id: left.id,
      right_model_id: right.id,
      choice: 'right',
      payload: { cohort: 'secondary' },
    },
  ];
  let requestedUrl = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    requestedUrl = String(url);
    return Response.json(upstreamRows);
  };
  const call = async (url) => {
    let payload = null;
    const headers = {};
    const response = {
      statusCode: 200,
      setHeader(name, value) { headers[name] = value; },
      end(value) { payload = JSON.parse(value); },
    };
    await leaderboardHandler({ url }, response);
    return { status: response.statusCode, headers, payload };
  };
  try {
    let result = await call('/api/leaderboard?dataset=owt&cohort=primary');
    assert.equal(result.status, 200);
    assert.equal(result.payload.total_votes, 1);
    assert.equal(result.payload.cohort, 'primary');
    assert.equal(result.payload.models.length, 2);
    assert.match(requestedUrl, /app_version=eq\.samplebench-web%2Fdlmbench-canonical-20260826-r6/);

    requestedUrl = '';
    result = await call('/api/leaderboard?dataset=owt&cohort=unknown');
    assert.equal(result.status, 400);
    assert.equal(requestedUrl, '');
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
  assert.equal(fs.readFileSync(new URL('../api/vote.js', import.meta.url), 'utf8').includes("'skip'"), false);
  assert.equal(source.includes('Choose the better sample overall'), false);
  assert.match(source, /headline: leftModelName/);
  assert.match(source, /headline: rightModelName/);
  assert.match(source, /headline: 'Equally good'/);
  assert.match(source, /headline: 'Both bad'/);
  assert.equal(source.includes('function CohortToggle'), false);
  assert.equal(source.includes('STORAGE_KEYS.cohort'), false);
  assert.match(source, /sample-raw/);
});
