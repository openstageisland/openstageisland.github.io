(function() {
  const toggle = document.getElementById('ul-player-toggle');
  const player = document.getElementById('ul-player');
  const playBtn = document.getElementById('ul-play');
  const prevBtn = document.getElementById('ul-prev');
  const nextBtn = document.getElementById('ul-next');
  const volInput = document.getElementById('ul-vol');
  const statusDot = document.getElementById('ul-status-dot');
  const trackTitle = document.getElementById('ul-track-title');
  const canvas = document.getElementById('ul-canvas');

  if (!toggle || !playBtn || !canvas) return;

  const ctx = canvas.getContext('2d');
  
  const STORAGE_PREFIX = 'neohiro_ecosystem_audio_';
  let isCollapsed = localStorage.getItem(STORAGE_PREFIX + 'collapsed') === 'true';
  let currentTrack = parseInt(localStorage.getItem(STORAGE_PREFIX + 'track') || '0', 10);
  let savedVol = parseFloat(localStorage.getItem(STORAGE_PREFIX + 'vol') ?? '0.5');
  let autoPlay = localStorage.getItem(STORAGE_PREFIX + 'playing') === 'true';

  volInput.value = savedVol;
  if (isCollapsed) {
    player.classList.add('collapsed');
  }

  toggle.addEventListener('click', () => {
    isCollapsed = !isCollapsed;
    player.classList.toggle('collapsed', isCollapsed);
    try { localStorage.setItem(STORAGE_PREFIX + 'collapsed', isCollapsed); } catch(e){}
  });

  // Verified top streamed sets from hearthis.at/neohiro
  let tracks = [
    { name: "Techno Point — Neohiro Live", streamUrl: "https://hearthis.app/neohiro/rec20250810-175936/listen/?s=paL", baseFreq: 146.83, type: 'sawtooth' },
    { name: "Korea City — Neohiro Live", streamUrl: "https://hearthis.app/neohiro/rec20250808-152942/listen/?s=D1Z", baseFreq: 164.81, type: 'square' },
    { name: "Little Mistake — Neohiro Live", streamUrl: "https://hearthis.app/neohiro/littlemistakeneo-rec20250803-185930/listen/?s=Ty6", baseFreq: 110.00, type: 'triangle' },
    { name: "DubWarz — Neohiro Live", streamUrl: "https://hearthis.app/neohiro/rec20250802-225902/listen/?s=t0W", baseFreq: 130.81, type: 'sawtooth' },
    { name: "Nexus {V0id} — Neohiro Live", streamUrl: "https://hearthis.app/neohiro/techno-1h-nexus-void/listen/?s=BTN", baseFreq: 123.47, type: 'square' }
  ];

  // Dynamically fetch freshest tracks from hearthis.at API with fallback to curated list
  fetch('https://api-v2.hearthis.at/neohiro/?type=tracks&count=10')
    .then(res => res.json())
    .then(data => {
      if (Array.isArray(data) && data.length > 0) {
        tracks = data.map(t => ({
          name: (t.title || "Neohiro Set") + " (hearthis.at)",
          streamUrl: t.stream_url || t.permalink_url,
          baseFreq: 146.83,
          type: 'sawtooth'
        }));
        currentTrack = ((currentTrack % tracks.length) + tracks.length) % tracks.length;
        trackTitle.textContent = tracks[currentTrack].name;
      }
    })
    .catch(() => {});

  currentTrack = ((currentTrack % tracks.length) + tracks.length) % tracks.length;
  trackTitle.textContent = tracks[currentTrack].name;

  let audioElement = null;
  let audioCtx = null;
  let masterGain = null;
  let analyser = null;
  let osc1 = null, osc2 = null, filter = null;
  let isPlaying = false;
  let animationId = null;
  let usingSynth = false;

  function updateTrack() {
    trackTitle.textContent = tracks[currentTrack].name;
    try { localStorage.setItem(STORAGE_PREFIX + 'track', currentTrack); } catch(e){}
    if (isPlaying) {
      stopAudio();
      startAudio();
    }
  }

  function startAudio() {
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (audioCtx.state === 'suspended') audioCtx.resume();

      masterGain = audioCtx.createGain();
      masterGain.gain.value = parseFloat(volInput.value);

      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.85;

      masterGain.connect(analyser);
      analyser.connect(audioCtx.destination);

      const track = tracks[currentTrack];
      
      if (track.streamUrl) {
        if (!audioElement) {
          audioElement = new Audio();
          audioElement.crossOrigin = 'anonymous';
          audioElement.loop = true;
        }
        audioElement.src = track.streamUrl;
        
        try {
          const trackSource = audioCtx.createMediaElementSource(audioElement);
          trackSource.connect(masterGain);
        } catch(e) {
          // Already connected or cross-origin handled by direct audio output
          audioElement.connect = null;
        }

        audioElement.play().then(() => {
          usingSynth = false;
          isPlaying = true;
          playBtn.textContent = '‖';
          playBtn.setAttribute('aria-label', 'Pause music');
          statusDot.classList.add('playing');
          try { localStorage.setItem(STORAGE_PREFIX + 'playing', 'true'); } catch(e){}
          drawVisualizer();
        }).catch(() => {
          startSynthFallback(track);
        });
      } else {
        startSynthFallback(track);
      }
    } catch(e) {
      startSynthFallback(tracks[currentTrack]);
    }
  }

  function startSynthFallback(track) {
    usingSynth = true;
    masterGain.gain.value = parseFloat(volInput.value) * 0.15;
    filter = audioCtx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 800;

    osc1 = audioCtx.createOscillator();
    osc1.type = track.type;
    osc1.frequency.value = track.baseFreq;

    osc2 = audioCtx.createOscillator();
    osc2.type = track.type;
    osc2.frequency.value = track.baseFreq * 1.004;

    const g1 = audioCtx.createGain();
    const g2 = audioCtx.createGain();
    g1.gain.value = 0.4;
    g2.gain.value = 0.3;

    osc1.connect(g1).connect(filter);
    osc2.connect(g2).connect(filter);
    filter.connect(masterGain);

    osc1.start();
    osc2.start();

    isPlaying = true;
    playBtn.textContent = '‖';
    playBtn.setAttribute('aria-label', 'Pause music');
    statusDot.classList.add('playing');
    try { localStorage.setItem(STORAGE_PREFIX + 'playing', 'true'); } catch(e){}
    drawVisualizer();
  }

  function stopAudio() {
    if (audioElement) {
      try { audioElement.pause(); } catch(e){}
    }
    if (usingSynth) {
      if (osc1) { try { osc1.stop(); osc1.disconnect(); } catch(e){} }
      if (osc2) { try { osc2.stop(); osc2.disconnect(); } catch(e){} }
      if (filter) { try { filter.disconnect(); } catch(e){} }
    }
    isPlaying = false;
    playBtn.textContent = '▶';
    playBtn.setAttribute('aria-label', 'Play music');
    statusDot.classList.remove('playing');
    try { localStorage.setItem(STORAGE_PREFIX + 'playing', 'false'); } catch(e){}
    if (animationId) cancelAnimationFrame(animationId);
    clearCanvas();
  }

  function drawVisualizer() {
    if (!analyser || !isPlaying) return;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const w = canvas.width, h = canvas.height;

    function draw() {
      if (!isPlaying) return;
      analyser.getByteFrequencyData(dataArray);
      ctx.clearRect(0, 0, w, h);
      const barWidth = w / bufferLength * 1.4;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 255;
        const barH = v * h * 0.95;
        const hue = 180 + v * 60;
        ctx.fillStyle = `hsla(${hue}, 100%, 65%, ${0.4 + v * 0.6})`;
        ctx.fillRect(x, h - barH, barWidth, barH);
        x += barWidth + 1;
      }
      animationId = requestAnimationFrame(draw);
    }
    draw();
  }

  function clearCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'rgba(0,229,255,0.06)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  playBtn.addEventListener('click', () => {
    if (isPlaying) stopAudio();
    else startAudio();
  });

  prevBtn.addEventListener('click', () => {
    currentTrack = (currentTrack - 1 + tracks.length) % tracks.length;
    updateTrack();
  });

  nextBtn.addEventListener('click', () => {
    currentTrack = (currentTrack + 1) % tracks.length;
    updateTrack();
  });

  volInput.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    try { localStorage.setItem(STORAGE_PREFIX + 'vol', val); } catch(e){}
    if (masterGain && audioCtx) {
      masterGain.gain.setValueAtTime(usingSynth ? val * 0.15 : val, audioCtx.currentTime);
    }
    if (audioElement) {
      audioElement.volume = val;
    }
  });

  if (autoPlay) {
    const resumeOnInteract = () => {
      startAudio();
      window.removeEventListener('pointerdown', resumeOnInteract);
      window.removeEventListener('keydown', resumeOnInteract);
    };
    window.addEventListener('pointerdown', resumeOnInteract);
    window.addEventListener('keydown', resumeOnInteract);
  }

  clearCanvas();
})();
