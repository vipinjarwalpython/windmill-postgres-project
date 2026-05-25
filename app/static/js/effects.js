(function () {
  'use strict';

  var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function initTilt() {
    if (prefersReduced) return;
    var cards = document.querySelectorAll('.tilt-card');
    var MAX = 6; // degrees
    cards.forEach(function (card) {
      card.addEventListener('mousemove', function (e) {
        var r = card.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width;
        var y = (e.clientY - r.top) / r.height;
        var rx = (0.5 - y) * (MAX * 2);
        var ry = (x - 0.5) * (MAX * 2);
        card.style.transform =
          'perspective(1000px) rotateX(' + rx.toFixed(2) + 'deg) rotateY(' + ry.toFixed(2) + 'deg) translateZ(0)';
      });
      card.addEventListener('mouseleave', function () {
        card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateZ(0)';
      });
    });
  }

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  function animateCount(el) {
    var target = parseInt(el.getAttribute('data-count-target'), 10);
    if (isNaN(target)) return;
    if (prefersReduced) { el.textContent = target.toLocaleString(); return; }
    var duration = Math.min(1400, Math.max(500, target * 4));
    var start = performance.now();
    function tick(now) {
      var p = Math.min(1, (now - start) / duration);
      var v = Math.round(target * easeOutCubic(p));
      el.textContent = v.toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initCountUp() {
    document.querySelectorAll('[data-count-target]').forEach(animateCount);
  }

  function initRevealOnLoad() {
    var els = document.querySelectorAll('[data-reveal]');
    els.forEach(function (el, i) {
      el.classList.add('reveal-on-load');
      var delay = (i % 4) + 1;
      el.classList.add('delay-' + delay);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initRevealOnLoad();
      initTilt();
      initCountUp();
    });
  } else {
    initRevealOnLoad();
    initTilt();
    initCountUp();
  }
})();
