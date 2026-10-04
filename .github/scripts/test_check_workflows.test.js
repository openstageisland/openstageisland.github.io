/*
 * Regression tests for .github/scripts/check_workflows.py.
 *
 * The bug class: a workflow whose YAML does not parse cannot be loaded by
 * GitHub at all. The run shows as failed with zero jobs and no logs, so it is
 * invisible in review and indistinguishable from flaky infrastructure.
 *
 * It happened twice in this repo - ci.yml and heartbeat.yml both embedded a
 * multi-line script in a `run: |` block, putting script source at column 0,
 * which terminates the YAML block scalar. These tests pin the detector to that
 * exact failure so a third occurrence cannot land unnoticed.
 *
 * Run: node --test tests/*.test.js
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const REPO = path.resolve(__dirname, '..', '..');
const CHECKER = path.join(REPO, '.github', 'scripts', 'check_workflows.py');

// Windows runners expose `python`, POSIX runners `python3`. Try both.
const PYTHON = (() => {
  for (const candidate of ['python3', 'python']) {
    const probe = spawnSync(candidate, ['--version'], { encoding: 'utf8' });
    if (probe.status === 0) return candidate;
  }
  throw new Error('no python interpreter found on PATH');
})();

let tmpRoot;

test.before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'check-workflows-'));
});

test.after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

/** Write `files` into a fresh temp workflow dir and run the checker on it. */
function run(files) {
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'case-'));
  for (const [name, body] of Object.entries(files)) {
    fs.writeFileSync(path.join(dir, name), body, 'utf8');
  }
  const res = spawnSync(PYTHON, [CHECKER, '--dir', dir, '--no-network'], {
    encoding: 'utf8',
  });
  return { status: res.status, stdout: res.stdout || '', stderr: res.stderr || '' };
}

test('accepts the workflows this repo actually ships', () => {
  const res = run({});
  // Empty dir is reported as a problem, so assert against the real repo instead.
  assert.notStrictEqual(res.status, 0, 'empty dir should be reported');

  const real = spawnSync(PYTHON, [CHECKER, '--no-network'], {
    cwd: REPO,
    encoding: 'utf8',
  });
  assert.strictEqual(
    real.status,
    0,
    `shipped workflows must parse; stderr was:\n${real.stderr}`
  );
});

test('accepts a well-formed workflow', () => {
  const res = run({
    'ok.yml': [
      'name: OK',
      'on:',
      '  push:',
      '    branches: [main]',
      'jobs:',
      '  build:',
      '    runs-on: ubuntu-latest',
      '    steps:',
      '      - uses: actions/checkout@v4',
      '      - name: Say hi',
      '        run: |',
      '          echo "hello"',
      '',
    ].join('\n'),
  });

  assert.strictEqual(res.status, 0, res.stderr);
  assert.match(res.stdout, /workflow\(s\) OK/);
});

// The core regression: this exact shape broke ci.yml and heartbeat.yml.
test('rejects a `run: |` block terminated by a column-0 line', () => {
  const res = run({
    'broken.yml': [
      'name: Broken',
      'on:',
      '  push:',
      '    branches: [main]',
      'jobs:',
      '  build:',
      '    runs-on: ubuntu-latest',
      '    steps:',
      '      - name: Inline python',
      '        run: |',
      '          python3 -c "',
      'import sys',
      'print(sys.argv)',
      '"',
      '',
    ].join('\n'),
  });

  assert.strictEqual(res.status, 1, 'must fail');
  assert.match(res.stderr, /broken\.yml/);
  // Must name the culprit line (12, where `import sys` sits), not the line after
  // it (13) that PyYAML's own error points at. That distinction is the whole
  // reason this checker exists.
  assert.match(res.stderr, /line 12: unindented line inside a `run: \|` block/);
  assert.match(res.stderr, /import sys/);
  assert.match(res.stderr, /invalid YAML at line 13/);
});

test('rejects the SVG-in-a-block-scalar shape that broke heartbeat.yml', () => {
  const res = run({
    'heartbeat.yml': [
      'name: Heartbeat',
      'on:',
      '  workflow_dispatch: {}',
      'jobs:',
      '  beat:',
      '    runs-on: ubuntu-latest',
      '    steps:',
      '      - run: |',
      '          node -e "',
      '          const svg = `',
      '<svg xmlns="http://www.w3.org/2000/svg">',
      '</svg>`;',
      '          "',
      '',
    ].join('\n'),
  });

  assert.strictEqual(res.status, 1, 'must fail');
  assert.match(res.stderr, /heartbeat\.yml/);
  assert.match(res.stderr, /<svg xmlns=/);
});

test('rejects a document with no jobs key', () => {
  const res = run({ 'no-jobs.yml': 'name: Nope\non:\n  push:\n    branches: [main]\n' });
  assert.strictEqual(res.status, 1);
  assert.match(res.stderr, /no `jobs` key/);
});

test('rejects empty jobs', () => {
  const res = run({ 'empty.yml': 'name: Empty\non:\n  push:\n    branches: [main]\njobs: {}\n' });
  assert.strictEqual(res.status, 1);
  assert.match(res.stderr, /`jobs` is empty/);
});

test('rejects a job-level uses that is neither an action nor a reusable workflow', () => {
  const res = run({
    'uses.yml': [
      'name: Uses',
      'on:',
      '  push:',
      '    branches: [main]',
      'jobs:',
      '  call:',
      '    uses: not-a-valid-reference',
      '',
    ].join('\n'),
  });

  assert.strictEqual(res.status, 1);
  assert.match(res.stderr, /unrecognised `uses: not-a-valid-reference`/);
});

// A reusable-workflow reference also matches the shape of a step action
// (`owner/repo/path@ref`), so it must be classified as a reusable workflow even
// when --no-network skips resolution. Getting this backwards silently disabled
// the archived-dependency check, which is how doctor.yml's dead reference went
// unnoticed.
test('classifies a .github/workflows/ reference as a reusable workflow, not an action', () => {
  const res = run({
    'reusable.yml': [
      'name: Reusable',
      'on:',
      '  push:',
      '    branches: [main]',
      'jobs:',
      '  call:',
      '    uses: neohiro/doctor/.github/workflows/reusable-doctor.yml@main',
      '  plain-action:',
      '    runs-on: ubuntu-latest',
      '    steps:',
      '      - uses: actions/checkout@v4',
      '',
    ].join('\n'),
  });

  // --no-network: recognised, therefore not reported as "unrecognised".
  assert.strictEqual(res.status, 0, res.stderr);
  assert.doesNotMatch(res.stderr, /unrecognised/);
});

test('reports every bad workflow, not just the first', () => {
  const bad = [
    'name: B',
    'on:',
    '  push:',
    '    branches: [main]',
    'jobs:',
    '  j:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - run: |',
    '          echo "',
    'oops',
    '"',
    '',
  ].join('\n');

  const res = run({ 'a.yml': bad, 'b.yml': bad, 'c.yml': bad });
  assert.strictEqual(res.status, 1);
  assert.match(res.stderr, /a\.yml/);
  assert.match(res.stderr, /b\.yml/);
  assert.match(res.stderr, /c\.yml/);
  assert.match(res.stderr, /6 problem\(s\) found/);
});