export type PipelineState = 'idle' | 'wake' | 'listening' | 'processing' | 'speaking' | 'follow_up' | 'disconnected';

export type WsEvent =
  | { type: 'state'; state: PipelineState }
  | { type: 'asr_result'; text: string }
  | { type: 'agent_chunk'; text: string }
  | { type: 'agent_done'; text: string }
  | { type: 'tts_chunk'; data: string }
  | { type: 'tts_segment_done' }
  | { type: 'tts_done' }
  | { type: 'error'; message: string }
  | { type: 'connected' }
  | { type: 'disconnected' };

export class WsClient {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners: ((e: WsEvent) => void)[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(url: string) {
    this.url = url;
  }

  connect() {
    this.closed = false;
    this._connect();
  }

  private _connect() {
    if (this.closed) return;
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => this._emit({ type: 'connected' });
    this.ws.onclose = () => {
      this._emit({ type: 'disconnected' });
      if (!this.closed) {
        this.reconnectTimer = setTimeout(() => this._connect(), 3000);
      }
    };
    this.ws.onerror = () => this.ws?.close();
    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        this._emit(msg as WsEvent);
      } catch {
        // ignore malformed messages
      }
    };
  }

  sendAudio(pcm: ArrayBuffer) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const bytes = new Uint8Array(pcm);
    // Use chunked base64 conversion to avoid call stack overflow on large buffers
    let b64 = '';
    const chunkSize = 8192;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      b64 += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    b64 = btoa(b64);
    this.ws.send(JSON.stringify({ type: 'audio', data: b64 }));
  }

  sendInterrupt() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'interrupt' }));
    }
  }

  sendPing() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }

  on(fn: (e: WsEvent) => void) {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter(l => l !== fn);
    };
  }

  private _emit(e: WsEvent) {
    this.listeners.forEach(l => l(e));
  }

  disconnect() {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}
