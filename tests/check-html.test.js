/*
 * Regression tests for scripts/check-html.py.
 *
 * Why this exists: ci.yml previously asserted
 *
 *     grep -q '<title>[^<]+</title>' "$f"
 *
 * and reported *every* generated page as "Missing or empty <title>", while the
 * rendered pages all carried a correct title. The assertion was wrong, not the
 * markup - confirmed against the real _site artifact uploaded from a CI run,
 * where all 7 pages have a non-empty title and pass these checks.
 *
 * These tests pin the behaviour that matters: a real title must be accepted
 * (no false positive), and each structural requirement must still be enforced
 * (no false negative). Byte-oriented grep has neither property.
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

const REPO = path.resolve(__dirname, '..');
const CHECKER = path.join(REPO, 'scripts', 'check-html.py');

const PYTHON = (() => {
  for (const candidate of ['python3', 'python']) {
    if (spawnSync(candidate, ['--version'], { encoding: 'utf8' }).status === 0) return candidate;
  }
  throw new Error('no python interpreter found on PATH');
})();

let tmpRoot;

test.before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'check-html-'));
});

test.after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

/** Write `files` into a fresh dir, run the checker, return its result. */
function run(files) {
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'case-'));
  for (const [name, body] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    fs.writeFileSync(path.join(dir, name), body, 'utf8');
  }
  const res = spawnSync(PYTHON, [CHECKER, dir], { encoding: 'utf8' });
  // ::error:: annotations go to stdout (that is where GitHub reads them from);
  // the human summary goes to stderr. Assertions match against both.
  const all = (res.stdout || '') + (res.stderr || '');
  return { status: res.status, stdout: res.stdout || '', stderr: res.stderr || '', all };
}

const GOOD = [
  '<!DOCTYPE html>',
  '<html lang="en">',
  '<head>',
  '  <meta charset="utf-8">',
  '  <title>Open Stage Island &mdash; Visitor Guide</title>',
  '  <meta name="description" content="The complete visitor guide.">',
  '</head>',
  '<body><main id="main"><h1>Hi</h1></main></body>',
  '</html>',
].join('\n');

// The exact false positive that shipped: a real title, reported missing.
test('accepts a page with a real title (regression: was reported missing)', () => {
  const res = run({ 'index.html': GOOD });
  assert.strictEqual(res.status, 0, res.stderr);
  assert.match(res.stdout, /1 HTML file\(s\) passed/);
});

// The rendered pages use a multi-byte em dash. That must not matter.
test('accepts a multi-byte title', () => {
  const withEmDash = GOOD.replace('Open Stage Island &mdash; Visitor Guide', 'Open Stage Island — Visitor Guide');
  assert.ok(withEmDash.includes('—'), 'fixture must contain a real em dash');
  const res = run({ 'index.html': withEmDash });
  assert.strictEqual(res.status, 0, res.stderr);
});

test('accepts a title containing an escaped entity', () => {
  const entity = GOOD.replace('Open Stage Island &mdash; Visitor Guide', 'Tips &amp; Tricks &lt;guide&gt;');
  const res = run({ 'index.html': entity });
  assert.strictEqual(res.status, 0, res.stderr);
});

test('rejects an empty title', () => {
  const res = run({ 'index.html': GOOD.replace(/<title>[^<]*<\/title>/, '<title></title>') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /missing or empty <title>/);
});

test('rejects a missing title', () => {
  const res = run({ 'index.html': GOOD.replace(/<title>[^<]*<\/title>\n/, '') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /missing or empty <title>/);
});

test('rejects a missing doctype', () => {
  const res = run({ 'index.html': GOOD.replace('<!DOCTYPE html>', '') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /DOCTYPE/);
});

test('rejects a missing lang attribute', () => {
  const res = run({ 'index.html': GOOD.replace('<html lang="en">', '<html>') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /lang=/);
});

test('rejects a missing description', () => {
  const res = run({ 'index.html': GOOD.replace(/<meta name="description"[^>]*>\n/, '') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /description/);
});

test('rejects an empty description', () => {
  const res = run({ 'index.html': GOOD.replace(/content="The complete visitor guide\."/, 'content=""') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /description/);
});

test('rejects unbalanced section tags', () => {
  const res = run({ 'index.html': GOOD.replace('<h1>Hi</h1>', '<section><h1>Hi</h1>') });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /unbalanced <section>/);
});

test('accepts balanced nested sections', () => {
  const nested = GOOD.replace(
    '<main id="main"><h1>Hi</h1></main>',
    '<main id="main"><section><section><h1>Hi</h1></section></section></main>'
  );
  const res = run({ 'index.html': nested });
  assert.strictEqual(res.status, 0, res.stderr);
});

test('walks nested directories', () => {
  const res = run({
    'index.html': GOOD,
    'deep/nested/page.html': GOOD,
  });
  assert.strictEqual(res.status, 0, res.stderr);
  assert.match(res.stdout, /2 HTML file\(s\) passed/);
});

test('reports every failing file, not just the first', () => {
  const bad = GOOD.replace(/<title>[^<]*<\/title>/, '<title></title>');
  const res = run({ 'a.html': bad, 'b.html': bad, 'ok.html': GOOD });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /a\.html/);
  assert.match(res.all, /b\.html/);
  assert.match(res.all, /2 of 3 HTML file\(s\) failed/);
});

test('fails when the directory has no HTML', () => {
  const res = run({ 'readme.txt': 'nothing here' });
  assert.strictEqual(res.status, 1);
  assert.match(res.all, /no HTML files found/);
});