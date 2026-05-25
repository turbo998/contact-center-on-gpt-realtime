/**
 * Browser microphone capture → 24 kHz PCM16 / 20ms frames.
 * Spec: docs/14-frontend-design.md §14.4.
 *
 * The actual DSP runs in the AudioWorklet (public/worklets/recorder-worklet.js).
 * This module is the main-thread glue. Unit-tested via export smoke only —
 * end-to-end audio capture is verified in E2E (#18).
 */

export interface RecorderOpts {
  /** Called for each 20ms PCM16 frame (ArrayBuffer of 960 bytes). */
  onFrame: (pcm16: ArrayBuffer) => void;
  /** Worklet module URL. Defaults to '/worklets/recorder-worklet.js'. */
  workletUrl?: string;
  /** AudioContext sample rate hint (browser may override). */
  sampleRate?: number;
}

export interface RecorderHandle {
  stop: () => Promise<void>;
  readonly contextSampleRate: number;
}

export async function startRecorder(opts: RecorderOpts): Promise<RecorderHandle> {
  if (typeof window === "undefined" || !navigator?.mediaDevices) {
    throw new Error("Recorder requires a browser with mediaDevices");
  }
  const url = opts.workletUrl ?? "/worklets/recorder-worklet.js";
  const ctx = new AudioContext({ sampleRate: opts.sampleRate ?? 48000 });
  await ctx.audioWorklet.addModule(url);

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const src = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "recorder-processor");
  node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
    opts.onFrame(e.data);
  };
  src.connect(node);

  let stopped = false;
  return {
    contextSampleRate: ctx.sampleRate,
    stop: async () => {
      if (stopped) return;
      stopped = true;
      try {
        node.port.onmessage = null;
        node.disconnect();
        src.disconnect();
        stream.getTracks().forEach((t) => t.stop());
      } finally {
        await ctx.close();
      }
    },
  };
}
