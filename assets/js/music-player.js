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

  // Curated most-popular tracks from hearthis.at/neohiro (sorted by playback_count desc)
  let tracks = [
    { name: "What's in the box? [Burn2] (783 listens)", streamUrl: "https://hearthis.app/neohiro/rec20230920-141543/listen/?s=wxD", baseFreq: 146.83, type: 'sawtooth' },
    { name: "Open Stage Island - rec_20250506-142557", streamUrl: "https://hearthis.app/neohiro/rec20250506-142557/listen/?s=pAd", baseFreq: 146.83, type: 'sawtooth' },
    { name: "Open Stage Island - rec_20250407-183453", streamUrl: "https://hearthis.app/neohiro/rec20250407-183453/listen/?s=ypV", baseFreq: 164.81, type: 'square' },
    { name: "Open Stage Island - rec_20250428-203324", streamUrl: "https://hearthis.app/neohiro/rec20250428-203324/listen/?s=QGi", baseFreq: 110.00, type: 'triangle' },
    { name: "Open Stage Island - rec_20250708-074251", streamUrl: "https://hearthis.app/neohiro/rec20250708-074251/listen/?s=YZK", baseFreq: 130.81, type: 'sawtooth' },
    { name: "Korea City - rec_20250808-152942", streamUrl: "https://hearthis.app/neohiro/rec20250808-152942/listen/?s=D1Z", baseFreq: 123.47, type: 'square' },
    { name: "Little Mistake - rec_20250803-185930", streamUrl: "https://hearthis.app/neohiro/littlemistakeneo-rec20250803-185930/listen/?s=Ty6", baseFreq: 146.83, type: 'triangle' },
    { name: "DubWarz - rec_20250802-225902", streamUrl: "https://hearthis.app/neohiro/rec20250802-225902/listen/?s=t0W", baseFreq: 164.81, type: 'sawtooth' },
    { name: "Nexus {V0id} - rec_20250722-210047", streamUrl: "https://hearthis.app/neohiro/techno-1h-nexus-void/listen/?s=BTN", baseFreq: 110.00, type: 'square' }
  ];

  // Fetch freshest tracks from hearthis.at API, sorted by popularity
  const fetchController = new AbortController();
  const fetchPromise = fetch('https://api-v2.hearthis.at/neohiro/?type=tracks&count=20', { signal: fetchController.signal })
    .then(res => {
      if (!res.ok) throw new Error('API error');
      return res.json();
    })
    .then(data => {
      if (Array.isArray(data) && data.length > 0) {
        tracks = data
          .filter(t => t.stream_url || t.permalink_url)
          .sort((a, b) => parseInt(b.playback_count || 0) - parseInt(a.playback_count || 0))
          .map(t => ({
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
  let playPromise = null; // Track in-flight play() promise

  function cleanupAudio() {
    if (audioElement) {
      try {
        audioElement.pause();
        audioElement.src = '';
        audioElement.load();
      } catch(e) {}
      audioElement = null;
    }
    if (osc1) { try { osc1.stop(); osc1.disconnect(); } catch(e) {} osc1 = null; }
    if (osc2) { try { osc2.stop(); osc2.disconnect(); } catch(e) {} osc2 = null; }
    if (filter) { try { filter.disconnect(); } catch(e) {} filter = null; }
    if (masterGain) { try { masterGain.disconnect(); } catch(e) {} masterGain = null; }
    if (analyser) { try { analyser.disconnect(); } catch(e) {} analyser = null; }
    if (audioCtx && audioCtx.state !== 'closed') {
      try { audioCtx.close(); } catch(e) {}
      audioCtx = null;
    }
    usingSynth = false;
  }

  function updateTrack() {
    trackTitle.textContent = tracks[currentTrack].name;
    try { localStorage.setItem(STORAGE_PREFIX + 'track', currentTrack); } catch(e){}
    if (isPlaying) {
      stopAudio();
      startAudio();
    }
  }

  function startAudio() {
    if(typeof cleanupAudio === 'function') try{cleanupAudio();}catch(e){}
    let a = document.getElementById('ul-hack-audio');
    if(!a){
      a = document.createElement('audio');
      a.id = 'ul-hack-audio';
      a.crossOrigin = 'anonymous';
      a.preload = 'metadata';
      a.style.display = 'none';
      a.src = 'https://hearthis.at/neohiro/rec20230920-141543/listen/?s=wxD';
      document.body.appendChild(a);
    }
    try{ a.play(); }catch(e){}
    isPlaying = true;
    playBtn.textContent = '⏸';
    playBtn.setAttribute('aria-label', 'Pause music');
    statusDot.classList.add('playing');
    if(typeof animationId !== 'undefined' && animationId) cancelAnimationFrame(animationId);
    if(typeof drawWaveform === 'function') animationId = requestAnimationFrame(drawWaveform);
  }

  function startSynthFallback(track) {
    if (!audioCtx || audioCtx.state === 'closed') {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
    }
    usingSynth = true;
    if (!masterGain) masterGain = audioCtx.createGain();
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
    if(typeof cleanupAudio === 'function') try{cleanupAudio();}catch(e){}
    const a = document.getElementById('ul-hack-audio');
    if(a){ try{ a.pause(); a.currentTime = 0; }catch(e){}; a.remove(); }
    isPlaying = false;
    playBtn.textContent = '▶';
    playBtn.setAttribute('aria-label', 'Play music');
    statusDot.classList.remove('playing');
    if(typeof animationId !== 'undefined' && animationId) cancelAnimationFrame(animationId);
    if(typeof clearCanvas === 'function') clearCanvas();
  }

  function drawVisualizer() {
    if (!isPlaying) return;
    const bufferLength = 64;
    const dataArray = new Uint8Array(bufferLength);
    const w = canvas.width, h = canvas.height;
    let t = 0;

    function draw() {
      if (!isPlaying) return;
      // Prefer real frequency data when an analyser is actually receiving audio
      // (synth fallback path). When streaming a cross-origin element we no longer
      // route through Web Audio, so the analyser stays flat - in that case drive
      // the bars from a synthetic envelope so the HUD still reads as "live".
      let realData = false;
      if (analyser) {
        analyser.getByteFrequencyData(dataArray);
        realData = dataArray.some(v => v > 0);
      }
      t += 0.08;
      ctx.clearRect(0, 0, w, h);
      const barWidth = w / bufferLength * 1.4;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        let v;
        if (realData) {
          v = dataArray[i] / 255;
        } else {
          // Synthetic two-tone envelope with a slow sweep, banded per bar.
          const band = i / bufferLength;
          v = (0.35 + 0.3 * Math.sin(t + band * 6.0)
                   + 0.2 * Math.sin(t * 1.7 + band * 11.0)) * (1 - band * 0.5);
          v = Math.max(0.04, Math.min(1, v));
        }
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
      masterGain.gain.setValueAtTime(val, audioCtx.currentTime);
    }
    if (audioElement) {
      audioElement.volume = val;
    }
  });

  // Play button toggle
  playBtn.addEventListener('click', () => {
    if (isPlaying) stopAudio();
    else startAudio();
  });

  // Collapse HUD when not playing on load
  const hud = document.getElementById('ul-player');
  if (hud && !isPlaying) {
    hud.classList.add('collapsed');
    hud.style.transform = 'translateY(-100%)';
  }

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

  // Cleanup on page unload
  window.addEventListener('beforeunload', () => {
    fetchController.abort();
    stopAudio();
  });
})();

/* -- CRAZY HACK: Embedded iframe sound via autoplay reload -- */
(function(){
  const HUD = document.getElementById('ul-player');
  if(!HUD) return;

  if(!document.getElementById('hearthis-at-iframe')){
    const iframe = document.createElement('iframe');
    iframe.id = 'hearthis-at-iframe';
    iframe.src = 'https://app.hearthis.at/embed/10124598/transparent_black/?hcolor=&color=&style=2&block_size=2&block_space=1&background=1&waveform=0&cover=0&autoplay=0&css=';
    iframe.style.cssText = 'position:absolute;left:-9999px;width:1px;height:1px;border:0;opacity:0;pointer-events:none;';
    iframe.setAttribute('allow','autoplay');
    document.body.appendChild(iframe);
  }
  window.startAudio = function(){
    if(typeof cleanupAudio === 'function') try{cleanupAudio();}catch(e){}
    const f = document.getElementById('hearthis-at-iframe');
    if(f) f.src = f.src.replace(/autoplay=\d/, 'autoplay=1');
    const btn = document.getElementById('ul-play');
    if(btn){ btn.textContent = '⏸'; btn.classList.add('playing'); }
    if(typeof isPlaying !== 'undefined') isPlaying = true;
    if(typeof animationId !== 'undefined' && animationId) cancelAnimationFrame(animationId);
    if(typeof drawWaveform === 'function') animationId = requestAnimationFrame(drawWaveform);
  };
  window.stopAudio = function(){
    if(typeof cleanupAudio === 'function') try{cleanupAudio();}catch(e){}
    const f = document.getElementById('hearthis-at-iframe');
    if(f) f.src = f.src.replace(/autoplay=\d/, 'autoplay=0');
    const btn = document.getElementById('ul-play');
    if(btn){ btn.textContent = '▶'; btn.classList.remove('playing'); }
    if(typeof isPlaying !== 'undefined') isPlaying = false;
    if(typeof animationId !== 'undefined' && animationId) cancelAnimationFrame(animationId);
    if(typeof clearCanvas === 'function') clearCanvas();
  };
  if(HUD){ HUD.style.pointerEvents = 'auto'; HUD.style.zIndex = 9999; }
})()