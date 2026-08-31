---
layout: default
title: "Open Stage Island — Live Destination Data"
description: "Live embed of the official Second Life destination page, visitor counters, and real-time status for Open Stage Island."
canonical: "https://openstageisland.github.io/destinations/"
preload_hero: true
---

<header class="hero" role="banner">
  <img src="{{ "/images/destination-image.png" | relative_url }}"
       alt="Avatars gathered at the Open Stage Island outdoor music venue under laser lights"
       class="hero-image"
       width="657" height="394"
       fetchpriority="high"
       decoding="async">
  <div class="hero-overlay">
    <p class="eyebrow">Live Data</p>
    <h1>Open Stage Island — Live</h1>
    <p class="tagline">Official SL destination page, visitor counters, and live status</p>
    <div class="cta-group">
      <a href="secondlife://Derwent/248/128/22" class="cta-button">Teleport</a>
      <a href="{{ "/" | relative_url }}" class="cta-button cta-secondary" rel="noopener">Back to home</a>
    </div>
  </div>
</header>

<nav class="page-nav" aria-label="Page sections">
  <ul>
    <li><a href="#stats">Live stats</a></li>
    <li><a href="#destination">Destination page</a></li>
    <li><a href="#signals">Live signals</a></li>
    <li><a href="#teleport">Teleport</a></li>
  </ul>
</nav>

<main id="main">
  <section class="intro-card" aria-labelledby="live-heading">
    <h2 id="live-heading" class="intro-heading">Open Stage Island, in real time</h2>
    <p class="intro-text">
      This page surfaces the live state of Open Stage Island. The official
      Second Life destination page is embedded below; visitor counters track
      site and destination traffic; and a live clock marks local time.
      If the destination page is blocked by your browser or network
      (X-Frame-Options / CSP), a graceful fallback appears automatically.
    </p>
  </section>

  <section id="stats" aria-labelledby="stats-heading">
    <h2 id="stats-heading">Live stats</h2>
    <div id="osi-live-data" class="osi-live-data">
      <noscript>
        <p class="osi-live-status">
          Live counters and the destination embed require JavaScript.
        </p>
      </noscript>
    </div>
  </section>

  <section id="destination" aria-labelledby="destination-heading">
    <h2 id="destination-heading">Official destination page</h2>
    <p>
      The Second Life Destination Guide is the authoritative source for the
      venue description, maturity rating, and SLURL. The embed above
      reads directly from
      <code>secondlife.com/destination/open-stage-island</code>.
    </p>
    <p>
      <a href="https://secondlife.com/destination/open-stage-island" rel="noopener" target="_blank">
        Open the official destination page &uarr;
      </a>
    </p>
  </section>

  <section id="signals" aria-labelledby="signals-heading">
    <h2 id="signals-heading">Live signals</h2>
    <ul class="link-list">
      <li>
        <strong>Heartbeat:</strong>
        <a href="https://openstageisland.github.io/heartbeats/" rel="noopener">
          openstageisland.github.io/heartbeats
        </a>
        &mdash; render-side health SVG, refreshed every Heart cycle.
      </li>
      <li>
        <strong>Counter slot 1631175</strong> tracks traffic to this site
        (openstageisland.github.io).
      </li>
      <li>
        <strong>Counter slot 1631180</strong> tracks traffic to the
        destination landing section.
      </li>
    </ul>
  </section>

  <section id="teleport" aria-labelledby="teleport-heading">
    <h2 id="teleport-heading">Teleport</h2>
    <dl class="location-list">
      <div class="location-row">
        <dt>Region</dt>
        <dd>Derwent</dd>
      </div>
      <div class="location-row">
        <dt>Coordinates</dt>
        <dd>248 / 128 / 22</dd>
      </div>
      <div class="location-row">
        <dt>Maturity Rating</dt>
        <dd>Moderate</dd>
      </div>
      <div class="location-row">
        <dt>SLURL</dt>
        <dd>
          <a href="https://maps.secondlife.com/secondlife/Derwent/248/128/22"
             rel="noopener" class="slurl">
            maps.secondlife.com/secondlife/Derwent/248/128/22
          </a>
        </dd>
      </div>
    </dl>
  </section>
</main>
