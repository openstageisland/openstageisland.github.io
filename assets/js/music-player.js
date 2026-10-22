(function () {
  'use strict';

  var playlist = [
    { title: 'Little Mistake — rec_20250803-185930', src: 'https://github.com/neohiro/dj/releases/download/v1.0/Little.Mistake.-.rec_20250803-185930.hearthis.at.mp3' },
    { title: 'Neo.at.Open.Stage.Island — rec_20250403-131400', src: 'https://github.com/neohiro/dj/releases/download/v1.0/Neo.at.Open.Stage.Island.-.rec_20250403-131400.hearthis.at.mp3' },
    { title: "What's in the box? [Burn2] — rec_20230920-141543", src: 'https://github.com/neohiro/dj/releases/download/v1.0/Whats.in.the.box.Burn2.-.rec_20230920-141543.hearthis.at.mp3' }
  ];

  var audio = document.createElement('audio');
  audio.crossOrigin = 'anonymous';
  audio.preload = 'metadata';
  audio.volume = 0.5;
  document.body.appendChild(audio);

  var btnPlay = document.getElementById('ul-play');
  var btnPrev = document.getElementById('ul-prev');
  var btnNext = document.getElementById('ul-next');
  var vol = document.getElementById('ul-vol');
  var titleEl = document.getElementById('ul-track-title');
  var dot = document.getElementById('ul-status-dot');
  var canvas = document.getElementById('ul-canvas');

  var idx = 0;
  var errorEl = null;

  function showError(msg) {
    if (!errorEl) {
      errorEl = document.createElement('p');
      errorEl.style.color = '#ff4060';
      errorEl.style.fontSize = '10px';
      errorEl.style.marginTop = '6px';
      errorEl.setAttribute('id', 'ul-error');
    }
    errorEl.textContent = msg;
  }

  function load(i) {
    idx = ((i % playlist.length) + playlist.length) % playlist.length;
    try {
      audio.src = playlist[idx].src;
      audio.load();
    } catch (e) {}
    if (titleEl) titleEl.textContent = playlist[idx].title;
  }

  function play() {
    var p = audio.play();
    if (p && p.catch) p.catch(function (err) {
      showError(err && err.message ? err.message : 'Playback failed to start');
    });
    if (dot) dot.classList.add('playing');
    if (btnPlay) btnPlay.textContent = '&#x23F8;';
  }

  function pause() {
    audio.pause();
    if (dot) dot.classList.remove('playing');
    if (btnPlay) btnPlay.textContent = '&#9654;';
  }

  function toggle() {
    if (!audio.src || audio.readyState < 2) load(idx);
    if (audio.paused) play(); else pause();
  }

  if (btnPlay) btnPlay.addEventListener('click', toggle);
  if (btnPrev) btnPrev.addEventListener('click', function () { load(idx - 1); play(); });
  if (btnNext) btnNext.addEventListener('click', function () { load(idx + 1); play(); });
  if (vol) {
    vol.addEventListener('input', function () { audio.volume = parseFloat(vol.value) || 0.5; });
  }

  audio.addEventListener('ended', function () { load(idx + 1); play(); });
  audio.addEventListener('error', function () { showError('Could not load track'); });

  load(0);

  if (canvas) {
    var ctx = canvas.getContext('2d');
    var anim = null;
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      var bars = 8;
      var gap = 2;
      var w = (canvas.width - (bars - 1) * gap) / bars;
      for (var i = 0; i < bars; i++) {
        var h = audio.paused ? 4 : 4 + Math.random() * 14;
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
