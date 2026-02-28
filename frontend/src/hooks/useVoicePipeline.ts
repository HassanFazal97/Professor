"use client";

import { useCallback, useRef, useState } from "react";
import { useTutorSession } from "./useTutorSession";

/**
 * Manages microphone capture and Deepgram STT integration.
 *
 * Current implementation: captures mic audio via MediaRecorder and
 * sends final transcripts to the backend WebSocket.
 *
 * TODO: pipe raw audio bytes to the backend for real-time Deepgram proxying
 * instead of using browser-level MediaRecorder chunks.
 */
export function useVoicePipeline() {
  const [isListening, setIsListening] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const { send, isConnected } = useTutorSession();

  const startListening = useCallback(async () => {
    if (isListening || !isConnected) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // TODO: replace with raw PCM streaming to backend for Deepgram proxy
      // For now use SpeechRecognition (Web Speech API) as a development stub
      if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
        const SpeechRecognition =
          (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = "en-US";

        recognition.onresult = (event: any) => {
          const transcript = event.results[event.results.length - 1][0].transcript.trim();
          if (transcript) {
            send({ type: "transcript", text: transcript });
          }
        };

        recognition.start();
        (streamRef as any).recognition = recognition;
      }

      setIsListening(true);
    } catch (err) {
      console.error("Microphone access denied:", err);
    }
  }, [isListening, isConnected, send]);

  const stopListening = useCallback(() => {
    if (!isListening) return;

    const recognition = (streamRef as any).recognition;
    recognition?.stop();

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;

    setIsListening(false);
  }, [isListening]);

  return { isListening, startListening, stopListening };
}
