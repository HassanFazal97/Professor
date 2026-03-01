/**
 * Singleton audio queue for playing TTS responses in order.
 *
 * ElevenLabs streams raw PCM (pcm_22050: 22050 Hz, 16-bit signed LE, mono).
 * PCM chunks are decoded synchronously — no MP3 encoder priming silence,
 * no async decodeAudioData races. Each chunk is scheduled immediately after
 * the previous one using AudioContext wall-clock time.
 */

const PCM_SAMPLE_RATE = 22050;

class AudioPlayer {
  private _ctx: AudioContext | null = null;

  // All sources currently started (needed for instant stop/barge-in).
  private _activeSources = new Set<AudioBufferSourceNode>();

  // AudioContext wall-clock time at which the next chunk should start.
  private _nextStartTime = 0;

  private _playing = false;

  // Carry-over from an odd-length chunk — held until the next chunk arrives
  // so we never split a 16-bit sample across two enqueue() calls.
  private _carryByte: number | null = null;

  /** Called when the last queued chunk finishes playing naturally. */
  onDrained?: () => void;

  /** Call once inside a user-gesture handler to unlock the AudioContext. */
  resume(): void {
    const ctx = this._getCtx();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
  }

  enqueue(base64Audio: string): void {
    const binary = atob(base64Audio);

    // Prepend any carry-over byte from the previous odd-length chunk so that
    // 16-bit sample boundaries are always respected across chunk edges.
    let raw: Uint8Array;
    if (this._carryByte !== null) {
      raw = new Uint8Array(binary.length + 1);
      raw[0] = this._carryByte;
      for (let i = 0; i < binary.length; i++) raw[i + 1] = binary.charCodeAt(i);
      this._carryByte = null;
    } else {
      raw = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
    }

    // If the combined length is still odd, save the last byte for next time.
    if (raw.length % 2 !== 0) {
      this._carryByte = raw[raw.length - 1];
      raw = raw.slice(0, raw.length - 1);
    }

    const numSamples = raw.length / 2;
    if (numSamples === 0) return;

    const ctx = this._getCtx();

    if (!this._playing) {
      this._playing = true;
      // Small look-ahead so the first chunk has time to reach the scheduler.
      this._nextStartTime = ctx.currentTime + 0.06;
    }

    // Parse 16-bit signed little-endian PCM synchronously — no encoder silence.
    const audioBuffer = ctx.createBuffer(1, numSamples, PCM_SAMPLE_RATE);
    const channelData = audioBuffer.getChannelData(0);
    const view = new DataView(raw.buffer);
    for (let i = 0; i < numSamples; i++) {
      channelData[i] = view.getInt16(i * 2, true) / 32768;
    }

    // Never schedule in the past; +0.01 s absorbs any scheduling jitter.
    const startTime = Math.max(ctx.currentTime + 0.01, this._nextStartTime);
    this._nextStartTime = startTime + audioBuffer.duration;

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    this._activeSources.add(source);

    source.onended = () => {
      this._activeSources.delete(source);
      if (this._playing && this._activeSources.size === 0) {
        this._playing = false;
        this.onDrained?.();
      }
    };

    source.start(startTime);
  }

  /** Immediately cut all audio and clear the queue. Does not fire onDrained. */
  stop(): void {
    this._playing = false;
    this._nextStartTime = 0;
    this._carryByte = null;
    for (const source of this._activeSources) {
      try {
        source.stop();
      } catch {
        // already ended
      }
    }
    this._activeSources.clear();
  }

  private _getCtx(): AudioContext {
    if (!this._ctx) this._ctx = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
    return this._ctx;
  }
}

export const audioPlayer = new AudioPlayer();
