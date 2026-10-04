/*
 * Regression tests for the expression check in .github/scripts/check_workflows.py.
 *
 * The bug: GitHub validates `${{ }}` expressions with a grammar stricter than
 * YAML. Property access, indexing and built-in functions are fine; method calls
 * on a value are not. This line made reusable-doctor.yml unloadable:
 *
 *     name: doctor-report-${{ inputs.target_repo.replace('/', '_') }}-${{ github.run_number }}
 *
 *     HTTP 422: failed to parse workflow: (Line: 255, Col: 17):
 *     Unexpected symbol: '(' ... inputs.target_repo.replace('/', '_')
 *
 * An unloadable workflow is reported as a failed run with ZERO jobs and no
 * logs, which is how neohiro/doctor accumulated 141/141 failing runs and why
 * every consumer repo calling it also failed without creating a single job.
 *
 * These tests pin both directions: the real defect must be caught, and every
 * legitimate expression form must stay accepted.
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

const PYTHON = (() => {
  for (const candidate of ['python3', 'python']) {
    if (spawnSync(candidate, ['--version'], { encoding: 'utf8' }).status === 0) return candidate;
  }
  throw new Error('no python interpreter found on PATH');
})();

let tmpRoot;

test.before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'check-expr-'));
});

test.after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

/** Wrap step lines in a minimal valid workflow and run the checker on it. */
function runWithSteps(steps, extraJobs = {}) {
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'case-'));
  const body = [
    'name: T',
    'on:',
    '  push:',
    '    branches: [main]',
    'jobs:',
    '  a:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    ...steps.map((s) => `      - ${s}`),
    ...Object.entries(extraJobs).flatMap(([name, spec]) => [
      `  ${name}:`,
      `    uses: ${spec}`,
    ]),
    '',
  ].join('\n');
  fs.writeFileSync(path.join(dir, 'wf.yml'), body, 'utf8');
  const res = spawnSync(PYTHON, [CHECKER, '--dir', dir, '--no-network'], {
    encoding: 'utf8',
  });
  return { status: res.status, stdout: res.stdout || '', stderr: res.stderr || '', all: (res.stdout || '') + (res.stderr || '') };
}

// --- the defect -----------------------------------------------------------

test('rejects .replace() in an expression (the neohiro/doctor defect)', () => {
  const res = runWithSteps([
    `run: echo "doctor-\${{ inputs.target_repo.replace('/', '_') }}-\${{ github.run_number }}"`,
  ]);
  assert.strictEqual(res.status, 1, 'must fail');
  assert.match(res.all, /\.replace\(/);
  assert.match(res.all, /unloadable/);
});

test('names the line, the method and a concrete alternative', () => {
  const res = runWithSteps([
    `run: echo one`,
    `run: echo "doctor-\${{ inputs.target_repo.replace('/', '_') }}-x"`,
  ]);
  assert.strictEqual(res.status, 1);
  // Header is 8 lines (name/on/push/branches/jobs/a/runs-on/steps), so the
  // second step lands on line 10.
  assert.match(res.all, /line 10/);
  assert.match(res.all, /'\.replace\('/);
  assert.match(res.all, /format\(\)|shell or script step/);
});

test('rejects other unsupported methods', () => {
  for (const expr of [
    "${{ github.ref.split('/')[1] }}",
    "${{ inputs.list.join(',') }}",
    "${{ github.ref.trim() }}",
    "${{ inputs.name.toLower() }}",
  ]) {
    const res = runWithSteps([`run: echo "\${{ ${expr}} }"`]);
    assert.strictEqual(res.status, 1, `should reject: ${expr}`);
    assert.match(res.all, /method call/);
  }
});

test('rejects a method call in a job-level if:', () => {
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'if-'));
  const body = [
    'name: T',
    'on:',
    '  push:',
    '    branches: [main]',
    'jobs:',
    '  a:',
    '    runs-on: ubuntu-latest',
    '    if: ${{ github.ref.startsWith(\'refs/tags/\') }}',
    '    steps:',
    '      - run: echo hi',
    '',
  ].join('\n');
  fs.writeFileSync(path.join(dir, 'wf.yml'), body, 'utf8');
  const res = spawnSync(PYTHON, [CHECKER, '--dir', dir, '--no-network'], { encoding: 'utf8' });
  const all = (res.stdout || '') + (res.stderr || '');
  assert.strictEqual(res.status, 1, all);
  assert.match(all, /method call/);
});

