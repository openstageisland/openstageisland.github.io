// Auto-fold / expand music HUD when scrolling past 2x hero height,
// and toggle when clicking the music icon button.
(function () {
  const player = document.getElementById('ul-player');
  const toggleBtn = document.getElementById('ul-player-toggle');
  if (!player) return;

  function checkScroll() {
    const hero = document.querySelector('.hero, .mhero, header, .site-header');
    const heroHeight = hero ? hero.offsetHeight : 300;
    const threshold = heroHeight * 2;

    if (window.scrollY > threshold) {
      player.classList.add('collapsed');
      try { localStorage.setItem('neohiro_ecosystem_audio_collapsed', 'true'); } catch (e) {}
    } else {
      player.classList.remove('collapsed');
      try { localStorage.removeItem('neohiro_ecosystem_audio_collapsed'); } catch (e) {}
    }
  }

  // Toggle on icon click (fluid)
  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      if (player.classList.contains('collapsed')) {
        player.classList.remove('collapsed');
        try { localStorage.removeItem('neohiro_ecosystem_audio_collapsed'); } catch (e) {}
      } else {
        player.classList.add('collapsed');
        try { localStorage.setItem('neohiro_ecosystem_audio_collapsed', 'true'); } catch (e) {}
      }
    });
  }

  window.addEventListener('scroll', checkScroll, { passive: true });
  // Initial check in case page loads scrolled
  checkScroll();
})();
