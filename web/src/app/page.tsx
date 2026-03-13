'use client';

import { useReducer, useEffect, useRef, useCallback, useState } from 'react';
import { WsClient, PipelineState, WsEvent } from '@/lib/ws-client';
import { MicCapture, AudioPlayer } from '@/lib/audio';

// ─── Types ────────────────────────────────────────────────────────────────────

type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  streaming: boolean;
};

type AppState = {
  pipelineState: PipelineState;
  connected: boolean;
  messages: Message[];
  currentAsrText: string;
  wsUrl: string;
};

type Action =
  | { type: 'SET_CONNECTED'; connected: boolean }
  | { type: 'SET_PIPELINE_STATE'; state: PipelineState }
  | { type: 'SET_ASR_TEXT'; text: string }
  | { type: 'PUSH_USER_MESSAGE'; text: string }
  | { type: 'START_ASSISTANT_MESSAGE'; id: string }
  | { type: 'APPEND_ASSISTANT_CHUNK'; id: string; text: string }
  | { type: 'FINISH_ASSISTANT_MESSAGE'; id: string; text: string }
  | { type: 'SET_WS_URL'; url: string };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected };
    case 'SET_PIPELINE_STATE':
      return { ...state, pipelineState: action.state };
    case 'SET_ASR_TEXT':
      return { ...state, currentAsrText: action.text };
    case 'PUSH_USER_MESSAGE':
      return {
        ...state,
        currentAsrText: '',
        messages: [
          ...state.messages,
          { id: Date.now().toString(), role: 'user', text: action.text, streaming: false },
        ],
      };
    case 'START_ASSISTANT_MESSAGE':
      return {
        ...state,
        messages: [
          ...state.messages,
          { id: action.id, role: 'assistant', text: '', streaming: true },
        ],
      };
    case 'APPEND_ASSISTANT_CHUNK':
      return {
        ...state,
        messages: state.messages.map(m =>
          m.id === action.id ? { ...m, text: m.text + action.text } : m
        ),
      };
    case 'FINISH_ASSISTANT_MESSAGE':
      return {
        ...state,
        messages: state.messages.map(m =>
          m.id === action.id ? { ...m, text: action.text, streaming: false } : m
        ),
      };
    case 'SET_WS_URL':
      return { ...state, wsUrl: action.url };
    default:
      return state;
  }
}

// ─── Pipeline Steps ────────────────────────────────────────────────────────────

type StepKey = PipelineState | 'playing';

const PIPELINE_STEPS: { key: StepKey; label: string; icon: string }[] = [
  { key: 'listening', label: 'Recording', icon: '🎤' },
  { key: 'processing', label: 'ASR', icon: '🔤' },
  { key: 'wake', label: 'Agent', icon: '🧠' },
  { key: 'speaking', label: 'TTS', icon: '🔊' },
  { key: 'playing', label: 'Playing', icon: '▶' },
];

const STATE_ORDER: Record<string, number> = {
  idle: -1,
  disconnected: -1,
  follow_up: 0,
  listening: 0,
  processing: 1,
  wake: 2,
  speaking: 3,
  playing: 4,
};

// ─── Settings Storage ─────────────────────────────────────────────────────────

interface Settings {
  wsUrl: string;
  asrProvider: string;
  asrApiKey: string;
  agentProvider: string;
  ttsProvider: string;
}

const DEFAULT_SETTINGS: Settings = {
  wsUrl: 'ws://localhost:8765/ws',
  asrProvider: 'whisper',
  asrApiKey: '',
  agentProvider: 'openclaw',
  ttsProvider: 'edge_tts',
};

function loadSettings(): Settings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = localStorage.getItem('listenclaw_settings');
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    // ignore
  }
  return DEFAULT_SETTINGS;
}

function saveSettings(s: Settings) {
  localStorage.setItem('listenclaw_settings', JSON.stringify(s));
}

// ─── Main Component ────────────────────────────────────────────────────────────

