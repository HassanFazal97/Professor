"use client";

import { useTutorSession } from "@/hooks/useTutorSession";

export default function TutorPanel() {
  const { tutorMode, conversationHistory, isConnected } = useTutorSession();

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4">
      {/* Avatar / header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-600 text-lg font-bold text-white">
          A
        </div>
        <div>
          <h1 className="text-sm font-semibold text-gray-900">Professor Ada</h1>
          <p className="text-xs text-gray-500 capitalize">
            {isConnected ? tutorMode : "Disconnected"}
          </p>
        </div>
        {/* Live indicator */}
        <div className="ml-auto">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              isConnected ? "animate-pulse bg-green-500" : "bg-gray-300"
            }`}
          />
        </div>
      </div>

      {/* Waveform placeholder */}
      <div className="mb-4 flex h-12 items-center justify-center rounded-lg bg-gray-100">
        <span className="text-xs text-gray-400">
          {tutorMode === "listening" ? "Listening..." : "Speaking..."}
        </span>
      </div>

      {/* Conversation transcript */}
      <div className="flex-1 space-y-3 overflow-y-auto text-sm">
        {conversationHistory.length === 0 ? (
          <p className="text-center text-xs text-gray-400">
            Start a session to begin talking with Professor Ada.
          </p>
        ) : (
          conversationHistory.map((turn, i) => (
            <div
              key={i}
              className={`rounded-lg px-3 py-2 ${
                turn.role === "assistant"
                  ? "bg-blue-50 text-blue-900"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide opacity-60">
                {turn.role === "assistant" ? "Ada" : "You"}
              </span>
              {turn.content}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
