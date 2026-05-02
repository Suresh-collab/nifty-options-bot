import { useEffect, useState } from 'react'
import { useStore } from '../store'

// ─── Toggle switch ───────────────────────────────────────────────────────────

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 transition-colors focus:outline-none
        ${checked ? 'bg-terminal-blue border-terminal-blue' : 'bg-[#1e293b] border-[#334155]'}
        ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
    >
      <span
        className={`pointer-events-none inline-block h-3.5 w-3.5 mt-0.5 rounded-full bg-white shadow transition-transform
          ${checked ? 'translate-x-5' : 'translate-x-0.5'}`}
      />
    </button>
  )
}

// ─── Flag descriptions ───────────────────────────────────────────────────────

const FLAG_META = {
  ENABLE_ML_SIGNAL: {
    label: 'ML Signal',
    desc: 'Activates ONNX/XGBoost ML direction signal instead of rule-based engine.',
    warn: 'Only enable after model is trained and validated.',
  },
  ENABLE_LIVE_BROKER: {
    label: 'Live Broker',
    desc: 'Routes orders to Zerodha Kite Connect instead of the paper adapter.',
    warn: 'REAL MONEY. Requires API keys stored via /broker/api-keys.',
  },
  ENABLE_AUTO_EXECUTION: {
    label: 'Auto Execution',
    desc: 'Automatically places broker orders when a signal fires (no manual confirm).',
    warn: 'Only valid when ENABLE_LIVE_BROKER is also enabled.',
  },
}

// ─── Audit log row ───────────────────────────────────────────────────────────

function AuditRow({ entry }) {
  const [open, setOpen] = useState(false)
  const ts = entry.created_at
    ? new Date(entry.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'medium' })
    : '—'

  const actionColor = {
    KILL_SWITCH:          'text-red-400',
    FLAG_TOGGLE:          'text-yellow-400',
    ORDER_PLACE_ATTEMPT:  'text-blue-400',
    ORDER_CANCEL_ATTEMPT: 'text-orange-400',
    API_KEYS_STORED:      'text-purple-400',
  }[entry.action] || 'text-[#94a3b8]'

  return (
    <>
      <tr
        className="border-b border-[#0d1526] hover:bg-white/[0.02] cursor-pointer transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <td className="py-2 pr-4 text-[#475569] font-mono text-[10px] whitespace-nowrap">{ts}</td>
        <td className={`py-2 pr-4 font-mono text-[10px] font-bold whitespace-nowrap ${actionColor}`}>{entry.action}</td>
        <td className="py-2 pr-4 font-mono text-[10px] text-[#64748b]">{entry.actor}</td>
        <td className="py-2 font-mono text-[10px] text-[#334155]">{open ? '▲' : '▼'}</td>
      </tr>
      {open && (
        <tr className="border-b border-[#0d1526]">
          <td colSpan={4} className="pb-3 pt-1">
            <pre className="text-[10px] font-mono text-[#64748b] bg-[#070b14] rounded p-3 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(entry.payload, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}

// ─── component ──────────────────────────────────────────────────────────────

export default function AdminPanel() {
  const {
    adminFlags, adminFlagsLoading, fetchAdminFlags, toggleAdminFlag,
    auditLog, auditLogLoading, fetchAuditLog,
  } = useStore()

  const [auditOffset, setAuditOffset] = useState(0)
  const LIMIT = 20

  useEffect(() => {
    fetchAdminFlags()
    fetchAuditLog(0, LIMIT)
  }, [])

  function loadMore() {
    const next = auditOffset + LIMIT
    setAuditOffset(next)
    fetchAuditLog(next, LIMIT)
  }

  function loadPrev() {
    const prev = Math.max(0, auditOffset - LIMIT)
    setAuditOffset(prev)
    fetchAuditLog(prev, LIMIT)
  }

  return (
    <div className="space-y-6">
      {/* ── Feature flags ─────────────────────────────────────────────────── */}
      <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-5">
        <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-4">Feature Flags</div>
        <div className="space-y-4">
          {(adminFlags || []).map(flag => {
            const meta = FLAG_META[flag.name] || { label: flag.name, desc: '', warn: '' }
            return (
              <div key={flag.name} className="flex items-start justify-between gap-4 pb-4 border-b border-[#1e293b] last:border-0 last:pb-0">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-mono text-xs font-bold text-white">{meta.label}</span>
                    <span className="text-[9px] font-mono text-[#334155]">{flag.name}</span>
                    {flag.enabled && meta.warn && (
                      <span className="text-[9px] font-mono text-yellow-500 bg-yellow-500/10 border border-yellow-500/20 rounded px-1.5 py-0.5">
                        ACTIVE
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] font-mono text-[#64748b]">{meta.desc}</div>
                  {flag.enabled && meta.warn && (
                    <div className="text-[10px] font-mono text-yellow-600 mt-1">{meta.warn}</div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 pt-0.5">
                  <span className={`text-[9px] font-mono ${flag.enabled ? 'text-green-400' : 'text-[#475569]'}`}>
                    {flag.enabled ? 'ON' : 'OFF'}
                  </span>
                  <Toggle
                    checked={flag.enabled}
                    disabled={adminFlagsLoading}
                    onChange={val => toggleAdminFlag(flag.name, val)}
                  />
                </div>
              </div>
            )
          })}
          {!adminFlagsLoading && (!adminFlags || adminFlags.length === 0) && (
            <div className="text-[#475569] font-mono text-xs">No flags loaded.</div>
          )}
        </div>
      </div>

      {/* ── Audit log ─────────────────────────────────────────────────────── */}
      <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">Audit Log</div>
          <button
            onClick={() => fetchAuditLog(auditOffset, LIMIT)}
            className="text-[9px] font-mono text-[#64748b] hover:text-white transition-colors"
          >
            Refresh
          </button>
        </div>

        {auditLogLoading ? (
          <div className="text-[#475569] font-mono text-xs py-4 text-center">Loading…</div>
        ) : !auditLog || auditLog.length === 0 ? (
          <div className="text-[#475569] font-mono text-xs py-4 text-center">No audit entries yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] font-mono">
              <thead>
                <tr className="border-b border-[#1e293b]">
                  {['Timestamp', 'Action', 'Actor', ''].map(h => (
                    <th key={h} className="pb-2 pr-4 text-left text-[#475569] font-normal uppercase tracking-wider text-[9px]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {auditLog.map(entry => <AuditRow key={entry.id} entry={entry} />)}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-[#1e293b]">
          <button
            onClick={loadPrev}
            disabled={auditOffset === 0}
            className="text-[10px] font-mono text-[#64748b] hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ← Newer
          </button>
          <span className="text-[9px] font-mono text-[#334155]">
            {auditOffset + 1}–{auditOffset + (auditLog?.length || 0)}
          </span>
          <button
            onClick={loadMore}
            disabled={!auditLog || auditLog.length < LIMIT}
            className="text-[10px] font-mono text-[#64748b] hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Older →
          </button>
        </div>
      </div>
    </div>
  )
}