export default function Home() {
  const [state, dispatch] = useReducer(reducer, {
    pipelineState: 'disconnected',
    connected: false,
    messages: [],
    currentAsrText: '',
    wsUrl: 'ws://localhost:8765/ws',
  });

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [isRecording, setIsRecording] = useState(false);
  const isRecordingRef = useRef(false);

  const wsRef = useRef<WsClient | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<AudioPlayer | null>(null);
  const ttsBufferRef = useRef<string[]>([]);        // base64 strings per segment
  const pttBufferRef = useRef<ArrayBuffer[]>([]);   // raw PCM chunks during PTT
  const currentAssistantIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const spaceDownRef = useRef(false);

  // Keep ref in sync with state
  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  // ─ Init settings from localStorage ─
  useEffect(() => {
    const s = loadSettings();
    setSettings(s);
    dispatch({ type: 'SET_WS_URL', url: s.wsUrl });
  }, []);

  // ─ Audio player ─
  useEffect(() => {
    playerRef.current = new AudioPlayer();
    return () => {
      playerRef.current?.stop();
    };
  }, []);

  // ─ WebSocket connection ─
  useEffect(() => {
    const url = state.wsUrl;
    const client = new WsClient(url);
    wsRef.current = client;

    const unsub = client.on((event: WsEvent) => {
      switch (event.type) {
        case 'connected':
          dispatch({ type: 'SET_CONNECTED', connected: true });
          dispatch({ type: 'SET_PIPELINE_STATE', state: 'idle' });
          break;

        case 'disconnected':
          dispatch({ type: 'SET_CONNECTED', connected: false });
          dispatch({ type: 'SET_PIPELINE_STATE', state: 'disconnected' });
          break;

        case 'state':
          dispatch({ type: 'SET_PIPELINE_STATE', state: event.state });
          break;

        case 'asr_result':
          dispatch({ type: 'SET_ASR_TEXT', text: event.text });
          dispatch({ type: 'PUSH_USER_MESSAGE', text: event.text });
          break;

        case 'agent_chunk': {
          if (!currentAssistantIdRef.current) {
            const id = `assistant-${Date.now()}`;
            currentAssistantIdRef.current = id;
            dispatch({ type: 'START_ASSISTANT_MESSAGE', id });
          }
          dispatch({
            type: 'APPEND_ASSISTANT_CHUNK',
            id: currentAssistantIdRef.current!,
            text: event.text,
          });
          break;
        }

        case 'agent_done': {
          if (currentAssistantIdRef.current) {
            dispatch({
              type: 'FINISH_ASSISTANT_MESSAGE',
              id: currentAssistantIdRef.current,
              text: event.text,
            });
            currentAssistantIdRef.current = null;
          } else {
            const id = `assistant-${Date.now()}`;
            dispatch({ type: 'START_ASSISTANT_MESSAGE', id });
            dispatch({ type: 'FINISH_ASSISTANT_MESSAGE', id, text: event.text });
          }
          break;
        }

        case 'tts_chunk':
          ttsBufferRef.current.push(event.data);
          break;

        case 'tts_segment_done': {
          const chunks = ttsBufferRef.current.splice(0);
          if (chunks.length > 0) {
            try {
              // Each chunk is independently base64-encoded — decode each then concatenate bytes
              const arrays = chunks.map(b64 => {
                const bin = atob(b64);
                const arr = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                return arr;
              });
              const totalLen = arrays.reduce((s, a) => s + a.length, 0);
              const mp3 = new Uint8Array(totalLen);
              let off = 0;
              for (const a of arrays) { mp3.set(a, off); off += a.length; }
              playerRef.current?.enqueue(mp3.buffer);
            } catch (e) {
              console.error('TTS decode error:', e);
            }
          }
          break;
        }

        case 'tts_done':
          ttsBufferRef.current = [];
          currentAssistantIdRef.current = null;
          break;

        case 'error':
          console.error('Server error:', event.message);
          break;
      }
    });

    client.connect();

    return () => {
      unsub();
      client.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.wsUrl]);

  // ─ Scroll to bottom on new messages ─
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.messages]);

  // ─ Recording handlers (PTT: accumulate locally, send on release) ─
  const startRecording = useCallback(async () => {
    if (isRecordingRef.current) return;
    // Resume AudioContext during user gesture so autoplay policy doesn't block TTS
    playerRef.current?.resume();
    pttBufferRef.current = [];
    try {
      const mic = new MicCapture((pcm) => {
        pttBufferRef.current.push(pcm);
      });
      await mic.start();
      micRef.current = mic;
      isRecordingRef.current = true;
      setIsRecording(true);
    } catch (e) {
      console.error('Mic error:', e);
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (!isRecordingRef.current) return;
    micRef.current?.stop();
    micRef.current = null;
    isRecordingRef.current = false;
    setIsRecording(false);

    // Concatenate all captured PCM chunks and send as one ptt_audio message
    const chunks = pttBufferRef.current.splice(0);
    if (chunks.length > 0) {
      const totalLen = chunks.reduce((s, b) => s + b.byteLength, 0);
      const combined = new Uint8Array(totalLen);
      let offset = 0;
      for (const chunk of chunks) {
        combined.set(new Uint8Array(chunk), offset);
        offset += chunk.byteLength;
      }
      wsRef.current?.sendPttAudio(combined.buffer);
    }
  }, []);

  // ─ Keyboard shortcuts ─
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;

      if (e.code === 'Space' && !spaceDownRef.current) {
        e.preventDefault();
        spaceDownRef.current = true;
        startRecording();
      }
      if ((e.key === 'i' || e.key === 'I') && !e.metaKey && !e.ctrlKey) {
        wsRef.current?.sendInterrupt();
        playerRef.current?.stop();
      }
      if (e.key === 'Escape') {
        setSettingsOpen(false);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        spaceDownRef.current = false;
        stopRecording();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [startRecording, stopRecording]);

  // ─ Settings save ─
  const handleSaveSettings = () => {
    saveSettings(settings);
    dispatch({ type: 'SET_WS_URL', url: settings.wsUrl });
    setSettingsOpen(false);
  };

  // ─ Derive pipeline step index ─
  const activeStepIndex = STATE_ORDER[state.pipelineState] ?? -1;

  // ─ Mic button class ─
  const micBtnClass = () => {
    const base = 'mic-btn';
    if (!state.connected) return `${base} mic-btn--idle`;
    if (isRecording || state.pipelineState === 'listening') return `${base} mic-btn--listening`;
    if (state.pipelineState === 'processing') return `${base} mic-btn--processing`;
    if (state.pipelineState === 'speaking') return `${base} mic-btn--speaking`;
    return `${base} mic-btn--idle`;
  };

  const stateLabel = {
    disconnected: 'Disconnected',
    idle: 'Ready',
    listening: 'Listening…',
    processing: 'Transcribing…',
    wake: 'Thinking…',
    speaking: 'Speaking…',
    follow_up: 'Follow-up…',
  }[state.pipelineState] ?? '';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col select-none">

      {/* ─── Header ─── */}
      <header className="flex items-center justify-between px-5 py-4 border-b border-gray-800/60 backdrop-blur-sm bg-gray-950/80 sticky top-0 z-10">
        {/* Connection status */}
        <div className="flex items-center gap-2 min-w-[120px]">
          <span
            className={`w-2 h-2 rounded-full transition-all duration-500 ${
              state.connected
                ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]'
                : 'bg-gray-600'
            }`}
          />
          <span className="text-xs text-gray-500">
            {state.connected ? 'Connected' : 'Connecting…'}
          </span>
        </div>

        {/* Logo */}
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold tracking-tight text-white">ListenClaw</span>
          <span className="hidden sm:inline text-xs text-gray-600 font-mono">voice gateway</span>
        </div>

        {/* Settings button */}
        <div className="min-w-[120px] flex justify-end">
          <button
            onClick={() => setSettingsOpen(true)}
            className="p-2 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition-colors"
            aria-label="Open settings"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
          </button>
        </div>
      </header>

      {/* ─── Pipeline Status Bar ─── */}
      <div className="flex items-center justify-center gap-1 px-4 py-2.5 border-b border-gray-800/40 bg-gray-900/30 overflow-x-auto">
        {PIPELINE_STEPS.map((step, idx) => {
          const isActive = idx === activeStepIndex;
          const isDone = idx < activeStepIndex;
          return (
            <div key={step.key} className="flex items-center gap-1 flex-shrink-0">
              <div
                className={`
                  flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium
                  transition-all duration-300
                  ${isActive
                    ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-[0_0_10px_rgba(99,102,241,0.25)]'
                    : isDone
                      ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                      : 'bg-transparent text-gray-600 border border-gray-800/60'
                  }
                `}
              >
                <span className="text-xs">{step.icon}</span>
                <span className="hidden sm:inline">{step.label}</span>
                {isActive && (
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                )}
              </div>
              {idx < PIPELINE_STEPS.length - 1 && (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                  className={`transition-colors duration-300 flex-shrink-0 ${isDone ? 'text-emerald-700' : 'text-gray-800'}`}>
                  <path d="M9 18l6-6-6-6" />
                </svg>
              )}
            </div>
          );
        })}
      </div>

      {/* ─── Chat Area ─── */}
      <div className="flex-1 overflow-y-auto px-4 py-5 max-w-2xl w-full mx-auto space-y-3">
        {state.messages.length === 0 && (
          <div className="flex flex-col items-center justify-center pt-16 gap-4 text-center">
            <div className="text-5xl opacity-20 select-none">🎙️</div>
            <div className="space-y-1.5">
              <p className="text-gray-500 text-sm">
                Hold{' '}
                <kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-700 rounded text-gray-400 text-xs font-mono">
                  Space
                </kbd>{' '}
                or press the mic button to start
              </p>
              <p className="text-gray-700 text-xs">
                Press{' '}
                <kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-700 rounded text-gray-600 text-xs font-mono">
                  i
                </kbd>{' '}
                to interrupt the AI response
              </p>
            </div>
          </div>
        )}

        {state.messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-end gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-6 h-6 rounded-full bg-indigo-500/15 border border-indigo-500/25 flex items-center justify-center text-xs flex-shrink-0 mb-0.5">
                🤖
              </div>
            )}
            <div
              className={`
                max-w-[78%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed
                ${msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-sm'
                  : 'bg-gray-800/80 text-gray-100 rounded-bl-sm border border-gray-700/40'
                }
              `}
            >
              {msg.text || (msg.streaming ? '' : '…')}
              {msg.streaming && (
                <span className="inline-block w-0.5 h-3.5 bg-current rounded-sm ml-0.5 animate-[blink_1s_ease-in-out_infinite] opacity-80" />
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-6 h-6 rounded-full bg-indigo-600/20 border border-indigo-500/25 flex items-center justify-center text-xs flex-shrink-0 mb-0.5">
                🎤
              </div>
            )}
          </div>
        ))}

        {/* Live ASR preview */}
        {state.currentAsrText && (
          <div className="flex justify-end items-end gap-2">
            <div className="max-w-[78%] px-4 py-2.5 rounded-2xl rounded-br-sm text-sm leading-relaxed bg-indigo-600/30 text-indigo-200/70 border border-indigo-500/20 italic">
              {state.currentAsrText}…
            </div>
            <div className="w-6 h-6 rounded-full bg-indigo-600/20 border border-indigo-500/25 flex items-center justify-center text-xs flex-shrink-0 mb-0.5 opacity-50">
              🎤
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ─── Mic Button Area ─── */}
      <div className="flex flex-col items-center gap-3 py-7 border-t border-gray-800/60 bg-gray-900/20">
        {/* State label */}
        <div className="h-4 flex items-center">
          <span className="text-[10px] text-gray-600 uppercase tracking-[0.15em] font-medium">
            {stateLabel}
          </span>
        </div>

        {/* Mic button */}
        <button
          className={micBtnClass()}
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={stopRecording}
          onTouchStart={(e) => { e.preventDefault(); startRecording(); }}
          onTouchEnd={(e) => { e.preventDefault(); stopRecording(); }}
          disabled={!state.connected}
          aria-label="Push to talk"
        >
          <span className="mic-btn__ring" aria-hidden />
          <span className="mic-btn__core">
            {state.pipelineState === 'processing' ? (
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="animate-spin" style={{ animationDuration: '0.8s' }}>
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
              </svg>
            ) : (state.pipelineState === 'speaking' || state.pipelineState === 'wake') ? (
              <span className="wave-bars" aria-hidden>
                <i /><i /><i /><i /><i />
              </span>
            ) : (
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            )}
          </span>
        </button>

        {/* Interrupt button */}
        <div className="h-8 flex items-center">
          {(state.pipelineState === 'speaking' || state.pipelineState === 'processing' || state.pipelineState === 'wake') && (
            <button
              onClick={() => {
                wsRef.current?.sendInterrupt();
                playerRef.current?.stop();
              }}
              className="px-4 py-1 rounded-full text-xs text-red-400/80 border border-red-500/25 hover:bg-red-500/10 hover:text-red-300 transition-all duration-200"
            >
              Interrupt
            </button>
          )}
        </div>

        <p className="text-[10px] text-gray-700 tracking-wide">
          Hold <span className="font-mono text-gray-600">Space</span> to talk · <span className="font-mono text-gray-600">i</span> to interrupt
        </p>
      </div>

      {/* ─── Settings Overlay ─── */}
      <div
        className={`fixed inset-0 z-40 transition-all duration-300 ${
          settingsOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={() => setSettingsOpen(false)}
      >
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      </div>

      {/* ─── Settings Drawer ─── */}
      <aside
        className={`
          fixed top-0 right-0 h-full w-full max-w-xs z-50
          bg-gray-900 border-l border-gray-700/50 shadow-2xl
          flex flex-col
          transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]
          ${settingsOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
        aria-label="Settings panel"
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-white">Settings</h2>
          <button
            onClick={() => setSettingsOpen(false)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition-colors"
            aria-label="Close settings"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Drawer body */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">

          {/* Server URL */}
          <section className="space-y-3">
            <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.12em]">Server</h3>
            <div className="space-y-1.5">
              <label className="block text-xs text-gray-400">WebSocket URL</label>
              <input
                type="text"
                value={settings.wsUrl}
                onChange={(e) => setSettings(s => ({ ...s, wsUrl: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-xs text-white font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500/60 focus:bg-gray-800/80 transition-colors"
                placeholder="ws://localhost:8765/ws"
              />
            </div>
          </section>

          {/* ASR */}
          <section className="space-y-3">
            <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.12em]">ASR</h3>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="block text-xs text-gray-400">Provider</label>
                <select
                  value={settings.asrProvider}
                  onChange={(e) => setSettings(s => ({ ...s, asrProvider: e.target.value }))}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-xs text-white focus:outline-none focus:border-indigo-500/60 transition-colors"
                >
                  <option value="whisper">Whisper (local)</option>
                  <option value="azure">Azure Speech</option>
                  <option value="deepgram">Deepgram</option>
                  <option value="funasr">FunASR (local)</option>
                </select>
              </div>
              {settings.asrProvider !== 'whisper' && settings.asrProvider !== 'funasr' && (
                <div className="space-y-1.5">
                  <label className="block text-xs text-gray-400">API Key</label>
                  <input
                    type="password"
                    value={settings.asrApiKey}
                    onChange={(e) => setSettings(s => ({ ...s, asrApiKey: e.target.value }))}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-xs text-white font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500/60 transition-colors"
                    placeholder="sk-…"
                  />
                </div>
              )}
            </div>
          </section>

          {/* Agent */}
          <section className="space-y-3">
            <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.12em]">Agent</h3>
            <div className="space-y-1.5">
              <label className="block text-xs text-gray-400">Provider</label>
              <select
                value={settings.agentProvider}
                onChange={(e) => setSettings(s => ({ ...s, agentProvider: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-xs text-white focus:outline-none focus:border-indigo-500/60 transition-colors"
              >
                <option value="openclaw">OpenClaw (local)</option>
                <option value="openai">OpenAI</option>
                <option value="claude">Claude (Anthropic)</option>
                <option value="ollama">Ollama (local)</option>
              </select>
            </div>
          </section>

          {/* TTS */}
          <section className="space-y-3">
            <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.12em]">TTS</h3>
            <div className="space-y-1.5">
              <label className="block text-xs text-gray-400">Provider</label>
              <select
                value={settings.ttsProvider}
                onChange={(e) => setSettings(s => ({ ...s, ttsProvider: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-xs text-white focus:outline-none focus:border-indigo-500/60 transition-colors"
              >
                <option value="edge_tts">Edge TTS (free)</option>
                <option value="elevenlabs">ElevenLabs</option>
                <option value="openai">OpenAI TTS</option>
                <option value="cosyvoice">CosyVoice (local)</option>
              </select>
            </div>
          </section>

          {/* Note */}
          <div className="rounded-lg bg-amber-500/8 border border-amber-500/20 px-3.5 py-3">
            <p className="text-[11px] text-amber-400/70 leading-relaxed">
              Provider selections are saved locally for display only. Actual config lives in{' '}
              <code className="font-mono text-amber-300/80">config.yaml</code>. Restart the server after changes.
            </p>
          </div>
        </div>

        {/* Drawer footer */}
        <div className="px-5 py-4 border-t border-gray-800">
          <button
            onClick={handleSaveSettings}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition-colors"
          >
            Save Settings
          </button>
        </div>
      </aside>
    </div>
  );
}
