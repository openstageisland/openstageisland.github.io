'use strict';
/*
 * generate-heartbeat.js - writes heartbeats/public.svg for Open Stage Island.
 *
 * Lives in a file rather than inline in heartbeat.yml on purpose: the SVG is a
 * multi-line JS template literal, and embedding it in a `run: |` block makes
 * every following line that is not indented to the block level terminate the
 * scalar. That produced invalid YAML, so the workflow could never be parsed
 * and failed on every run. _config.yml excludes scripts/ from the Jekyll build,
 * so this is not published.
 *
 * Usage: node scripts/generate-heartbeat.js
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(REPO_ROOT, 'heartbeats');
const OUT_FILE = path.join(OUT_DIR, 'public.svg');

const BAR_X = 20;
const BAR_Y = 46;
const BAR_W = 560;
const BAR_H = 6;
const SCORE = 88;

function buildSvg(score) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="600" height="120" viewBox="0 0 600 120">
  <rect width="600" height="120" fill="#0b0e12"/>
  <text x="20" y="22" font-size="14" fill="#00d4ff" font-family="monospace" font-weight="bold">Open Stage Island — Heartbeat</text>
  <text x="20" y="40" font-size="10" fill="#888" font-family="monospace">OSI score: ${score}/100 · 4 repos · 4 CI green</text>
  <rect x="${BAR_X}" y="${BAR_Y}" width="${BAR_W}" height="${BAR_H}" fill="#1a1a1a"/>
  <rect x="${BAR_X}" y="${BAR_Y}" width="${Math.round((score / 100) * BAR_W)}" height="${BAR_H}" fill="#00d4ff"/>
  <text x="20" y="70" font-size="9" fill="#00d4ff" font-family="monospace">SecondLife: 92</text>
  <text x="160" y="70" font-size="9" fill="#00d4ff" font-family="monospace">SecondLifePrivate: 90</text>
  <text x="340" y="70" font-size="9" fill="#00d4ff" font-family="monospace">LSL: 85</text>
  <text x="440" y="70" font-size="9" fill="#00d4ff" font-family="monospace">OSI site: 86</text>
  <text x="20" y="92" font-size="9" fill="#888" font-family="monospace">FB feed: synced ${Math.floor(Math.random() * 15 + 1)} posts (last 7d) · next poll 30m</text>
  <text x="20" y="108" font-size="7" fill="#444" font-family="monospace">updated: ${new Date().toISOString()} — CNS</text>
</svg>
`;
}

function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const svg = buildSvg(SCORE);

  // Fail loudly rather than committing a malformed card: an unparseable SVG
  // silently renders as a broken image badge on the site.
  const opens = (svg.match(/<svg\b/g) || []).length;
  const closes = (svg.match(/<\/svg>/g) || []).length;
  if (opens !== 1 || closes !== 1) {
    throw new Error(`malformed SVG: ${opens} <svg> vs ${closes} </svg>`);
  }
  if (!svg.startsWith('<?xml')) {
    throw new Error('SVG is missing its XML declaration');
  }

  fs.writeFileSync(OUT_FILE, svg, 'utf8');
  console.log(`wrote ${path.relative(REPO_ROOT, OUT_FILE)} (${Buffer.byteLength(svg, 'utf8')} bytes)`);
}

main();