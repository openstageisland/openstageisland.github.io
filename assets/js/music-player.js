(function () {
  'use strict';

  const playlist = [
    {
      title: 'Little Mistake — rec_20250803-185930',
      src: 'https://github.com/neohiro/dj/releases/download/v1.0/Little.Mistake.-.rec_20250803-185930.hearthis.at.mp3'
    },
    {
      title: 'Neo.at.Open.Stage.Island — rec_20250403-131400',
      src: 'https://github.com/neohiro/dj/releases/download/v1.0/Neo.at.Open.Stage.Island.-.rec_20250403-131400.hearthis.at.mp3'
    },
    {
      title: "What's in the box? [Burn2] — rec_20230920-141543",
      src: 'https://github.com/neohiro/dj/releases/download/v1.0/Whats.in.the.box.Burn2.-.rec_20230920-141543.hearthis.at.mp3'
    }
  ];

  const audio = document.createElement('audio');
  audio.preload = 'metadata';
  audio.volume = 0.5;

  const btnPlay = document.getElementById('ul-play');
  const btnPrev = document.getElementById('ul-prev');
  const btnNext = document.getElementById('ul-next');
  const vol = document.getElementById('ul-vol');
  const titleEl = document.getElementById('ul-track-title');
  const dot = document.getElementById('ul-status-dot');
  const canvas = document.getElementById('ul-canvas');

  let idx = 0;

  function load(i) {
    idx = ((i % playlist.length) + playlist.length) % playlist.length;
    audio.src = playlist[idx].src;
    if (titleEl) titleEl.textContent = playlist[idx].title;
  }

  function play() {
    audio.play().catch(function () {});
    if (dot) dot.classList.add('playing');
    if (btnPlay) btnPlay.textContent = '❚❚';
  }

  function pause() {
    audio.pause();
    if (dot) dot.classList.remove('playing');
    if (btnPlay) btnPlay.textContent = '▶';
  }

  function toggle() {
    if (audio.paused) play(); else pause();
  }

  if (btnPlay) btnPlay.addEventListener('click', toggle);
  if (btnPrev) btnPrev.addEventListener('click', function () { load(idx - 1); play(); });
  if (btnNext) btnNext.addEventListener('click', function () { load(idx + 1); play(); });
  if (vol) {
    vol.addEventListener('input', function () { audio.volume = parseFloat(vol.value); });
    audio.volume = parseFloat(vol.value || 0.5);
  }

  audio.addEventListener('ended', function () { load(idx + 1); play(); });

  load(0);

  // Simple canvas visualizer
  if (canvas) {
    const ctx = canvas.getContext('2d');
    let anim = null;
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const bars = 8;
      const gap = 2;
      const w = (canvas.width - (bars - 1) * gap) / bars;
      for (let i = 0; i < bars; i++) {
        const h = audio.paused ? 4 : 4 + Math.random() * 14;
        ctx.fillStyle = audio.paused ? 'rgba(0,229,255,0.15)' : '#00e5ff';
        ctx.fillRect(i * (w + gap), (canvas.height - h) / 2, w, h);
      }
      if (!audio.paused) anim = requestAnimationFrame(draw);
    }
    audio.addEventListener('play', function () { anim = requestAnimationFrame(draw); });
    audio.addEventListener('pause', function () { if (anim) cancelAnimationFrame(anim); draw(); });
    draw();
  }
})();
