"use client";

import { useEffect, useState } from "react";
import { useTutorSession } from "@/hooks/useTutorSession";
import { useVoicePipeline } from "@/hooks/useVoicePipeline";
import { audioPlayer } from "@/lib/audioPlayer";

const SUBJECTS = [
  "Mathematics",
  "Physics",
  "Chemistry",
  "Biology",
  "Computer Science",
  "History",
  "English",
];

export default function SessionControls() {
  const [selectedSubject, setSelectedSubject] = useState(SUBJECTS[0]);
  const { isConnected, sessionId, startSession, endSession, adaSpeaking, setAdaSpeaking } =
    useTutorSession();
  const { startListening, stopListening, isListening } = useVoicePipeline();

  // Auto-start mic the moment the session connects
  useEffect(() => {
    if (isConnected) startListening();
  }, [isConnected]); // eslint-disable-line react-hooks/exhaustive-deps

  // When Ada's audio finishes, clear the speaking flag (mic stays on the whole time)
  useEffect(() => {
    audioPlayer.onDrained = () => {
      setAdaSpeaking(false);
    };
    return () => {
      audioPlayer.onDrained = undefined;
    };
  }, [setAdaSpeaking]);

  const handleStart = () => {
    startSession(selectedSubject);
  };

  const handleEnd = () => {
    stopListening();
    endSession();
  };

  const toggleMute = () => {
    isListening ? stopListening() : startListening();
  };

  return (
    <div className="space-y-3">
      {!isConnected ? (
        <>
          <select
            value={selectedSubject}
            onChange={(e) => setSelectedSubject(e.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
          >
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            onClick={handleStart}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 active:scale-95 transition-transform"
          >
            Start Session
          </button>
        </>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>{selectedSubject}</span>
            <span className="font-mono">{sessionId?.slice(0, 8)}…</span>
          </div>

          {/* Mic status / mute toggle */}
          <button
            onClick={toggleMute}
            disabled={adaSpeaking}
            title={adaSpeaking ? "Ada is speaking…" : isListening ? "Mute mic" : "Unmute mic"}
            className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all active:scale-95 disabled:cursor-not-allowed ${
              adaSpeaking
                ? "border border-blue-200 bg-blue-50 text-blue-400"
                : isListening
                  ? "bg-red-500 text-white hover:bg-red-600"
                  : "border border-gray-300 bg-white text-gray-500 hover:bg-gray-50"
            }`}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z"
                clipRule="evenodd"
              />
            </svg>
            {adaSpeaking ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-400" />
                Ada is speaking…
              </span>
            ) : isListening ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-white" />
                Listening — tap to mute
              </span>
            ) : (
              "Tap to unmute"
            )}
          </button>

          <button
            onClick={handleEnd}
            className="w-full rounded-md bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 active:scale-95 transition-transform"
          >
            End Session
          </button>
        </div>
      )}
    </div>
  );
}
