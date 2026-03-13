class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._bufferSize = 4800; // 300ms at 16kHz
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      const samples = input[0];
      for (let i = 0; i < samples.length; i++) {
        this._buffer.push(samples[i]);
      }
      if (this._buffer.length >= this._bufferSize) {
        this.port.postMessage(new Float32Array(this._buffer.splice(0, this._bufferSize)));
      }
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
