/* Development-only acceptance of the actual bundled page; APIs use synthetic DTOs. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright-core');

const base = new URL(process.env.FACET_DASHBOARD_TEST_URL || 'http://127.0.0.1:18084/');
assert.equal(base.hostname, '127.0.0.1', 'Use an isolated loopback test server.');
assert.equal(base.pathname, '/');
const timestamp = '2026-10-09T11:00:00.000000+08:00';
const families = ['status', 'progress', 'issues', 'rules', 'activity', 'diagnostics'];
const apiPaths = families.map(name => `/api/v1/${name}`);
const fixture = () => {
  const role = (name, mode) => ({role: name, mode, auth_state: 'verified', last_verified_at: timestamp, freshness: 'fresh'});
  const values = {
    status: {phase: 'incremental', health: 'healthy', source: role('source', 'source_readonly'), target: role('target', 'target_insert_readonly'), last_poll_at: timestamp, last_verified_insert_at: timestamp, heartbeat_at: timestamp},
    progress: {epoch: {kind: 'initial_backfill', state: 'completed', started_at: timestamp}, discovery_complete: true, scanned_threads: 777, discovered_threads: 777, completed_threads: 777, known_message_total: 4234, confirmed_messages: 4340, jobs: {queued: 0, claimed: 0, retry_wait: 0, blocked: 0, needs_attention: 0, completed: 9010, cancelled: 3, source_missing: 0, failed: 0}, oldest_runnable_job_age_seconds: null, verified_last_hour: null, verified_last_day: null, rate: {value: null, unit: 'messages_per_second', window_seconds: 60, sample_count: 0}, latency: {p50: null, p95: null, unit: 'milliseconds', window_seconds: 60, sample_count: 0}},
    issues: {groups: []},
    rules: {entries: [{kind: 'allow_sender', value: 'sender@example.test', enabled: true}, {kind: 'action_label_add_sender', value: 'Facet/AddSender', enabled: true}]},
    activity: {entries: [{rule_kind: 'allow_sender', rule_value: 'sender@example.test', matched_count: 4, observed_at: timestamp}]},
    diagnostics: {app_version: '0.1.0', commit_sha: '0123456789abcdef0123456789abcdef01234567', schema_version: 5, sync_owner_count: 1, db_readable: 'ok', db_writable: 'ok', source_mode: 'readonly', source_scope_ready: 'ok', target_scope_ready: 'ok', memory_pressure: 'normal', disk_pressure: 'normal', heartbeat_at: timestamp, checked_at: timestamp}
  };
  return Object.fromEntries(families.map(name => [name, {data: values[name], schema_version: 1, sampled_at: timestamp, freshness: 'fresh', age_seconds: 0, scope: 'projection'}]));
};

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.FACET_BROWSER_EXECUTABLE || undefined, args: ['--no-sandbox']});
  try {
    for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
      const context = await browser.newContext({viewport});
      const page = await context.newPage();
      let snapshots = fixture(), failure = null;
      const requests = [], errors = [];
      page.on('request', request => requests.push({url: request.url(), method: request.method()}));
      page.on('pageerror', () => errors.push('page_error'));
      await page.route(`${base.origin}/api/v1/*`, async route => {
        const family = new URL(route.request().url()).pathname.split('/').pop();
        assert.ok(families.includes(family));
        if (failure === 'network' && family === 'issues') return route.abort();
        if (failure === 'http' && family === 'progress') return route.fulfill({status: 503, body: '{}'});
        if (failure === 'malformed' && family === 'diagnostics') return route.fulfill({body: '{'});
        if (failure === 'timeout' && family === 'issues') return;
        await route.fulfill({contentType: 'application/json', body: JSON.stringify(snapshots[family])});
      });
      const text = id => page.locator(`#${id}`).innerText();
      const expectText = async (id, value) => {
        await page.waitForFunction(({id, value}) => document.getElementById(id).textContent === value, {id, value});
      };
      const refresh = async () => {
        await page.locator('#refresh').click();
        await page.waitForFunction(() => !document.getElementById('refresh').disabled);
      };
      const expectUnknown = async () => {
        await expectText('health', 'Unknown');
        for (const id of ['confirmed', 'queued', 'attention', 'job-queued', 'job-failed']) assert.equal(await text(id), 'Unknown');
        assert.equal(await page.locator('#health').getAttribute('class'), 'badge');
        assert.match(await text('issues'), /Unknown/);
      };
      await page.goto(base.href);
      await expectText('confirmed', '4340');
      assert.equal(await text('health'), 'Healthy');
      assert.equal(await text('candidates'), '4234');
      assert.equal(await text('rate'), 'Unknown');
      assert.equal(await text('latency'), 'Unknown');
      assert.equal(await text('source-binding'), 'Verified');
      assert.equal(await text('commit-sha'), '0123456789abcdef0123456789abcdef01234567');
      assert.match(await text('activity'), /sender@example\.test.*4 messages/);
      assert.match(await page.locator('body').innerText(), /Source binding verified/);
      assert.doesNotMatch(await page.locator('body').innerText(), /\d+(?:\.\d+)?%|ETA/);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      if (process.env.FACET_BROWSER_SCREENSHOT_DIR) await page.screenshot({path: `${process.env.FACET_BROWSER_SCREENSHOT_DIR}/dashboard-${viewport.width}.png`, fullPage: true});

      // Unknown discovery, backlog, unit-bearing real samples, gap recovery.
      snapshots.progress.data.discovery_complete = false;
      snapshots.progress.data.known_message_total = null;
      snapshots.progress.data.jobs.queued = 12;
      snapshots.progress.data.jobs.retry_wait = 2;
      snapshots.progress.data.epoch = {kind: 'history_gap', state: 'catching_up', started_at: timestamp};
      snapshots.progress.data.rate = {value: 2.5, unit: 'messages_per_second', window_seconds: 60, sample_count: 15};
      snapshots.progress.data.latency = {p50: 100, p95: 500, unit: 'milliseconds', window_seconds: 60, sample_count: 15};
      snapshots.status.data.phase = 'recovering';
      snapshots.status.data.health = 'degraded';
      await refresh();
      assert.equal(await text('queued'), '12');
      assert.equal(await text('job-retry_wait'), '2');
      assert.equal(await text('candidates'), 'Unknown');
      assert.match(await text('discovery'), /total unknown/);
      assert.equal(await text('epoch-kind'), 'History gap');
      assert.equal(await text('phase'), 'Recovering');
      assert.match(await text('rate'), /2.5 messages\/s.*15 samples.*60 s window/);
      assert.match(await text('latency'), /100 \/ 500 ms/);

      // Authorization and partial completion remain visible, never all-success.
      snapshots.status.data.health = 'blocked';
      snapshots.status.data.target.auth_state = 'auth_required';
      snapshots.progress.data.epoch.state = 'completed_with_issues';
      snapshots.progress.data.jobs.needs_attention = 1;
      snapshots.issues.data.groups = [{code: 'target_auth_required', error_class: 'dependency', role: 'target', count: 1, first_at: timestamp, last_at: timestamp, retryable: true, next_retry_at: null, suggestion: 'authorize_target'}];
      await refresh();
      assert.equal(await text('health'), 'Blocked');
      assert.equal(await text('target-binding'), 'Authorization required');
      assert.equal(await text('epoch-state'), 'Completed with issues');
      assert.equal(await text('attention'), '1');
      assert.match(await text('issues'), /target_auth_required.*Target.*1/);
      assert.match(await text('issues'), /Reauthorize Target/);

      // Any stale family, even while status says Healthy, clears unsafe conclusions.
      for (const family of families) {
        snapshots = fixture(); snapshots[family].freshness = 'stale';
        await refresh(); await expectUnknown();
      }
      snapshots = fixture(); snapshots.issues.freshness = 'unavailable'; snapshots.issues.age_seconds = null;
      await refresh(); await expectUnknown();
      snapshots = fixture(); snapshots.progress.age_seconds = 31;
      await refresh(); await expectUnknown();
      for (const mode of ['network', 'http', 'malformed']) {
        snapshots = fixture(); failure = mode;
        await refresh(); await expectUnknown();
        assert.match(await text('freshness'), /refresh failed/);
        failure = null;
        await refresh(); await expectText('health', 'Healthy');
      }

      // Negative malformed enum fixture is never echoed into DOM or later requests.
      snapshots = fixture(); snapshots.status.data.health = 'PRIVATE_NEGATIVE_SENTINEL';
      await refresh(); await expectUnknown();
      assert.doesNotMatch(await page.content(), /PRIVATE_NEGATIVE_SENTINEL/);
      snapshots = fixture(); snapshots.status.data.target.freshness = 'stale';
      await refresh(); await expectUnknown();
      snapshots = fixture(); snapshots.progress.data.rate.value = 0; // Still no samples.
      await refresh(); await expectText('health', 'Healthy');
      assert.equal(await text('rate'), 'Unknown');

      // Held fetch is bounded; no overlapping manual/automatic batches.
      failure = 'timeout';
      const before = requests.filter(request => request.url.endsWith('/api/v1/issues')).length;
      await page.locator('#refresh').click();
      assert.equal(await page.locator('#refresh').isDisabled(), true);
      await page.waitForFunction(() => !document.getElementById('refresh').disabled, null, {timeout: 9500});
      await expectUnknown();
      assert.equal(requests.filter(request => request.url.endsWith('/api/v1/issues')).length, before + 1);
      failure = null;
      await refresh(); await expectText('health', 'Healthy');

      // A response already aged 29 seconds has only one second left, not 30.
      await page.clock.install();
      snapshots = fixture(); snapshots.issues.age_seconds = 29;
      await refresh(); await expectText('health', 'Healthy');
      await page.clock.runFor(2100);
      await expectUnknown();
      snapshots = fixture();
      await refresh(); await expectText('health', 'Healthy');

      // Real browser timers: an absent successful refresh ages out prior Healthy.
      failure = 'timeout';
      await page.clock.runFor(31001);
      await expectUnknown();
      assert.equal(errors.length, 0);
      const dom = await page.locator('body').innerText();
      assert.doesNotMatch(dom, /subject|attachment|body|raw|\b[a-f0-9]{64}\b/i);
      for (const request of requests) {
        const url = new URL(request.url);
        assert.equal(url.origin, base.origin);
        assert.equal(request.method, 'GET');
        assert.ok(url.pathname === '/' || apiPaths.includes(url.pathname));
        assert.equal(url.search, '');
      }
      await context.close();
      process.stdout.write(`Dashboard viewport ${viewport.width}x${viewport.height}: PASS\n`);
    }
  } finally { await browser.close(); }
})().catch(() => { process.stderr.write('Dashboard browser acceptance failed.\n'); process.exitCode = 1; });
