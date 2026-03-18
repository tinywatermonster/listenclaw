// MicCapture: getUserMedia → AudioWorklet → resample to 16kHz → int16 → callback
// AudioPlayer: queue MP3 blobs → AudioContext.decodeAudioData → BufferSourceNode serial playback
//   resume() MUST be called inside a user gesture (PTT press) to unlock iOS AudioContext.

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
  private queue: ArrayBuffer[] = [];
  private playing = false;
  private currentSource: AudioBufferSourceNode | null = null;
  private onPlayStateChange?: (playing: boolean) => void;

  constructor(onPlayStateChange?: (playing: boolean) => void) {
    this.onPlayStateChange = onPlayStateChange;
  }

  /**
   * Call during a user gesture (PTT press) to unlock AudioContext on iOS.
   * Creates the context if needed and resumes it.
   */
  resume() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  async enqueue(mp3Bytes: ArrayBuffer) {
    this.queue.push(mp3Bytes);
    if (!this.playing) this._playNext();
  }

  private async _playNext() {
    if (this.queue.length === 0) {
      this.playing = false;
      this.currentSource = null;
      this.onPlayStateChange?.(false);
      return;
    }
    this.playing = true;
    this.onPlayStateChange?.(true);

    const bytes = this.queue.shift()!;

    // Lazily create context if resume() wasn't called (non-iOS path)
    if (!this.ctx) {
      this.ctx = new AudioContext();
    }
    // Ensure context is running
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume();
    }

    try {
      const decoded = await this.ctx.decodeAudioData(bytes);
      const source = this.ctx.createBufferSource();
      source.buffer = decoded;
      source.connect(this.ctx.destination);
      this.currentSource = source;
      source.onended = () => this._playNext();
      source.start();
    } catch (e) {
      console.error('AudioPlayer decode error:', e);
      this._playNext();
    }
  }

  stop() {
    this.queue = [];
    this.playing = false;
    this.currentSource?.stop();
    this.currentSource = null;
    this.onPlayStateChange?.(false);
  }

  dispose() {
    this.stop();
    this.ctx?.close();
    this.ctx = null;
  }
}
