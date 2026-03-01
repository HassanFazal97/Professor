/**
 * Singleton audio queue for playing TTS responses in order.
 *
 * Uses the Web Audio API (AudioContext) instead of new Audio() so that
 * autoplay works reliably after a single user gesture. Call resume() once
 * during a click handler (e.g. "Start Session") to unlock the context; all
 * subsequent enqueue() calls will play without being blocked.
 */

class AudioPlayer {
  private _ctx: AudioContext | null = null;
  private _queue: ArrayBuffer[] = [];
  private _playing = false;
  private _currentSource: AudioBufferSourceNode | null = null;

  /** Called when the last queued chunk finishes playing naturally. */
  onDrained?: () => void;

  /** Call this inside a click handler to unlock the AudioContext. */
  resume(): void {
    const ctx = this._getCtx();
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
  }

  enqueue(base64Audio: string): void {
    // Decode base64 → ArrayBuffer
    const binary = atob(base64Audio);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    this._queue.push(bytes.buffer);
    if (!this._playing) this._playNext();
  }

  /** Immediately cut all audio and clear the queue. Does not fire onDrained. */
  stop(): void {
    this._queue = [];
    this._playing = false;
    if (this._currentSource) {
      try {
        this._currentSource.stop();
      } catch {
        // source may have already ended
      }
      this._currentSource = null;
    }
  }

  private _getCtx(): AudioContext {
    if (!this._ctx) {
      this._ctx = new AudioContext();
    }
    return this._ctx;
  }

  private _playNext(): void {
    if (this._queue.length === 0) {
      this._playing = false;
      this._currentSource = null;
      this.onDrained?.();
      return;
    }

    this._playing = true;
    const buffer = this._queue.shift()!;
    const ctx = this._getCtx();

    // Resume in case the context got suspended between calls
    const doPlay = () => {
      ctx.decodeAudioData(
        buffer,
        (audioBuffer) => {
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(ctx.destination);
          this._currentSource = source;
          source.onended = () => this._playNext();
          source.start(0);
        },
        (err) => {
          console.error("Audio decode error:", err);
          this._playNext();
        },
      );
    };

    if (ctx.state === "suspended") {
      ctx.resume().then(doPlay).catch(() => {
        console.warn("AudioContext resume blocked — no audio");
        this._playNext();
      });
    } else {
      doPlay();
    }
  }
}

export const audioPlayer = new AudioPlayer();
