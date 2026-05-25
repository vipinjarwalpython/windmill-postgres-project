"""One-shot refactor: collapse the cross-talking dashboard into one self-contained htmlcomponent."""
import json
from pathlib import Path

DASHBOARD_SCRIPT = r'''const FLOW_PATH = 'u/admin/loan_pipeline'

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]))
}

function statusBadge(j) {
  let label='Unknown', fg='#475569', bg='#e2e8f0'
  if (j.type === 'QueuedJob') { if (j.running) { label='Running'; fg='#1d4ed8'; bg='#dbeafe' } else { label='Queued'; fg='#a16207'; bg='#fef3c7' } }
  else if (j.success === true) { label='Success'; fg='#166534'; bg='#dcfce7' }
  else if (j.success === false) { label='Failed'; fg='#991b1b'; bg='#fee2e2' }
  return `<span style="display:inline-block;padding:0.125rem 0.5rem;background:${bg};color:${fg};border-radius:9999px;font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;">${label}</span>`
}

function colorize(line) {
  const safe = esc(line)
  if (/\b(ERROR|FAIL|FAILED|Exception|Traceback)\b/i.test(line)) return `<span style="color:#fca5a5;">${safe}</span>`
  if (/\b(WARN|WARNING)\b/i.test(line)) return `<span style="color:#fcd34d;">${safe}</span>`
  if (/\b(SUCCESS|DONE|OK|Completed)\b/i.test(line)) return `<span style="color:#86efac;">${safe}</span>`
  if (/\b(INFO|Running|Started)\b/i.test(line)) return `<span style="color:#93c5fd;">${safe}</span>`
  return `<span style="color:#e2e8f0;">${safe}</span>`
}

function statCard(title, value, accent, icon) {
  return `<div style="background:#fff;padding:1.1rem;border-radius:0.75rem;border-left:4px solid ${accent};box-shadow:0 1px 3px rgba(0,0,0,0.06);">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
      <div style="font-size:0.7rem;text-transform:uppercase;color:#64748b;letter-spacing:0.08em;font-weight:600;">${esc(title)}</div>
      <div style="font-size:1rem;">${icon}</div>
    </div>
    <div style="font-size:2rem;font-weight:700;color:#0f172a;line-height:1;margin-top:0.5rem;">${value}</div>
  </div>`
}

export async function main() {
  const base = process.env.BASE_INTERNAL_URL || 'http://windmill_server:8000'
  const ws = process.env.WM_WORKSPACE || 'admin'
  const token = process.env.WM_TOKEN || ''
  const wmBase = process.env.WM_BASE_URL || 'http://localhost:8080'
  const auth = { Authorization: `Bearer ${token}` }

  let jobs = [], err = null
  try {
    const url = `${base}/api/w/${ws}/jobs/list?script_path_exact=${FLOW_PATH}&per_page=100`
    const r = await fetch(url, { headers: auth })
    if (!r.ok) err = `${r.status} ${r.statusText}: ${await r.text().catch(()=>'')}`
    else jobs = await r.json()
  } catch (e) { err = e?.message ?? String(e) }

  const stats = { total: jobs.length, running: 0, success: 0, failed: 0 }
  for (const j of jobs) {
    if (j.type === 'QueuedJob') stats.running++
    else if (j.success === true) stats.success++
    else if (j.success === false) stats.failed++
  }

  let logsHtml = `<div style="color:#64748b;padding:1rem;">No pipeline runs yet</div>`
  let logsHeader = 'Flow logs'
  if (jobs.length > 0) {
    const latest = jobs[0]
    logsHeader = `Flow logs · ${esc(latest.id.slice(0,12))}… · ${statusBadge(latest)}`
    try {
      const r = await fetch(`${base}/api/w/${ws}/jobs_u/get_flow_all_logs/${latest.id}`, { headers: auth })
      if (r.ok) {
        const text = await r.text()
        const lines = text.split(/\r?\n/).slice(-400)
        logsHtml = lines.map(colorize).join('\n')
      } else {
        logsHtml = `<span style="color:#fca5a5;">log fetch failed: ${r.status}</span>`
      }
    } catch (e) { logsHtml = `<span style="color:#fca5a5;">${esc(e?.message ?? e)}</span>` }
  }

  const tableRows = jobs.slice(0, 30).map(j => {
    const args = j.args || {}
    const started = j.started_at || j.created_at
    const startedStr = started ? new Date(started).toLocaleString() : '—'
    const dur = j.duration_ms != null ? (j.duration_ms/1000).toFixed(2) + 's' : '—'
    const file = args.original_filename || (args.file_path||'').split('/').pop() || '—'
    const link = `${wmBase}/run/${j.id}?workspace=${ws}`
    return `<tr style="border-bottom:1px solid #e5e7eb;">
      <td style="padding:0.5rem 0.625rem;font-size:0.8125rem;color:#0f172a;white-space:nowrap;">${esc(startedStr)}</td>
      <td style="padding:0.5rem 0.625rem;font-family:monospace;font-size:0.75rem;"><a href="${link}" target="_blank" rel="noopener" style="color:#1d4ed8;text-decoration:none;">${esc(j.id.slice(0,12))}…</a></td>
      <td style="padding:0.5rem 0.625rem;font-size:0.8125rem;color:#475569;">${esc(j.created_by ?? '—')}</td>
      <td style="padding:0.5rem 0.625rem;">${statusBadge(j)}</td>
      <td style="padding:0.5rem 0.625rem;font-size:0.8125rem;color:#475569;text-align:right;">${esc(dur)}</td>
      <td style="padding:0.5rem 0.625rem;font-size:0.8125rem;color:#475569;">${esc(file)}</td>
    </tr>`
  }).join('')

  const errBanner = err ? `<div style="background:#fef2f2;border:1px solid #fecaca;color:#991b1b;padding:0.625rem 0.875rem;border-radius:0.5rem;font-size:0.8125rem;margin-bottom:0.75rem;"><strong>Could not load jobs:</strong> ${esc(err)}</div>` : ''

  return `
    ${errBanner}
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.875rem;margin-bottom:1rem;">
      ${statCard('Total runs', stats.total, '#3b82f6', '📊')}
      ${statCard('Running / queued', stats.running, '#2563eb', '▶️')}
      ${statCard('Succeeded', stats.success, '#16a34a', '✅')}
      ${statCard('Failed', stats.failed, '#dc2626', '⚠️')}
    </div>
    <div style="background:#fff;border-radius:0.75rem;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:1rem;">
      <div style="padding:0.625rem 0.875rem;background:#f8fafc;border-bottom:1px solid #e5e7eb;font-size:0.75rem;text-transform:uppercase;color:#64748b;letter-spacing:0.06em;font-weight:600;">
        Recent runs (${jobs.length})
      </div>
      <div style="max-height:280px;overflow:auto;">
        <table style="width:100%;border-collapse:collapse;">
          <thead style="background:#f8fafc;position:sticky;top:0;z-index:1;">
            <tr>
              <th style="text-align:left;padding:0.5rem 0.625rem;font-size:0.7rem;text-transform:uppercase;color:#64748b;font-weight:600;letter-spacing:0.04em;">Started</th>
              <th style="text-align:left;padding:0.5rem 0.625rem;font-size:0.7rem;text-transform:uppercase;color:#64748b;font-weight:600;letter-spacing:0.04em;">Job ID</th>
              <th style="text-align:left;padding:0.5rem 0.625rem;font-size:0.7rem;text-transform:uppercase;color:#64748b;font-weight:600;letter-spacing:0.04em;">User</th>
              <th style="text-align:left;padding:0.5rem 0.625rem;font-size:0.7rem;text-transform:uppercase;color:#64748b;font-weight:600;letter-spacing:0.04em;">Status</th>
              <th style="text-align:right;padding:0.5rem 0.625rem;font-size:0.7rem;text-transform:uppercase;color:#64748b;font-weight:600;letter-spacing:0.04em;">Duration</th>
              <th style="text-align:left;padding:0.5rem 0.625rem;font-size:0.7rem;text-transform:uppercase;color:#64748b;font-weight:600;letter-spacing:0.04em;">Upload</th>
            </tr>
          </thead>
          <tbody>${tableRows || '<tr><td colspan="6" style="padding:1.5rem;text-align:center;color:#94a3b8;">No runs yet — upload a file via FastAPI to start one</td></tr>'}</tbody>
        </table>
      </div>
    </div>
    <div style="border-radius:0.5rem;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:0.5rem 0.875rem;background:#1e293b;">
        <div style="color:#e2e8f0;font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;">${logsHeader}</div>
        <div style="color:#64748b;font-size:0.7rem;">Updated ${new Date().toLocaleTimeString()}</div>
      </div>
      <pre style="margin:0;padding:0.875rem 1rem;background:#0f172a;color:#e2e8f0;height:320px;overflow:auto;font-family:'JetBrains Mono','Menlo',monospace;font-size:0.75rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;">${logsHtml}</pre>
    </div>
  `
}
'''

