"""Build windmill-app-dashboard.json from readable source.

Hand-editing JSON that contains an escaped multiline Bun script is a chore.
This script keeps the Bun render script as a clean Python multi-line string,
then constructs the full dashboard JSON via json.dumps so escaping is automatic.

Run with:  python build_dashboard.py
"""

import json
from pathlib import Path


# ------------------------------------------------------------------
# 1. The HEADER component — sticky nav with login/upload/dashboard steps.
# ------------------------------------------------------------------
HEADER_HTML = r"""<div style="background:linear-gradient(135deg,#0b1226 0%,#0f1a36 55%,#152453 100%);color:#f1f5f9;padding:1rem 1.375rem;border-radius:0.625rem;border:1px solid rgba(255,255,255,0.06);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;box-shadow:0 8px 24px rgba(15,23,42,0.10);">
  <div style="display:flex;align-items:center;gap:0.875rem;">
    <div style="width:2.25rem;height:2.25rem;border-radius:0.5rem;background:linear-gradient(135deg,#6366f1,#3b82f6,#06b6d4);display:grid;place-items:center;font-weight:800;font-size:1.05rem;color:#fff;box-shadow:0 6px 14px rgba(59,130,246,0.40), inset 0 1px 0 rgba(255,255,255,0.30);">L</div>
    <div>
      <div style="font-size:0.6rem;text-transform:uppercase;letter-spacing:0.16em;color:#93c5fd;font-weight:700;">Operations Console</div>
      <div style="font-size:1.0625rem;font-weight:700;letter-spacing:-0.01em;margin-top:0.0625rem;">Loan Pipeline Dashboard</div>
    </div>
  </div>
  <nav id="loan-nav" style="display:flex;align-items:center;gap:0.25rem;padding:0.1875rem;background:rgba(255,255,255,0.06);border-radius:0.5rem;border:1px solid rgba(255,255,255,0.08);">
    <button data-step="login"     class="loan-step-btn" style="padding:0.375rem 0.875rem;background:transparent;color:#cbd5e1;border:none;border-radius:0.375rem;font-size:0.7rem;font-weight:700;cursor:pointer;text-transform:uppercase;letter-spacing:0.06em;">1 &middot; Sign in</button>
    <button data-step="upload"    class="loan-step-btn" style="padding:0.375rem 0.875rem;background:transparent;color:#cbd5e1;border:none;border-radius:0.375rem;font-size:0.7rem;font-weight:700;cursor:pointer;text-transform:uppercase;letter-spacing:0.06em;">2 &middot; Upload</button>
    <button data-step="dashboard" class="loan-step-btn" style="padding:0.375rem 0.875rem;background:transparent;color:#cbd5e1;border:none;border-radius:0.375rem;font-size:0.7rem;font-weight:700;cursor:pointer;text-transform:uppercase;letter-spacing:0.06em;">3 &middot; Dashboard</button>
  </nav>
  <div style="display:flex;align-items:center;gap:0.625rem;font-size:0.7rem;color:#94a3b8;">
    <span style="display:inline-flex;align-items:center;gap:0.375rem;padding:0.25rem 0.625rem;background:rgba(16,185,129,0.18);color:#6ee7b7;border-radius:999px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;font-size:0.6rem;">
      <span style="width:0.4375rem;height:0.4375rem;background:#10b981;border-radius:9999px;box-shadow:0 0 0 0 #10b981;animation:loan-live-pulse 1.6s infinite;"></span>Live
    </span>
    <code style="background:rgba(255,255,255,0.08);color:#e2e8f0;padding:0.1875rem 0.5rem;border-radius:4px;font-size:0.65rem;font-family:'JetBrains Mono','Menlo',monospace;">u/admin/loan_pipeline</code>
  </div>
</div>
<style>
  .loan-step-btn.active { background:linear-gradient(135deg,#3b82f6,#6366f1) !important; color:#fff !important; box-shadow:0 4px 10px rgba(59,130,246,0.35); }
  .loan-step-btn:hover:not(.active) { background:rgba(255,255,255,0.10); color:#fff; }
  @keyframes loan-live-pulse {
    0%,100% { box-shadow:0 0 0 0 rgba(16,185,129,0.55); }
    50%     { box-shadow:0 0 0 6px rgba(16,185,129,0); }
  }
</style>
<script>
(function() {
  if (window.__loanWizardInit) return; window.__loanWizardInit = true
  function findGridItem(node) {
    let p = node
    for (let i = 0; i < 12 && p && p !== document.body; i++) {
      if (p.classList && (p.classList.contains('svlt-grid-item') || p.classList.contains('grid-item'))) return p
      if (p.getAttribute && p.getAttribute('data-component-id')) return p
      p = p.parentElement
    }
    return null
  }
  function apply(step) {
    document.body.dataset.loanStep = step
    document.querySelectorAll('[data-loan-marker]').forEach(marker => {
      const itemView = marker.dataset.loanMarker
      const wrapper = findGridItem(marker)
      if (!wrapper) return
      wrapper.style.display = (itemView === 'always' || itemView === step) ? '' : 'none'
    })
    document.querySelectorAll('.loan-step-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.step === step)
    })
    localStorage.setItem('loan_step', step)
  }
  setInterval(() => apply(localStorage.getItem('loan_step') || (localStorage.getItem('loan_jwt') ? 'upload' : 'login')), 500)
  apply(localStorage.getItem('loan_step') || (localStorage.getItem('loan_jwt') ? 'upload' : 'login'))
  document.querySelectorAll('.loan-step-btn').forEach(b => {
    b.addEventListener('click', () => apply(b.dataset.step))
  })
  window.addEventListener('loan-auth-change', () => {
    if (localStorage.getItem('loan_jwt') && (document.body.dataset.loanStep === 'login')) apply('upload')
  })
  window.addEventListener('loan-upload-success', () => apply('dashboard'))
})()
</script><div data-loan-marker="always" style="display:none;"></div>"""


