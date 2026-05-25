/* =====================================================================
   Loan Pipeline Console — front-end effects
   - 3D tilt on cards
   - Count-up animations
   - Reveal-on-load
   - Sparkline canvas charts (no dependency)
   - Chart.js wiring for line + donut charts on dashboards
   - Parallax for hero/login 3D shapes
   ===================================================================== */
(function () {
  'use strict';

  var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------- Tilt cards ---------------- */
  function initTilt() {
    if (prefersReduced) return;
    var cards = document.querySelectorAll('.tilt-card');
    var MAX = 5;
    cards.forEach(function (card) {
      card.addEventListener('mousemove', function (e) {
        var r = card.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width;
        var y = (e.clientY - r.top) / r.height;
        var rx = (0.5 - y) * (MAX * 2);
        var ry = (x - 0.5) * (MAX * 2);
        card.style.transform =
          'perspective(1100px) rotateX(' + rx.toFixed(2) + 'deg) rotateY(' + ry.toFixed(2) + 'deg) translateZ(0)';
      });
      card.addEventListener('mouseleave', function () {
        card.style.transform = 'perspective(1100px) rotateX(0) rotateY(0) translateZ(0)';
      });
    });
  }

  /* ---------------- Count-up ---------------- */
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  function animateCount(el) {
    var raw = el.getAttribute('data-count-target');
    var target = parseInt(raw, 10);
    if (isNaN(target)) return;
    if (prefersReduced) { el.textContent = target.toLocaleString(); return; }
    var duration = Math.min(1600, Math.max(600, target * 5));
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

  /* ---------------- Reveal ---------------- */
  function initRevealOnLoad() {
    document.querySelectorAll('[data-reveal]').forEach(function (el, i) {
      el.classList.add('reveal-on-load');
      el.classList.add('delay-' + ((i % 4) + 1));
    });
  }

  /* ---------------- Sparkline (canvas, no deps) ---------------- */
  function drawSparkline(canvas) {
    var raw = canvas.getAttribute('data-spark');
    if (!raw) return;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return; }
    if (!Array.isArray(data) || !data.length) return;

    var color = canvas.getAttribute('data-spark-color') || '#6366f1';
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || canvas.parentNode.clientWidth || 200;
    var h = canvas.clientHeight || 40;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    var values = data.map(function (d) { return Number(d.value) || 0; });
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    if (min === max) { min = min - 1; max = max + 1; }

    var pad = 3;
    function x(i) { return pad + (i / Math.max(1, values.length - 1)) * (w - pad * 2); }
    function y(v) { return h - pad - ((v - min) / (max - min)) * (h - pad * 2); }

    // gradient area
    var grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, hexToRgba(color, 0.35));
    grad.addColorStop(1, hexToRgba(color, 0));

    ctx.beginPath();
    ctx.moveTo(x(0), y(values[0]));
    for (var i = 1; i < values.length; i++) {
      var px = x(i - 1), py = y(values[i - 1]);
      var nx = x(i), ny = y(values[i]);
      var cx = (px + nx) / 2;
      ctx.quadraticCurveTo(px, py, cx, (py + ny) / 2);
    }
    ctx.lineTo(x(values.length - 1), y(values[values.length - 1]));

    // close to baseline for fill
    ctx.lineTo(w - pad, h - pad);
    ctx.lineTo(pad, h - pad);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // stroke top line
    ctx.beginPath();
    ctx.moveTo(x(0), y(values[0]));
    for (var j = 1; j < values.length; j++) {
      var px2 = x(j - 1), py2 = y(values[j - 1]);
      var nx2 = x(j), ny2 = y(values[j]);
      var cx2 = (px2 + nx2) / 2;
      ctx.quadraticCurveTo(px2, py2, cx2, (py2 + ny2) / 2);
    }
    ctx.lineTo(x(values.length - 1), y(values[values.length - 1]));
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // last point dot
    ctx.beginPath();
    ctx.arc(x(values.length - 1), y(values[values.length - 1]), 2.6, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x(values.length - 1), y(values[values.length - 1]), 4.6, 0, Math.PI * 2);
    ctx.fillStyle = hexToRgba(color, 0.18);
    ctx.fill();
  }
  function hexToRgba(hex, a) {
    var h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
    var n = parseInt(h, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function initSparklines() {
    document.querySelectorAll('canvas[data-spark]').forEach(drawSparkline);
  }

  /* ---------------- Chart.js bindings ---------------- */
  function getChart() { return window.Chart; }

  function gridConfig() {
    return {
      grid: { color: 'rgba(15,23,42,0.06)', drawBorder: false },
      ticks: { color: '#64748b', font: { family: 'Inter, sans-serif', size: 11 } }
    };
  }

  function buildLineChart(ctx, labels, datasets) {
    var Chart = getChart();
    if (!Chart) return null;
    return new Chart(ctx, {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0f172a',
            titleColor: '#fff',
            bodyColor: '#cbd5e1',
            borderColor: 'rgba(255,255,255,0.10)',
            borderWidth: 1,
            padding: 10,
            cornerRadius: 8,
            displayColors: true
          }
        },
        scales: {
          x: gridConfig(),
          y: Object.assign(gridConfig(), { beginAtZero: true, ticks: { color: '#64748b', precision: 0 } })
        },
        elements: { point: { radius: 0, hoverRadius: 5 } }
      }
    });
  }

  function gradientFill(canvas, hexFrom) {
    var ctx = canvas.getContext('2d');
    var g = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 220);
    g.addColorStop(0, hexToRgba(hexFrom, 0.35));
    g.addColorStop(1, hexToRgba(hexFrom, 0));
    return g;
  }

  function initPipelineVolumeChart() {
    var el = document.getElementById('chart-pipeline-volume');
    if (!el || !getChart()) return;
    var uploads, ingest;
    try {
      uploads = JSON.parse(el.getAttribute('data-uploads') || '[]');
      ingest  = JSON.parse(el.getAttribute('data-ingest') || '[]');
    } catch (e) { return; }
    var labels = (uploads.length ? uploads : ingest).map(function (d) { return d.label; });
    var datasets = [
      {
        label: 'Uploads',
        data: uploads.map(function (d) { return d.value; }),
        borderColor: '#6366f1',
        backgroundColor: gradientFill(el, '#6366f1'),
        borderWidth: 2.4,
        tension: 0.42,
        fill: true,
        pointBackgroundColor: '#6366f1'
      }
    ];
    var singleSeries = el.getAttribute('data-single') === '1';
    if (!singleSeries) {
      datasets.push({
        label: 'Rows ingested',
        data: ingest.map(function (d) { return d.value; }),
        borderColor: '#06b6d4',
        backgroundColor: gradientFill(el, '#06b6d4'),
        borderWidth: 2.4,
        tension: 0.42,
        fill: true,
        pointBackgroundColor: '#06b6d4'
      });
    }
    buildLineChart(el, labels, datasets);
  }

  function initUploadVolumeChart() {
    var el = document.getElementById('chart-upload-volume');
    if (!el || !getChart()) return;
    var data;
    try { data = JSON.parse(el.getAttribute('data-series') || '[]'); } catch (e) { return; }
    var labels = data.map(function (d) { return d.label; });
    var values = data.map(function (d) { return d.value; });
    var Chart = getChart();
    new Chart(el, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Volume',
          data: values,
          backgroundColor: function (ctx) {
            var chart = ctx.chart;
            var area = chart.chartArea;
            if (!area) return '#6366f1';
            var g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
            g.addColorStop(0, '#6366f1');
            g.addColorStop(1, hexToRgba('#06b6d4', 0.55));
            return g;
          },
          borderRadius: 8,
          borderSkipped: false,
          maxBarThickness: 32
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0f172a',
            titleColor: '#fff',
            bodyColor: '#cbd5e1',
            borderColor: 'rgba(255,255,255,0.10)',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 10
          }
        },
        scales: {
          x: gridConfig(),
          y: Object.assign(gridConfig(), { beginAtZero: true, ticks: { color: '#64748b', precision: 0 } })
        }
      }
    });
  }

  function initDeptDonut() {
    var el = document.getElementById('chart-dept-donut');
    if (!el || !getChart()) return;
    var f = parseInt(el.getAttribute('data-finance') || '0', 10);
    var h = parseInt(el.getAttribute('data-hr') || '0', 10);
    var s = parseInt(el.getAttribute('data-sales') || '0', 10);
    var highlight = el.getAttribute('data-highlight');
    var allZero = (f + h + s) === 0;
    if (allZero) { f = 1; h = 1; s = 1; }

    var colors = ['#10b981', '#f59e0b', '#ec4899'];
    var offsets = [0, 0, 0];
    if (highlight === 'finance') offsets[0] = 10;
    if (highlight === 'hr')      offsets[1] = 10;
    if (highlight === 'sales')   offsets[2] = 10;

    var Chart = getChart();
    new Chart(el, {
      type: 'doughnut',
      data: {
        labels: ['Finance', 'HR', 'Sales'],
        datasets: [{
          data: [f, h, s],
          backgroundColor: colors,
          borderColor: '#ffffff',
          borderWidth: 4,
          hoverOffset: 12,
          offset: offsets,
          spacing: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0f172a',
            titleColor: '#fff',
            bodyColor: '#cbd5e1',
            borderColor: 'rgba(255,255,255,0.10)',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 10,
            callbacks: {
              label: function (ctx) {
                if (allZero) return ctx.label + ': 0';
                return ctx.label + ': ' + ctx.parsed;
              }
            }
          }
        }
      }
    });
  }

  /* ---------------- 3D parallax on login/hero ---------------- */
  function initParallax() {
    if (prefersReduced) return;
    var stages = document.querySelectorAll('.brand-stage');
    stages.forEach(function (stage) {
      stage.parentElement.addEventListener('mousemove', function (e) {
        var r = stage.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5;
        var y = (e.clientY - r.top) / r.height - 0.5;
        stage.querySelectorAll('.shape').forEach(function (sh, i) {
          var depth = (i + 1) * 6;
          sh.style.transform = (sh.style.transform || '')
            .replace(/translate3d\([^)]*\)/, '') + ' translate3d(' + (x * depth) + 'px, ' + (y * depth) + 'px, 0)';
        });
      });
    });
  }

  /* ---------------- Back to top ---------------- */
  function initBackToTop() {
    var btn = document.getElementById('back-to-top');
    if (!btn) return;
    var threshold = 320;
    var ticking = false;
    function update() {
      var y = window.scrollY || document.documentElement.scrollTop;
      if (y > threshold) btn.classList.add('show');
      else btn.classList.remove('show');
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    btn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: prefersReduced ? 'auto' : 'smooth' });
    });
    update();
  }

  /* ---------------- Bootstrap ---------------- */
  function boot() {
    initRevealOnLoad();
    initTilt();
    initCountUp();
    initSparklines();
    initParallax();
    initBackToTop();

    // Chart.js may still be loading (defer) — try once, then retry briefly.
    function tryCharts(attempt) {
      if (getChart()) {
        if (window.Chart && window.Chart.defaults) {
          window.Chart.defaults.font.family = 'Inter, sans-serif';
          window.Chart.defaults.color = '#64748b';
        }
        initPipelineVolumeChart();
        initUploadVolumeChart();
        initDeptDonut();
        return;
      }
      if (attempt < 30) setTimeout(function () { tryCharts(attempt + 1); }, 80);
    }
    tryCharts(0);

    // Redraw sparklines on resize
    var resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(initSparklines, 150);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