// --- legitimate syntax must not be flagged --------------------------------

test('accepts property access, built-ins, indexing and hashFiles', () => {
  const res = runWithSteps([
    `run: echo "\${{ github.sha }} \${{ github.repository }} \${{ github.event_name }}"`,
    `run: echo "\${{ format('{0}_v{1}', github.ref, 2) }}"`,
    `if: \${{ contains(github.event_name, 'push') }}`,
    `if: \${{ startsWith(github.ref, 'refs/heads/') }}`,
    `if: \${{ endsWith(github.ref, 'main') }}`,
    `run: echo "\${{ hashFiles('package.json') }}"`,
    `run: echo "\${{ join(github.event.commits.*.message, ' | ') }}"`,
  ]);
  assert.strictEqual(res.status, 0, res.all);
});

test('accepts expression indexing', () => {
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'idx-'));
  const body = [
    'name: T',
    'on:',
    '  push:',
    '    branches: [main]',
    'jobs:',
    '  a:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - env:',
    '          FIRST: ${{ inputs.list[0] }}',
    '        run: echo "$FIRST"',
    '',
  ].join('\n');
  fs.writeFileSync(path.join(dir, 'wf.yml'), body, 'utf8');
  const res = spawnSync(PYTHON, [CHECKER, '--dir', dir, '--no-network'], { encoding: 'utf8' });
  const all = (res.stdout || '') + (res.stderr || '');
  assert.strictEqual(res.status, 0, all);
});

test('does not flag dot-paren text outside an expression', () => {
  const res = runWithSteps([
    `run: echo "foo.bar(1) and a.b.c(2) are just text"`,
    `run: pip install --constraint req.txt`,
  ]);
  assert.strictEqual(res.status, 0, res.all);
});

test('does not flag dot-paren inside a run block scalar', () => {
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'blk-'));
  const body = [
    'name: T',
    'on:',
    '  push:',
    '    branches: [main]',
    'jobs:',
    '  a:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - run: |',
    '          echo "not.an.expression(here)"',
    "          echo 'nor.this(one)'",
    '',
  ].join('\n');
  fs.writeFileSync(path.join(dir, 'wf.yml'), body, 'utf8');
  const res = spawnSync(PYTHON, [CHECKER, '--dir', dir, '--no-network'], { encoding: 'utf8' });
  const all = (res.stdout || '') + (res.stderr || '');
  assert.strictEqual(res.status, 0, all);
});

// --- the real upstream file ----------------------------------------------

test('the fixed neohiro/doctor reusable workflow passes', () => {
  const fixed = [
    'name: reusable-doctor',
    'on:',
    '  workflow_call:',
    '    inputs:',
    '      target_sha:',
    "        description: 'SHA'",
    '        required: true',
    '        type: string',
    'jobs:',
    '  validate:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - uses: actions/checkout@v7',
    '      - name: Upload doctor report artifact',
    '        if: always()',
    '        uses: actions/upload-artifact@v7',
    '        with:',
    '          name: doctor-report-${{ github.run_number }}-${{ github.run_attempt }}',
    '          path: /tmp/doctor-report.json',
    '',
  ].join('\n');

  const dir = fs.mkdtempSync(path.join(tmpRoot, 'fixed-'));
  fs.writeFileSync(path.join(dir, 'reusable-doctor.yml'), fixed, 'utf8');
  const res = spawnSync(PYTHON, [CHECKER, '--dir', dir, '--no-network'], { encoding: 'utf8' });
  const all = (res.stdout || '') + (res.stderr || '');
  assert.strictEqual(res.status, 0, all);
});

test('every workflow this repo ships is clean', () => {
  const res = spawnSync(PYTHON, [CHECKER, '--no-network'], { cwd: REPO, encoding: 'utf8' });
  assert.strictEqual(res.status, 0, res.stdout + res.stderr);
});