# ------------------------------------------------------------------
# 2. AUTH card (sign in) — unchanged behavior.
# ------------------------------------------------------------------
AUTH_HTML = r"""<div data-loan-marker="login" style="background:#fff;border:1px solid #e2e8f0;border-radius:0.625rem;padding:1.5rem 1.75rem;height:100%;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;max-width:560px;margin:0 auto;box-shadow:0 4px 14px rgba(15,23,42,0.06);">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
    <div>
      <div style="font-size:0.65rem;text-transform:uppercase;color:#64748b;letter-spacing:0.1em;font-weight:700;">Step 1 of 3</div>
      <div style="font-size:1.25rem;font-weight:700;color:#0f172a;margin-top:0.125rem;letter-spacing:-0.01em;">Sign in</div>
    </div>
    <div id="auth-pill" style="font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;padding:0.25rem 0.625rem;border-radius:999px;"></div>
  </div>
  <div id="auth-form" style="display:flex;flex-direction:column;gap:0.5rem;">
    <input id="auth-u" placeholder="Username (try: admin)" autocomplete="username" style="padding:0.5rem 0.75rem;border:1px solid #cbd5e1;border-radius:0.5rem;font-size:0.875rem;font-family:inherit;" />
    <input id="auth-p" type="password" placeholder="Password (try: admin1234)" autocomplete="current-password" style="padding:0.5rem 0.75rem;border:1px solid #cbd5e1;border-radius:0.5rem;font-size:0.875rem;font-family:inherit;" />
    <button id="auth-btn" style="padding:0.5rem 0.875rem;background:linear-gradient(135deg,#1e40af,#3b82f6);color:#fff;border:none;border-radius:0.5rem;font-size:0.8125rem;font-weight:700;cursor:pointer;letter-spacing:0.03em;margin-top:0.25rem;box-shadow:0 6px 14px rgba(59,130,246,0.30);">Sign in</button>
  </div>
  <div id="auth-logout-row" style="display:none;align-items:center;justify-content:space-between;gap:0.75rem;padding:0.625rem 0.75rem;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:0.5rem;">
    <div style="font-size:0.8125rem;color:#0f172a;">&#x2713; Signed in as <strong id="auth-user-name">-</strong></div>
    <button id="auth-logout" style="padding:0.3125rem 0.625rem;background:#fff;color:#475569;border:1px solid #cbd5e1;border-radius:0.375rem;font-size:0.7rem;font-weight:700;cursor:pointer;">Sign out</button>
  </div>
  <div id="auth-msg" style="margin-top:0.625rem;font-size:0.75rem;color:#94a3b8;min-height:1em;"></div>
</div>
<script>
(function() {
  if (window.__loanAuthInit) return; window.__loanAuthInit = true
  const FASTAPI = 'http://localhost:8000'
  const pill = document.getElementById('auth-pill')
  const form = document.getElementById('auth-form')
  const lrow = document.getElementById('auth-logout-row')
  const name = document.getElementById('auth-user-name')
  const msg  = document.getElementById('auth-msg')
  const loginBtn  = document.getElementById('auth-btn')
  const logoutBtn = document.getElementById('auth-logout')
  function paint() {
    const tok = localStorage.getItem('loan_jwt')
    const usr = localStorage.getItem('loan_user') || ''
    if (tok) {
      pill.textContent = 'AUTHED'; pill.style.background='#dcfce7'; pill.style.color='#15803d'
      form.style.display='none'; lrow.style.display='flex'; name.textContent = usr
    } else {
      pill.textContent = 'ANON'; pill.style.background='#f1f5f9'; pill.style.color='#64748b'
      form.style.display='flex'; lrow.style.display='none'
    }
    window.dispatchEvent(new CustomEvent('loan-auth-change'))
  }
  paint()
  loginBtn.addEventListener('click', async () => {
    const u = document.getElementById('auth-u').value.trim()
    const p = document.getElementById('auth-p').value
    if (!u || !p) { msg.innerHTML = '<span style="color:#a16207;">enter username + password</span>'; return }
    loginBtn.disabled = true; loginBtn.textContent = 'Signing in...'; msg.textContent = ''
    try {
      const r = await fetch(FASTAPI + '/api/v1/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p })
      })
      if (!r.ok) throw new Error((await r.text()) || ('HTTP ' + r.status))
      const j = await r.json()
      localStorage.setItem('loan_jwt', j.access_token)
      localStorage.setItem('loan_user', u)
      msg.innerHTML = '<span style="color:#15803d;">&#x2713; signed in - opening upload...</span>'
      paint()
    } catch (e) {
      msg.innerHTML = '<span style="color:#dc2626;">' + (e.message || e) + '</span>'
    } finally {
      loginBtn.disabled = false; loginBtn.textContent = 'Sign in'
    }
  })
  logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('loan_jwt'); localStorage.removeItem('loan_user')
    localStorage.setItem('loan_step', 'login')
    msg.innerHTML = '<span style="color:#64748b;">signed out</span>'
    paint()
  })
  document.getElementById('auth-p').addEventListener('keydown', e => { if (e.key === 'Enter') loginBtn.click() })
})()
</script>"""