POLL_TIMER_NEW = (
    "if (window.__dashPoll) clearInterval(window.__dashPoll)\n"
    "window.__dashPoll = setInterval(() => { try { recompute('dashboard') } catch (_) {} }, 5000)\n"
    "return { polling_started_at: new Date().toISOString(), interval_ms: 5000 }"
)

REFRESH_BTN_NEW = (
    "recompute('dashboard')\n"
    "return { triggered_at: new Date().toISOString() }"
)

DASHBOARD_COMPONENT = {
    "3": {"fixed": False, "x": 0, "y": 7, "w": 3, "h": 18},
    "12": {"fixed": False, "x": 0, "y": 7, "w": 12, "h": 18},
    "id": "dashboard",
    "data": {
        "id": "dashboard",
        "type": "htmlcomponent",
        "componentInput": {
            "type": "runnable",
            "fieldType": "any",
            "fields": {},
            "runnable": {
                "type": "runnableByName",
                "name": "dashboard_render",
                "inlineScript": {
                    "content": DASHBOARD_SCRIPT,
                    "language": "bun",
                    "schema": {"type": "object", "properties": {}, "required": [], "$schema": "https://json-schema.org/draft/2020-12/schema"},
                    "refreshOn": [],
                },
            },
        },
        "configuration": {},
        "customCss": {"container": {"class": "", "style": ""}},
    },
}

