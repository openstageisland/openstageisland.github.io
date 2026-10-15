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
  
  // Persistent state across ecosystem domains via localStorage
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

  const tracks = [
    { name: "Cyber-Ambient Synth #1", baseFreq: 146.83, type: 'sawtooth', detune: 0, lfoRate: 0.15, lfoDepth: 12 },
    { name: "Neon Grid Runner #2", baseFreq: 164.81, type: 'square', detune: -8, lfoRate: 0.3, lfoDepth: 8 },
    { name: "Sub-Zero Protocol #3", baseFreq: 110.00, type: 'triangle', detune: 4, lfoRate: 0.08, lfoDepth: 18 }
  ];
  
  currentTrack = ((currentTrack % tracks.length) + tracks.length) % tracks.length;
  trackTitle.textContent = tracks[currentTrack].name;

  let audioCtx = null;
  let masterGain = null;
  let analyser = null;
  let osc1 = null, osc2 = null, subOsc = null;
  let lfo1 = null, lfo2 = null;
  let filter = null, filterLFO = null;
  let isPlaying = false;
  let animationId = null;

  function updateTrack() {
    trackTitle.textContent = tracks[currentTrack].name;
    try { localStorage.setItem(STORAGE_PREFIX + 'track', currentTrack); } catch(e){}
    if (isPlaying && audioCtx) {
      stopAudio();
      startAudio();
    }
  }

  function createAudioChain() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') audioCtx.resume();

    masterGain = audioCtx.createGain();
    masterGain.gain.value = parseFloat(volInput.value) * 0.12;

    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.85;

    filter = audioCtx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 800;
    filter.Q.value = 2;

    filterLFO = audioCtx.createOscillator();
    filterLFO.type = 'sine';
    filterLFO.frequency.value = 0.07;
    const filterLFODepth = audioCtx.createGain();
    filterLFODepth.gain.value = 400;
    filterLFO.connect(filterLFODepth).connect(filter.frequency);
    filterLFO.start();

    const track = tracks[currentTrack];

    osc1 = audioCtx.createOscillator();
    osc1.type = track.type;
    osc1.frequency.value = track.baseFreq;
    osc1.detune.value = track.detune;

    osc2 = audioCtx.createOscillator();
    osc2.type = track.type;
    osc2.frequency.value = track.baseFreq * 1.003;
    osc2.detune.value = track.detune + 6;

    subOsc = audioCtx.createOscillator();
    subOsc.type = 'sine';
    subOsc.frequency.value = track.baseFreq * 0.5;

    lfo1 = audioCtx.createOscillator();
    lfo1.type = 'sine';
    lfo1.frequency.value = track.lfoRate;
    const lfo1Depth = audioCtx.createGain();
    lfo1Depth.gain.value = track.lfoDepth;
    lfo1.connect(lfo1Depth);
    lfo1Depth.connect(osc1.frequency);
    lfo1Depth.connect(osc2.frequency);
    lfo1.start();

    lfo2 = audioCtx.createOscillator();
    lfo2.type = 'triangle';
    lfo2.frequency.value = track.lfoRate * 0.7;
    const lfo2Depth = audioCtx.createGain();
    lfo2Depth.gain.value = 200;
    lfo2.connect(lfo2Depth).connect(filter.frequency);
    lfo2.start();

    const osc1Gain = audioCtx.createGain();
    const osc2Gain = audioCtx.createGain();
    const subGain = audioCtx.createGain();
    osc1Gain.gain.value = 0.35;
    osc2Gain.gain.value = 0.25;
    subGain.gain.value = 0.15;

    osc1.connect(osc1Gain);
    osc2.connect(osc2Gain);
    subOsc.connect(subGain);

    osc1Gain.connect(filter);
    osc2Gain.connect(filter);
    subGain.connect(filter);

    filter.connect(analyser);
    analyser.connect(masterGain);
    masterGain.connect(audioCtx.destination);

    osc1.start();
    osc2.start();
    subOsc.start();
  }

  function startAudio() {
    try {
      createAudioChain();
      isPlaying = true;
      playBtn.textContent = '‖';
      playBtn.setAttribute('aria-label', 'Pause music');
      playBtn.title = 'Pause';
      statusDot.classList.add('playing');
      try { localStorage.setItem(STORAGE_PREFIX + 'playing', 'true'); } catch(e){}
      drawVisualizer();
    } catch(e) {
      console.warn("Audio Context init error:", e);
    }
  }

  function stopAudio() {
    [osc1, osc2, subOsc, lfo1, lfo2, filterLFO].forEach(o => {
      if (o) {
        try { o.stop(); o.disconnect(); } catch(e){}
      }
    });
    if (filter) { try { filter.disconnect(); } catch(e){} }
    if (analyser) { try { analyser.disconnect(); } catch(e){} }
    if (masterGain) { try { masterGain.disconnect(); } catch(e){} }
    osc1 = osc2 = subOsc = lfo1 = lfo2 = filterLFO = filter = analyser = masterGain = null;
    isPlaying = false;
    playBtn.textContent = '▶';
    playBtn.setAttribute('aria-label', 'Play music');
    playBtn.title = 'Play (Off by default)';
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
      const barWidth = w / bufferLength * 1.5;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 255;
        const barH = v * h * 0.9;
        const hue = 180 + v * 60;
        ctx.fillStyle = `hsla(${hue}, 100%, 60%, ${0.4 + v * 0.6})`;
        ctx.fillRect(x, h - barH, barWidth, barH);
        x += barWidth + 1;
      }
      animationId = requestAnimationFrame(draw);
    }
    draw();
  }

  function clearCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'rgba(0,229,255,0.05)';
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
      masterGain.gain.setValueAtTime(val * 0.12, audioCtx.currentTime);
    }
  });

  // If autoplay was persisted across page transitions, start audio on first user interaction or context resume
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
