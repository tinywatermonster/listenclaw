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
  private ctx: AudioContext | null = null;
  private queue: AudioBuffer[] = [];
  private playing = false;
  private nextStart = 0;
  private onPlayStateChange?: (playing: boolean) => void;

  constructor(onPlayStateChange?: (playing: boolean) => void) {
    this.onPlayStateChange = onPlayStateChange;
  }

  private getCtx(): AudioContext {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new AudioContext();
    }
    return this.ctx;
  }

  /** Call during a user gesture so the AudioContext isn't blocked by autoplay policy. */
  resume() {
    const ctx = this.getCtx();
    if (ctx.state === 'suspended') ctx.resume();
  }

  async enqueue(mp3Bytes: ArrayBuffer) {
    const ctx = this.getCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    try {
      const buffer = await ctx.decodeAudioData(mp3Bytes);
      this.queue.push(buffer);
      if (!this.playing) this._playNext();
    } catch (e) {
      console.error('Audio decode error:', e);
    }
  }

  private _playNext() {
    if (this.queue.length === 0) {
      this.playing = false;
      this.onPlayStateChange?.(false);
      return;
    }
    const ctx = this.getCtx();
    this.playing = true;
    this.onPlayStateChange?.(true);
    const buffer = this.queue.shift()!;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const now = ctx.currentTime;
    const start = Math.max(now, this.nextStart);
    source.start(start);
    this.nextStart = start + buffer.duration;
    source.onended = () => this._playNext();
  }

  stop() {
    this.queue = [];
    this.playing = false;
    this.nextStart = 0;
    this.ctx?.close();
    this.ctx = null;
    this.onPlayStateChange?.(false);
  }
}