p = Path("windmill-app-dashboard.json")
d = json.loads(p.read_text(encoding="utf-8"))

KEEP_GRID = {"header", "refresh_btn"}
before_g = len(d["value"]["grid"])
d["value"]["grid"] = [g for g in d["value"]["grid"] if g["id"] in KEEP_GRID]
print(f"Grid components: {before_g} -> {len(d['value']['grid'])} (kept {KEEP_GRID})")

for g in d["value"]["grid"]:
    if g["id"] == "refresh_btn":
        g["data"]["componentInput"]["runnable"]["inlineScript"]["content"] = REFRESH_BTN_NEW
        g["data"]["componentInput"]["runnable"]["inlineScript"]["language"] = "frontend"

d["value"]["grid"].append(DASHBOARD_COMPONENT)
print(f"Grid IDs now: {[g['id'] for g in d['value']['grid']]}")

KEEP_HIDDEN = {"poll_timer"}
before_h = len(d["value"]["hiddenInlineScripts"])
d["value"]["hiddenInlineScripts"] = [s for s in d["value"]["hiddenInlineScripts"] if s["name"] in KEEP_HIDDEN]
print(f"Hidden scripts: {before_h} -> {len(d['value']['hiddenInlineScripts'])} (kept {KEEP_HIDDEN})")

for s in d["value"]["hiddenInlineScripts"]:
    if s["name"] == "poll_timer":
        s["inlineScript"]["content"] = POLL_TIMER_NEW

p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nWrote {p}")
print(f"Validating...")
d2 = json.loads(p.read_text(encoding="utf-8"))
print(f"OK: {len(d2['value']['grid'])} grid items, {len(d2['value']['hiddenInlineScripts'])} hidden scripts")
