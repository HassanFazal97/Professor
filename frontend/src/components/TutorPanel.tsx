"use client";

import { useEffect, useRef } from "react";
import { useTutorSession } from "@/hooks/useTutorSession";

export default function TutorPanel() {
  const { tutorMode, conversationHistory, isConnected, adaSpeaking } = useTutorSession();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversationHistory]);

  // Derive a human-readable status
  const status = !isConnected
    ? "disconnected"
    : adaSpeaking
      ? "speaking"
      : tutorMode === "listening"
        ? "listening"
        : tutorMode;

  const statusColor = {
    disconnected: "bg-gray-300",
    listening: "bg-green-500 animate-pulse",
    speaking: "bg-blue-500 animate-pulse",
    guiding: "bg-yellow-400 animate-pulse",
    demonstrating: "bg-purple-500 animate-pulse",
    evaluating: "bg-orange-400 animate-pulse",
  }[status] ?? "bg-gray-300";

  const statusLabel = {
    disconnected: "Disconnected",
    listening: "Listening…",
    speaking: "Speaking…",
    guiding: "Thinking…",
    demonstrating: "Demonstrating…",
    evaluating: "Evaluating…",
  }[status] ?? status;

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4">
      {/* Avatar / header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-600 text-lg font-bold text-white">
          A
        </div>
        <div>
          <h1 className="text-sm font-semibold text-gray-900">Professor Ada</h1>
          <p className="text-xs text-gray-500">{statusLabel}</p>
        </div>
        <div className="ml-auto">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${statusColor}`} />
        </div>
      </div>

      {/* Speaking / listening indicator bar */}
      <div className="mb-4 flex h-10 items-center justify-center rounded-lg bg-gray-100">
        {adaSpeaking ? (
          <div className="flex items-center gap-1">
            {[0, 1, 2, 3, 4].map((i) => (
              <span
                key={i}
                className="inline-block w-1 rounded-full bg-blue-500"
                style={{
                  height: `${12 + Math.sin(i * 1.2) * 8}px`,
                  animation: `pulse ${0.5 + i * 0.1}s ease-in-out infinite alternate`,
                }}
              />
            ))}
            <span className="ml-2 text-xs text-blue-500">Ada is speaking</span>
          </div>
        ) : (
          <span className="text-xs text-gray-400">
            {isConnected ? "Your mic is live — just talk" : "Start a session to begin"}
          </span>
        )}
      </div>

      {/* Conversation transcript */}
      <div className="flex-1 space-y-3 overflow-y-auto text-sm">
        {conversationHistory.length === 0 ? (
          <p className="text-center text-xs text-gray-400">
            Say hello to Professor Ada to get started.
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
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