# ------------------------------------------------------------------
# 3. UPLOAD card — unchanged behavior.
# ------------------------------------------------------------------
UPLOAD_HTML = r"""<div data-loan-marker="upload" style="background:#fff;border:1px solid #e2e8f0;border-radius:0.625rem;padding:1.5rem 1.75rem;height:100%;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;max-width:640px;margin:0 auto;box-shadow:0 4px 14px rgba(15,23,42,0.06);">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
    <div>
      <div style="font-size:0.65rem;text-transform:uppercase;color:#64748b;letter-spacing:0.1em;font-weight:700;">Step 2 of 3</div>
      <div style="font-size:1.25rem;font-weight:700;color:#0f172a;margin-top:0.125rem;letter-spacing:-0.01em;">Upload loan file</div>
    </div>
    <div style="font-size:0.65rem;color:#94a3b8;font-family:'JetBrains Mono','Menlo',monospace;">POST /api/v1/uploads/loan</div>
  </div>
  <div style="display:flex;gap:0.5rem;align-items:center;">
    <label id="upload-pick" for="upload-file" style="flex:1;padding:0.75rem;border:2px dashed #cbd5e1;border-radius:0.5rem;font-size:0.8125rem;color:#64748b;cursor:pointer;background:linear-gradient(180deg,#f8fafc,#fff);text-align:center;">&#x1f4ce; Choose .csv file...</label>
    <input id="upload-file" type="file" accept=".csv,.json,.txt,.pdf" style="display:none;" />
    <button id="upload-btn" disabled style="padding:0.5rem 1rem;background:linear-gradient(135deg,#0f766e,#10b981);color:#fff;border:none;border-radius:0.5rem;font-size:0.8125rem;font-weight:700;cursor:pointer;letter-spacing:0.03em;opacity:0.5;box-shadow:0 6px 14px rgba(16,185,129,0.30);">Upload</button>
  </div>
  <div id="upload-msg" style="margin-top:0.75rem;font-size:0.75rem;color:#94a3b8;min-height:1em;"></div>
</div>
<script>
(function() {
  if (window.__loanUploadInit) return; window.__loanUploadInit = true
  const FASTAPI = 'http://localhost:8000'
  const pick = document.getElementById('upload-pick')
  const fin  = document.getElementById('upload-file')
  const btn  = document.getElementById('upload-btn')
  const msg  = document.getElementById('upload-msg')
  function refreshBtn() {
    const tok = localStorage.getItem('loan_jwt')
    const file = fin.files[0]
    btn.disabled = !(tok && file)
    btn.style.opacity = btn.disabled ? '0.5' : '1'
    if (!tok) {
      msg.innerHTML = '<span style="color:#a16207;">&#x26a0; sign in first (Step 1)</span>'
    } else if (!file) {
      msg.innerHTML = '<span style="color:#64748b;">select a file to enable upload</span>'
    }
  }
  refreshBtn()
  window.addEventListener('loan-auth-change', refreshBtn)
  fin.addEventListener('change', () => {
    const f = fin.files[0]
    pick.textContent = f ? ('\u{1F4C4} ' + f.name + ' (' + (f.size/1024).toFixed(1) + ' KB)') : '\u{1F4CE} Choose .csv file...'
    refreshBtn()
  })
  btn.addEventListener('click', async () => {
    const tok = localStorage.getItem('loan_jwt')
    const f = fin.files[0]
    if (!tok || !f) return
    btn.disabled = true; btn.textContent = 'Uploading...'; msg.textContent = ''
    try {
      const fd = new FormData(); fd.append('file', f)
      const r = await fetch(FASTAPI + '/api/v1/uploads/loan', {
        method: 'POST', headers: { Authorization: 'Bearer ' + tok }, body: fd
      })
      const body = await r.text()
      if (!r.ok) throw new Error(body || ('HTTP ' + r.status))
      const j = JSON.parse(body)
      msg.innerHTML = '<span style="color:#15803d;">&#x2713; ' + (j.message || 'triggered') + ' - opening dashboard...</span>'
      window.dispatchEvent(new CustomEvent('loan-upload-success', { detail: j }))
    } catch (e) {
      msg.innerHTML = '<span style="color:#dc2626;">' + (e.message || e) + '</span>'
    } finally {
      btn.textContent = 'Upload'; refreshBtn()
    }
  })
})()
</script>"""


