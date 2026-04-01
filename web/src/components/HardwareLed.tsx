'use client';
// ── Hardware state machine ────────────────────────────────────────────────────
export type HwState =
  | 'standby'
  | 'listening'
  | 'processing'
  | 'thinking'
  | 'speaking'
  | 'success'
  | 'error';
interface LedConfig {
  color: string;       // Tailwind bg color
  glow: string;        // box-shadow color (CSS)
  animation: string;   // CSS animation class
  label: string;
  ring: string;        // ring border color
}
const LED_CONFIG: Record<HwState, LedConfig> = {
  standby:    { color: 'bg-blue-500',    glow: 'rgba(59,130,246,0.6)',   animation: 'hw-breathe-slow', label: '待机',    ring: 'border-blue-500/40' },
  listening:  { color: 'bg-green-400',   glow: 'rgba(74,222,128,0.8)',   animation: 'hw-pulse-fast',   label: '录音中',  ring: 'border-green-400/60' },
  processing: { color: 'bg-amber-400',   glow: 'rgba(251,191,36,0.7)',   animation: 'hw-spin-glow',    label: '识别中',  ring: 'border-amber-400/50' },
  thinking:   { color: 'bg-purple-500',  glow: 'rgba(168,85,247,0.6)',   animation: 'hw-breathe-slow', label: '思考中',  ring: 'border-purple-500/40' },
  speaking:   { color: 'bg-cyan-400',    glow: 'rgba(34,211,238,0.7)',   animation: 'hw-wave-glow',    label: '播放中',  ring: 'border-cyan-400/50' },
  success:    { color: 'bg-emerald-400', glow: 'rgba(52,211,153,0.9)',   animation: 'hw-flash',        label: '成功',    ring: 'border-emerald-400/70' },
  error:      { color: 'bg-red-500',     glow: 'rgba(239,68,68,0.9)',    animation: 'hw-flash',        label: '失败',    ring: 'border-red-500/70' },
};
// Detect success/error from agent text
const SUCCESS_RE = /完成|成功|好的|搞定|明白|收到|没问题|OK|ok|done/i;
const ERROR_RE   = /失败|错误|出错|无法|不能|抱歉|sorry|error|failed/i;
export function detectHwState(agentText: string): 'success' | 'error' | null {
  if (ERROR_RE.test(agentText)) return 'error';
  if (SUCCESS_RE.test(agentText)) return 'success';
  return null;
}
// ── Component ─────────────────────────────────────────────────────────────────
interface Props {
  hwState: HwState;
}
export function HardwareLed({ hwState }: Props) {
  const cfg = LED_CONFIG[hwState];
  return (
    <div className="flex flex-col items-center gap-3">
      {/* LED ring */}
      <div className="relative flex items-center justify-center">
        {/* Outer glow ring */}
        <div
          className={`absolute rounded-full border-2 ${cfg.ring} hw-ring`}
          style={{ width: 88, height: 88 }}
        />
        {/* LED dot */}
        <div
          className={`w-14 h-14 rounded-full ${cfg.color} ${cfg.animation} flex items-center justify-center`}
          style={{ boxShadow: `0 0 24px 8px ${cfg.glow}` }}
        >
          <LedIcon state={hwState} />
        </div>
      </div>
      {/* State label */}
      <div className="flex flex-col items-center gap-0.5">
        <span className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">HW STATE</span>
        <span className={`text-xs font-semibold ${stateLabelColor(hwState)}`}>{cfg.label}</span>
      </div>
    </div>
  );
}
function stateLabelColor(s: HwState) {
  const map: Record<HwState, string> = {
    standby:    'text-blue-400',
    listening:  'text-green-400',
    processing: 'text-amber-400',
    thinking:   'text-purple-400',
    speaking:   'text-cyan-400',
    success:    'text-emerald-400',
    error:      'text-red-400',
  };
  return map[s];
}
function LedIcon({ state }: { state: HwState }) {
  const cls = 'text-white/80';
  if (state === 'listening') return <span className={`text-lg ${cls}`}>🎤</span>;
  if (state === 'processing') return <span className={`text-lg ${cls}`}>🔤</span>;
  if (state === 'thinking')   return <span className={`text-lg ${cls}`}>🧠</span>;
  if (state === 'speaking')   return <span className={`text-lg ${cls}`}>🔊</span>;
  if (state === 'success')    return <span className={`text-lg ${cls}`}>✓</span>;
  if (state === 'error')      return <span className={`text-lg ${cls}`}>✗</span>;
  return <span className={`text-lg ${cls}`}>◉</span>;
}
