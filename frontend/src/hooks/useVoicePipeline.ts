"use client";

import { useCallback, useRef, useState } from "react";
import { useTutorSession } from "./useTutorSession";

// Preferred mime type — webm/opus is supported in Chrome, Firefox, and Edge.
// The backend tells Deepgram to expect encoding=opus&container=webm.
const PREFERRED_MIME = "audio/webm;codecs=opus";
const FALLBACK_MIME = "audio/webm";
const CHUNK_INTERVAL_MS = 250;

function getSupportedMimeType(): string {
  if (MediaRecorder.isTypeSupported(PREFERRED_MIME)) return PREFERRED_MIME;
  if (MediaRecorder.isTypeSupported(FALLBACK_MIME)) return FALLBACK_MIME;
  return ""; // let the browser choose
}

export function useVoicePipeline() {
  const [isListening, setIsListening] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const { send, isConnected } = useTutorSession();

  const startListening = useCallback(async () => {
    if (isListening || !isConnected) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,  // removes Ada's voice from the mic signal
          noiseSuppression: true,  // reduces background noise
          autoGainControl: true,   // normalises volume
        },
      });
      streamRef.current = stream;

      const mimeType = getSupportedMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      recorder.ondataavailable = async (e) => {
        if (e.data.size === 0) return;

        // Drop the chunk while Ada is speaking. Browser echo cancellation isn't
        // guaranteed to cover AudioContext playback, so we gate at the source:
        // nothing reaches Deepgram while Ada's audio is playing.
        if (useTutorSession.getState().adaSpeaking) return;

        // Convert Blob → ArrayBuffer → base64 and send to backend
        const buffer = await e.data.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        send({ type: "audio_data", data: btoa(binary) });
      };

      // Tell the backend to open a Deepgram connection
      send({ type: "audio_start" });

      recorder.start(CHUNK_INTERVAL_MS);
      recorderRef.current = recorder;
      setIsListening(true);
    } catch (err) {
      console.error("Microphone access denied:", err);
    }
  }, [isListening, isConnected, send]);

  const stopListening = useCallback(() => {
    if (!isListening) return;

    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
    streamRef.current = null;

    send({ type: "audio_stop" });
    setIsListening(false);
  }, [isListening, send]);

  return { isListening, startListening, stopListening };
}