# ------------------------------------------------------------------
# 4. DASHBOARD render — the redesigned component:
#    metrics → PIPELINE PHASES (new) → LIVE LOGS (moved to top) → run history table.
# ------------------------------------------------------------------
DASHBOARD_BUN = r"""const FLOW_PATH = 'u/admin/loan_pipeline'

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]))
}

function humanize(id) {
  return String(id || '').replace(/[_\-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function statusPill(j) {
  let label='—', fg='#64748b', bg='#f1f5f9', dot='#94a3b8', pulse=false
  if (j.type === 'QueuedJob') {
    if (j.running) { label='Running'; fg='#1d4ed8'; bg='#eff6ff'; dot='#3b82f6'; pulse=true }
    else { label='Queued'; fg='#a16207'; bg='#fefce8'; dot='#eab308'; pulse=true }
  } else if (j.success === true) { label='Success'; fg='#15803d'; bg='#f0fdf4'; dot='#22c55e' }
  else if (j.success === false) { label='Failed'; fg='#b91c1c'; bg='#fef2f2'; dot='#ef4444' }
  const pulseStyle = pulse ? `box-shadow:0 0 0 0 ${dot};animation:dash-pulse 1.4s infinite;` : ''
  return `<span style="display:inline-flex;align-items:center;gap:0.3125rem;padding:0.1875rem 0.5rem;background:${bg};color:${fg};border-radius:999px;font-size:0.6875rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;">
    <span style="width:0.375rem;height:0.375rem;background:${dot};border-radius:9999px;${pulseStyle}"></span>${label}</span>`
}

function colorize(line) {
  const safe = esc(line)
  if (/\b(ERROR|FAIL|FAILED|Exception|Traceback)\b/i.test(line)) return `<span style="color:#fca5a5;">${safe}</span>`
  if (/\b(WARN|WARNING)\b/i.test(line)) return `<span style="color:#fcd34d;">${safe}</span>`
  if (/\b(SUCCESS|DONE|OK|Completed)\b/i.test(line)) return `<span style="color:#86efac;">${safe}</span>`
  if (/\b(INFO|Running|Started)\b/i.test(line)) return `<span style="color:#93c5fd;">${safe}</span>`
  return `<span style="color:#cbd5e1;">${safe}</span>`
}

function metric(label, value, accent, sublabel) {
  const sub = sublabel ? `<div style="font-size:0.6rem;color:#94a3b8;margin-top:0.1875rem;letter-spacing:0.04em;">${esc(sublabel)}</div>` : ''
  return `<div style="position:relative;background:linear-gradient(180deg,#ffffff,#fbfcfe);padding:0.875rem 1rem;border:1px solid #e2e8f0;border-radius:0.625rem;overflow:hidden;box-shadow:0 2px 6px rgba(15,23,42,0.04);">
    <div style="position:absolute;top:0;left:0;right:0;height:3px;background:${accent};"></div>
    <div style="font-size:0.625rem;text-transform:uppercase;color:#64748b;letter-spacing:0.1em;font-weight:700;">${esc(label)}</div>
    <div style="font-size:1.625rem;font-weight:800;color:#0f172a;line-height:1.05;margin-top:0.3125rem;letter-spacing:-0.025em;font-variant-numeric:tabular-nums;">${value}</div>
    ${sub}
  </div>`
}

function phaseStateColors(state) {
  // state: passed / running / failed / blocked / pending
  switch (state) {
    case 'passed':  return { bg:'linear-gradient(135deg,#34d399,#10b981)', badge:'#10b981', meta:'#d1fae5', metaFg:'#047857', label:'Passed' }
    case 'running': return { bg:'linear-gradient(135deg,#60a5fa,#2563eb)', badge:'#2563eb', meta:'#dbeafe', metaFg:'#1d4ed8', label:'Running' }
    case 'failed':  return { bg:'linear-gradient(135deg,#fb7185,#e11d48)', badge:'#e11d48', meta:'#fee2e2', metaFg:'#b91c1c', label:'Failed' }
    case 'blocked': return { bg:'linear-gradient(135deg,#cbd5e1,#94a3b8)', badge:'#64748b', meta:'#e2e8f0', metaFg:'#475569', label:'Skipped' }
    default:        return { bg:'linear-gradient(135deg,#e2e8f0,#cbd5e1)', badge:'#94a3b8', meta:'#f1f5f9', metaFg:'#475569', label:'Pending' }
  }
}

function stateIcon(state) {
  if (state === 'passed')  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
  if (state === 'failed')  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
  if (state === 'running') return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="dash-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>'
  if (state === 'blocked') return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>'
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
}

function phaseNode(idx, total, name, state, detail) {
  const c = phaseStateColors(state)
  const ring = state === 'running'
    ? `<div style="position:absolute;inset:-6px;border-radius:50%;border:2px solid #38bdf8;opacity:0.55;animation:dash-ring-pulse 1.6s ease-in-out infinite;"></div>` : ''
  return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 0.5rem;min-width:0;">
    <div style="position:relative;width:3.75rem;height:3.75rem;">
      ${ring}
      <div style="width:3.5rem;height:3.5rem;border-radius:50%;background:${c.bg};display:grid;place-items:center;color:#fff;box-shadow:0 10px 22px rgba(15,23,42,0.18), inset 0 1px 0 rgba(255,255,255,0.30);">
        <div style="font-weight:800;font-size:1rem;">${idx + 1}</div>
      </div>
      <div style="position:absolute;right:-4px;bottom:-4px;width:1.5rem;height:1.5rem;border-radius:50%;background:${c.badge};color:#fff;display:grid;place-items:center;border:2px solid #fff;box-shadow:0 4px 8px rgba(15,23,42,0.18);">
        <span style="width:0.875rem;height:0.875rem;display:inline-block;">${stateIcon(state)}</span>
      </div>
    </div>
    <div style="margin-top:0.5rem;font-size:0.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;">Step ${idx + 1}</div>
    <div style="font-size:0.8125rem;font-weight:700;color:#0f172a;margin-top:0.125rem;letter-spacing:-0.01em;">${esc(name)}</div>
    <div style="display:inline-block;margin-top:0.25rem;padding:0.0625rem 0.4375rem;border-radius:999px;font-size:0.625rem;font-weight:700;background:${c.meta};color:${c.metaFg};">${c.label}</div>
    <div style="margin-top:0.3125rem;font-size:0.6875rem;color:#64748b;line-height:1.35;word-break:break-word;">${esc(detail || '')}</div>
  </div>`
}

function phaseConnector(state) {
  let bg = '#e2e8f0', extra = ''
  if (state === 'passed')  bg = 'linear-gradient(90deg,#34d399,#10b981)'
  else if (state === 'failed') bg = 'linear-gradient(90deg,#fb7185,#e11d48)'
  else if (state === 'blocked') bg = 'linear-gradient(90deg,#cbd5e1,#94a3b8)'
  else if (state === 'running') {
    extra = `<div style="position:absolute;inset:0;background:linear-gradient(90deg,transparent 0%,#60a5fa 50%,transparent 100%);background-size:50% 100%;background-repeat:no-repeat;animation:dash-flow 1.4s linear infinite;"></div>`
  }
  return `<div style="position:relative;flex:0 0 2rem;height:4px;align-self:center;margin-top:2.625rem;border-radius:999px;background:${bg};overflow:hidden;">${extra}</div>`
}

function moduleStateFromWindmill(modType) {
  // Windmill flow_status.modules[i].type values
  if (modType === 'Success') return 'passed'
  if (modType === 'Failure') return 'failed'
  if (modType === 'InProgress') return 'running'
  if (modType === 'WaitingForPriorSteps') return 'pending'
  return 'pending'
}

function renderPhases(latestJob, modules, flowDef) {
  // Map flow_status.modules to phase descriptors. Flow definition gives us
  // friendly module names; flow_status gives the live status.
  if (!modules || !modules.length) {
    return `<div style="padding:1.5rem;text-align:center;color:#94a3b8;font-size:0.8125rem;">No phase data — flow has not started reporting yet.</div>`
  }
  const defs = (flowDef && flowDef.value && flowDef.value.modules) ? flowDef.value.modules : []
  const phases = modules.map((m, i) => {
    const def = defs[i] || {}
    const id = m.id || def.id || `step_${i + 1}`
    const name = def.summary || humanize(id) || `Step ${i + 1}`
    const state = moduleStateFromWindmill(m.type)
    let detail = ''
    if (state === 'failed' && m.flow_jobs && m.flow_jobs.length) detail = `${m.flow_jobs.length} sub-job(s) failed`
    else if (m.iterator) detail = `Iterator (${m.iterator.itered ? m.iterator.itered.length : '?'} items)`
    else if (state === 'passed') detail = id
    else if (state === 'running') detail = `Running ${id}…`
    else if (state === 'pending') detail = 'Waiting'
    return { name, state, detail }
  })

  const nodes = []
  phases.forEach((p, i) => {
    nodes.push(phaseNode(i, phases.length, p.name, p.state, p.detail))
    if (i < phases.length - 1) {
      const next = phases[i + 1]
      nodes.push(phaseConnector(next.state))
    }
  })

  // Overall status pill for the run
  let overall = 'pending', overallLabel = 'Pending'
  if (latestJob && latestJob.type === 'QueuedJob') { overall = 'running'; overallLabel = 'Running' }
  else if (latestJob && latestJob.success === true) { overall = 'passed'; overallLabel = 'Completed' }
  else if (latestJob && latestJob.success === false) { overall = 'failed'; overallLabel = 'Failed' }
  const c = phaseStateColors(overall)

  return `<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.875rem;flex-wrap:wrap;margin-bottom:0.875rem;">
    <div>
      <div style="font-size:0.625rem;text-transform:uppercase;color:#94a3b8;letter-spacing:0.1em;font-weight:700;">Latest run · Pipeline phases</div>
      <div style="font-size:0.8125rem;color:#475569;margin-top:0.125rem;font-family:'JetBrains Mono','Menlo',monospace;">${esc((latestJob && latestJob.id) ? latestJob.id : '—')}</div>
    </div>
    <span style="display:inline-flex;align-items:center;gap:0.4375rem;padding:0.3125rem 0.75rem;border-radius:999px;font-size:0.6875rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;background:${c.meta};color:${c.metaFg};border:1px solid rgba(15,23,42,0.06);">
      <span style="width:1rem;height:1rem;display:inline-grid;place-items:center;color:${c.metaFg};">${stateIcon(overall)}</span>
      ${overallLabel}
    </span>
  </div>
  <div style="display:flex;align-items:flex-start;padding:1rem 0.5rem;background:radial-gradient(800px 240px at 50% 0%, rgba(99,102,241,0.06), transparent 70%);border-radius:0.5rem;">${nodes.join('')}</div>`
}

function infoChip(label, value, color) {
  return `<span style="display:inline-flex;align-items:center;gap:0.375rem;padding:0.25rem 0.625rem;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;font-size:0.6875rem;color:#475569;">
    <span style="font-weight:700;color:${color || '#0f172a'};">${esc(label)}</span>
    <span style="font-variant-numeric:tabular-nums;">${esc(value)}</span>
  </span>`
}

export async function main() {
  const base = process.env.BASE_INTERNAL_URL || 'http://windmill_server:8000'
  const ws = process.env.WM_WORKSPACE || 'admin'
  const token = process.env.WM_TOKEN || ''
  const auth = { Authorization: `Bearer ${token}` }

  // 1) Jobs list
  let jobs = [], err = null
  try {
    const r = await fetch(`${base}/api/w/${ws}/jobs/list?script_path_exact=${FLOW_PATH}&per_page=100`, { headers: auth })
    if (!r.ok) err = `${r.status} ${r.statusText}`
    else jobs = await r.json()
  } catch (e) { err = e?.message ?? String(e) }

  const stats = { total: jobs.length, running: 0, success: 0, failed: 0 }
  for (const j of jobs) {
    if (j.type === 'QueuedJob') stats.running++
    else if (j.success === true) stats.success++
    else if (j.success === false) stats.failed++
  }
  const completed = stats.success + stats.failed
  const successRate = completed > 0 ? Math.round((stats.success / completed) * 100) : 0

  // Average duration on completed jobs (last 20)
  let avgMs = 0
  const completedJobs = jobs.filter(j => j.type !== 'QueuedJob' && j.duration_ms != null).slice(0, 20)
  if (completedJobs.length) {
    avgMs = Math.round(completedJobs.reduce((a, j) => a + j.duration_ms, 0) / completedJobs.length)
  }
  const avgDurStr = avgMs ? (avgMs > 1500 ? (avgMs / 1000).toFixed(1) + 's' : avgMs + 'ms') : '—'

  // 2) Latest job details (for flow_status) + logs
  let latestDetails = null
  let flowDef = null
  let logsBody = `<span style="color:#64748b;">No pipeline runs yet — upload a file to start one.</span>`
  let logsCount = ''
  let logsMeta = ''
  let logsJobId = ''
  let liveDot = ''
  let phasesHtml = `<div style="padding:1.5rem;text-align:center;color:#94a3b8;font-size:0.8125rem;">No runs yet — upload a file from Step 2.</div>`

  if (jobs.length > 0) {
    const latest = jobs[0]
    const isRunning = latest.type === 'QueuedJob'
    logsJobId = latest.id

    // Fetch full job details for flow_status
    const detailUrl = isRunning
      ? `${base}/api/w/${ws}/jobs_u/get/${latest.id}`
      : `${base}/api/w/${ws}/jobs_u/completed/get/${latest.id}`
    try {
      const r = await fetch(detailUrl, { headers: auth })
      if (r.ok) latestDetails = await r.json()
    } catch (e) {}

    // Fetch flow definition once (for module summaries)
    try {
      const r = await fetch(`${base}/api/w/${ws}/flows/get/${FLOW_PATH}`, { headers: auth })
      if (r.ok) flowDef = await r.json()
    } catch (e) {}

    if (latestDetails && latestDetails.flow_status) {
      phasesHtml = renderPhases(latest, latestDetails.flow_status.modules, flowDef)
    }

    // Logs
    const startedFmt = (latest.started_at || latest.created_at) ? new Date(latest.started_at || latest.created_at).toLocaleTimeString() : '—'
    let lineCount = 0
    try {
      const r = await fetch(`${base}/api/w/${ws}/jobs_u/get_flow_all_logs/${latest.id}`, { headers: auth })
      if (r.ok) {
        const text = await r.text()
        const lines = text.split(/\r?\n/)
        lineCount = lines.length
        if (lineCount === 0 || (lineCount === 1 && lines[0] === '')) {
          logsBody = isRunning
            ? `<span style="color:#94a3b8;">⏳ Waiting for output — job just started…</span>`
            : `<span style="color:#64748b;">(no log output for this job)</span>`
        } else {
          logsBody = lines.slice(-400).map(colorize).join('\n')
        }
      } else {
        logsBody = `<span style="color:#fca5a5;">log fetch failed: ${r.status}</span>`
      }
    } catch (e) { logsBody = `<span style="color:#fca5a5;">${esc(e?.message ?? e)}</span>` }

    logsCount = `<span style="color:#94a3b8;font-size:0.6875rem;font-variant-numeric:tabular-nums;">${lineCount} lines</span>`
    logsMeta = `<span style="color:#cbd5e1;font-family:'JetBrains Mono','Menlo',monospace;font-size:0.6875rem;">${esc(latest.id.slice(0,20))}…</span>
      <span style="color:#94a3b8;font-size:0.6875rem;">${esc(startedFmt)}</span>
      ${statusPill(latest)}`
    if (isRunning) {
      liveDot = `<span style="display:inline-flex;align-items:center;gap:0.3125rem;padding:0.1875rem 0.5rem;background:rgba(59,130,246,0.18);color:#bfdbfe;border-radius:999px;font-size:0.625rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;border:1px solid rgba(59,130,246,0.30);">
        <span style="width:0.4375rem;height:0.4375rem;background:#3b82f6;border-radius:9999px;box-shadow:0 0 0 0 #3b82f6;animation:dash-pulse 1.4s infinite;"></span>LIVE</span>`
    }
  }

  // Recent run history rows
  const tableRows = jobs.slice(0, 30).map(j => {
    const args = j.args || {}
    const started = j.started_at || j.created_at
    const startedStr = started ? new Date(started).toLocaleString() : '—'
    const dur = j.duration_ms != null ? (j.duration_ms/1000).toFixed(2) + 's' : (j.type === 'QueuedJob' && started ? ((Date.now() - new Date(started).getTime())/1000).toFixed(1) + 's…' : '—')
    const file = args.original_filename || (args.file_path||'').split('/').pop() || '—'
    const link = `/run/${j.id}?workspace=${ws}`
    const rowAccent = j.id === logsJobId ? 'background:#fafbfc;' : ''
    return `<tr style="border-top:1px solid #f1f5f9;${rowAccent}">
      <td style="padding:0.5rem 0.75rem;font-size:0.75rem;color:#334155;white-space:nowrap;">${esc(startedStr)}</td>
      <td style="padding:0.5rem 0.75rem;font-family:'JetBrains Mono','Menlo',monospace;font-size:0.6875rem;">
        <a href="${link}" target="_blank" rel="noopener" style="color:#1d4ed8;text-decoration:none;">${esc(j.id.slice(0,12))}…</a></td>
      <td style="padding:0.5rem 0.75rem;font-size:0.75rem;color:#475569;">${esc(j.created_by ?? '—')}</td>
      <td style="padding:0.5rem 0.75rem;">${statusPill(j)}</td>
      <td style="padding:0.5rem 0.75rem;font-size:0.75rem;color:#475569;text-align:right;font-variant-numeric:tabular-nums;">${esc(dur)}</td>
      <td style="padding:0.5rem 0.75rem;font-size:0.75rem;color:#475569;">${esc(file)}</td>
    </tr>`
  }).join('')

  const errBanner = err
    ? `<div style="background:#fef2f2;border:1px solid #fecaca;color:#991b1b;padding:0.5rem 0.75rem;border-radius:0.375rem;font-size:0.75rem;margin-bottom:0.625rem;">Could not load jobs: ${esc(err)}</div>`
    : ''

  // Top context strip (env, flow, ws, avg duration)
  const contextStrip = `<div style="display:flex;flex-wrap:wrap;gap:0.4375rem;margin-bottom:0.75rem;">
    ${infoChip('Workspace', ws, '#6366f1')}
    ${infoChip('Flow', FLOW_PATH, '#0ea5e9')}
    ${infoChip('Avg duration', avgDurStr, '#10b981')}
    ${infoChip('Jobs cached', String(jobs.length), '#475569')}
  </div>`

  return `
    <div data-loan-marker="dashboard" style="display:none;"></div>
    <style>
      @keyframes dash-pulse {
        0%   { box-shadow:0 0 0 0 rgba(59,130,246,0.55); }
        70%  { box-shadow:0 0 0 6px rgba(59,130,246,0); }
        100% { box-shadow:0 0 0 0 rgba(59,130,246,0); }
      }
      @keyframes dash-ring-pulse {
        0%,100% { transform:scale(1); opacity:0.55; }
        50%     { transform:scale(1.08); opacity:0.95; }
      }
      @keyframes dash-flow {
        from { background-position: -50% 0; }
        to   { background-position:  150% 0; }
      }
      @keyframes dash-spin { to { transform: rotate(360deg); } }
      .dash-spin { animation: dash-spin 1.4s linear infinite; transform-origin: 50% 50%; }
      #dash-logs { scroll-behavior:smooth; }
    </style>
    ${errBanner}
    ${contextStrip}

    <!-- 1. HERO METRIC TILES -->
    <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0.625rem;margin-bottom:0.875rem;">
      ${metric('Total runs', stats.total, 'linear-gradient(90deg,#6366f1,#3b82f6)', 'all-time')}
      ${metric('Running', stats.running, 'linear-gradient(90deg,#3b82f6,#06b6d4)', 'in flight')}
      ${metric('Succeeded', stats.success, 'linear-gradient(90deg,#10b981,#22c55e)', 'all phases green')}
      ${metric('Failed', stats.failed, 'linear-gradient(90deg,#ef4444,#f97316)', 'needs review')}
      ${metric('Success rate', successRate + '%', 'linear-gradient(90deg,#0ea5e9,#6366f1)', 'on completed')}
    </div>

    <!-- 2. PIPELINE PHASES -->
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:0.625rem;padding:1rem 1.125rem;margin-bottom:0.875rem;box-shadow:0 2px 6px rgba(15,23,42,0.04);position:relative;">
      ${phasesHtml}
    </div>

    <!-- 3. LIVE LOGS (moved to top) -->
    <div data-job-id="${logsJobId}" style="border:1px solid #1e293b;border-radius:0.625rem;overflow:hidden;margin-bottom:0.875rem;box-shadow:0 10px 22px rgba(15,23,42,0.12);">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:0.5625rem 1rem;background:linear-gradient(180deg,#0f172a,#0b1226);gap:0.75rem;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,0.06);">
        <div style="display:flex;align-items:center;gap:0.625rem;">
          <div style="color:#f1f5f9;font-size:0.72rem;font-weight:800;text-transform:uppercase;letter-spacing:0.1em;">Latest run · live flow logs</div>
          ${liveDot}
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          ${logsCount}
          ${logsMeta}
          <button onclick="try{recompute('dashboard')}catch(e){}" style="padding:0.1875rem 0.5rem;background:rgba(255,255,255,0.08);color:#cbd5e1;border:1px solid rgba(255,255,255,0.12);border-radius:4px;font-size:0.65rem;cursor:pointer;font-weight:700;">↻ refresh</button>
        </div>
      </div>
      <pre id="dash-logs" data-job="${logsJobId}" style="margin:0;padding:0.875rem 1rem;background:#0b1220;color:#e2e8f0;height:320px;overflow:auto;font-family:'JetBrains Mono','Menlo','Consolas',monospace;font-size:0.7rem;line-height:1.55;white-space:pre-wrap;word-break:break-word;">${logsBody}</pre>
    </div>

    <!-- 4. RUN HISTORY TABLE -->
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:0.625rem;overflow:hidden;box-shadow:0 2px 6px rgba(15,23,42,0.04);">
      <div style="padding:0.5625rem 1rem;background:#f8fafc;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:0.625rem;">
          <div style="font-size:0.65rem;text-transform:uppercase;color:#64748b;letter-spacing:0.1em;font-weight:700;">Recent runs</div>
        </div>
        <div style="font-size:0.6875rem;color:#94a3b8;font-variant-numeric:tabular-nums;">${jobs.length} total &middot; showing ${Math.min(30, jobs.length)}</div>
      </div>
      <div style="max-height:300px;overflow:auto;">
        <table style="width:100%;border-collapse:collapse;">
          <thead style="background:#fafbfc;position:sticky;top:0;z-index:1;">
            <tr>
              <th style="text-align:left;padding:0.4375rem 0.75rem;font-size:0.625rem;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;">Started</th>
              <th style="text-align:left;padding:0.4375rem 0.75rem;font-size:0.625rem;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;">Job ID</th>
              <th style="text-align:left;padding:0.4375rem 0.75rem;font-size:0.625rem;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;">User</th>
              <th style="text-align:left;padding:0.4375rem 0.75rem;font-size:0.625rem;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;">Status</th>
              <th style="text-align:right;padding:0.4375rem 0.75rem;font-size:0.625rem;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;">Duration</th>
              <th style="text-align:left;padding:0.4375rem 0.75rem;font-size:0.625rem;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;">Upload</th>
            </tr>
          </thead>
          <tbody>${tableRows || '<tr><td colspan="6" style="padding:1.75rem;text-align:center;color:#94a3b8;font-size:0.8125rem;">No runs yet</td></tr>'}</tbody>
        </table>
      </div>
    </div>
    <script>
      (function() {
        const el = document.getElementById('dash-logs')
        if (!el) return
        const jobId = el.getAttribute('data-job')
        const wrapper = el.parentElement
        if (!wrapper) return
        if (typeof window.__dashLastJob === 'undefined') {
          window.__dashLastJob = jobId
          return
        }
        if (window.__dashLastJob !== jobId && jobId) {
          window.__dashLastJob = jobId
          const old = wrapper.querySelector('.dash-flash')
          if (old) old.remove()
          const flash = document.createElement('div')
          flash.className = 'dash-flash'
          flash.innerHTML = '<span style="display:inline-flex;align-items:center;gap:0.5rem;"><span style="width:0.5rem;height:0.5rem;background:#fff;border-radius:9999px;box-shadow:0 0 0 0 #fff;animation:dash-pulse 1.4s infinite;"></span>NEW RUN STARTED</span><span style="margin-left:0.75rem;opacity:0.75;font-family:monospace;font-size:0.65rem;">' + jobId.slice(0,18) + '…</span>'
          flash.style.cssText = 'position:absolute;top:0;left:0;right:0;background:linear-gradient(135deg,#1d4ed8,#3b82f6);color:#fff;text-align:center;padding:0.5rem 0.75rem;font-size:0.7rem;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;z-index:2;box-shadow:0 8px 18px rgba(29,78,216,0.30);transition:opacity 0.4s,transform 0.4s;'
          wrapper.style.position = 'relative'
          wrapper.appendChild(flash)
          setTimeout(() => { flash.style.opacity = '0'; flash.style.transform = 'translateY(-100%)' }, 1600)
          setTimeout(() => flash.remove(), 2200)
          el.scrollTop = 0
        } else {
          el.scrollTop = el.scrollHeight
        }
      })()
    </script>
  `
}
"""


