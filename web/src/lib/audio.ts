// MicCapture: getUserMedia → AudioWorklet → resample to 16kHz → int16 → callback
// AudioPlayer: queue MP3 blobs → decodeAudioData → AudioBufferSourceNode serial playback

export class MicCapture {
  private ctx: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private stream: MediaStream | null = null;
  private onChunk: (pcm: ArrayBuffer) => void;
  private targetRate = 16000;

  constructor(onChunk: (pcm: ArrayBuffer) => void) {
    this.onChunk = onChunk;
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    this.ctx = new AudioContext();
    await this.ctx.audioWorklet.addModule('/audio-processor.js');
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(this.ctx, 'pcm-processor');
    this.worklet.port.onmessage = (e: MessageEvent<Float32Array>) => {
      const float32 = e.data;
      const nativeRate = this.ctx!.sampleRate;
      const resampled = this._resample(float32, nativeRate, this.targetRate);
      const int16 = new Int16Array(resampled.length);
      for (let i = 0; i < resampled.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.round(resampled[i] * 32767)));
      }
      this.onChunk(int16.buffer);
    };
    this.source.connect(this.worklet);
    this.worklet.connect(this.ctx.destination);
  }

  stop() {
    this.worklet?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach(t => t.stop());
    this.ctx?.close();
    this.ctx = null;
  }

  private _resample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
    if (fromRate === toRate) return input;
    const ratio = fromRate / toRate;
    const outputLen = Math.round(input.length / ratio);
    const output = new Float32Array(outputLen);
    for (let i = 0; i < outputLen; i++) {
      const src = i * ratio;
      const idx = Math.floor(src);
      const frac = src - idx;
      output[i] = idx + 1 < input.length
        ? input[idx] * (1 - frac) + input[idx + 1] * frac
        : input[idx];
    }
    return output;
  }
}

export class AudioPlayer {
  private queue: string[] = []; // object URLs of MP3 blobs
  private playing = false;
  private current: HTMLAudioElement | null = null;
  private onPlayStateChange?: (playing: boolean) => void;

  constructor(onPlayStateChange?: (playing: boolean) => void) {
    this.onPlayStateChange = onPlayStateChange;
  }

  /** No-op — HTML5 Audio doesn't need AudioContext gesture unlock. */
  resume() {}

  async enqueue(mp3Bytes: ArrayBuffer) {
    const blob = new Blob([mp3Bytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    this.queue.push(url);
    if (!this.playing) this._playNext();
  }

  private _playNext() {
    if (this.queue.length === 0) {
      this.playing = false;
      this.onPlayStateChange?.(false);
      return;
    }
    this.playing = true;
    this.onPlayStateChange?.(true);
    const url = this.queue.shift()!;
    const audio = new Audio(url);
    this.current = audio;
    const cleanup = () => { URL.revokeObjectURL(url); this._playNext(); };
    audio.onended = cleanup;
    audio.onerror = cleanup;
    audio.play().catch(cleanup);
  }

  stop() {
    const urls = this.queue.splice(0);
    urls.forEach(u => URL.revokeObjectURL(u));
    this.playing = false;
    if (this.current) { this.current.pause(); this.current = null; }
    this.onPlayStateChange?.(false);
  }

  dispose() { this.stop(); }
}
