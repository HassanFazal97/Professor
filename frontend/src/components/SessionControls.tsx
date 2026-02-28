"use client";

import { useState } from "react";
import { useTutorSession } from "@/hooks/useTutorSession";
import { useVoicePipeline } from "@/hooks/useVoicePipeline";

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
  const { isConnected, sessionId, startSession, endSession } = useTutorSession();
  const { startListening, stopListening, isListening } = useVoicePipeline();

  const handleStart = () => {
    startSession(selectedSubject);
    startListening();
  };

  const handleEnd = () => {
    stopListening();
    endSession();
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
            <span>Subject: {selectedSubject}</span>
            <span className="font-mono">{sessionId?.slice(0, 8)}…</span>
          </div>
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