def build():
    grid_item = lambda gid, w3, h3, x3, y3, w12, h12, x12, y12, data: {
        "3":  {"fixed": False, "x": x3,  "y": y3,  "w": w3,  "h": h3},
        "12": {"fixed": False, "x": x12, "y": y12, "w": w12, "h": h12},
        "id": gid,
        "data": data,
    }

    def html_component(cid, html):
        return {
            "id": cid,
            "type": "htmlcomponent",
            "componentInput": {
                "type": "templatev2",
                "fieldType": "template",
                "value": html,
                "connections": [],
            },
            "configuration": {},
            "customCss": {"container": {"class": "", "style": ""}},
        }

    def runnable_component(cid, bun_content, name):
        return {
            "id": cid,
            "type": "htmlcomponent",
            "componentInput": {
                "type": "runnable",
                "fieldType": "any",
                "fields": {},
                "runnable": {
                    "type": "runnableByName",
                    "name": name,
                    "inlineScript": {
                        "content": bun_content,
                        "language": "bun",
                        "schema": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "$schema": "https://json-schema.org/draft/2020-12/schema",
                        },
                        "refreshOn": [],
                    },
                },
            },
            "configuration": {},
            "customCss": {"container": {"class": "", "style": ""}},
        }

    dashboard = {
        "summary": "Loan Pipeline Dashboard",
        "value": {
            "fullscreen": False,
            "norefreshbar": False,
            "darkMode": False,
            "css": {"app": {"viewer": {"style": "background:#f4f6fb;"}}},
            "lazyInitRequire": [],
            "subgrids": {},
            "policy": {"execution_mode": "viewer"},
            "grid": [
                # Header — tall enough for the gradient navy bar
                grid_item(
                    "header",
                    w3=3, h3=2, x3=0, y3=0,
                    w12=12, h12=2, x12=0, y12=0,
                    data=html_component("header", HEADER_HTML),
                ),
                # Main dashboard — bigger so phases + logs + table all fit
                grid_item(
                    "dashboard",
                    w3=3, h3=28, x3=0, y3=5,
                    w12=12, h12=28, x12=0, y12=2,
                    data=runnable_component("dashboard", DASHBOARD_BUN, "dashboard_render"),
                ),
                # Auth + upload cards (only one is visible at a time via the marker JS)
                grid_item(
                    "auth_card",
                    w3=3, h3=8, x3=0, y3=2,
                    w12=12, h12=8, x12=0, y12=2,
                    data=html_component("auth_card", AUTH_HTML),
                ),
                grid_item(
                    "upload_card",
                    w3=3, h3=8, x3=0, y3=2,
                    w12=12, h12=8, x12=0, y12=2,
                    data=html_component("upload_card", UPLOAD_HTML),
                ),
            ],
            "unusedInlineScripts": [],
            "hiddenInlineScripts": [
                {
                    "name": "poll_timer",
                    "fields": {},
                    "type": "runnableByName",
                    "recomputeIds": [],
                    "doNotRecomputeOnInputChanged": False,
                    "autoRefresh": True,
                    "refreshOnStart": True,
                    "inlineScript": {
                        "content": (
                            "if (window.__dashPoll) clearInterval(window.__dashPoll)\n"
                            "window.__dashPoll = setInterval(() => { try { recompute('dashboard') } catch (_) {} }, 1500)\n"
                            "return { polling_started_at: new Date().toISOString(), interval_ms: 1500 }"
                        ),
                        "language": "frontend",
                        "schema": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "$schema": "https://json-schema.org/draft/2020-12/schema",
                        },
                        "refreshOn": [],
                    },
                }
            ],
        },
    }

    out = Path(__file__).parent / "windmill-app-dashboard.json"
    out.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
