"use client";

import { useEffect, useRef } from "react";
import { useTutorSession } from "@/hooks/useTutorSession";


export default function TutorPanel() {
  const { tutorMode, conversationHistory, isConnected, adaSpeaking, waitForStudent } = useTutorSession();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversationHistory]);

  const status = !isConnected
    ? "disconnected"
    : adaSpeaking
      ? "speaking"
      : tutorMode === "listening"
        ? "listening"
        : tutorMode;

  const statusColor = {
    disconnected: "bg-kia-warm",
    listening: "bg-kia-lime animate-pulse",
    speaking: "bg-kia-blue animate-pulse",
    guiding: "bg-kia-blue animate-pulse",
    demonstrating: "bg-kia-blue animate-pulse",
    evaluating: "bg-kia-blue animate-pulse",
  }[status] ?? "bg-kia-warm";

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
      {/* Header — logo + name + status */}
      <div className="mb-5 flex items-center gap-3">
        <div className="h-11 w-11 flex-shrink-0 overflow-hidden rounded-full bg-black">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/kia-avatar.png" alt="Professor KIA" className="h-full w-full object-cover" />
        </div>
        <div className="min-w-0">
          <h1 className="text-sm font-bold text-kia-black font-heading leading-tight tracking-wide uppercase">
            Professor KIA
          </h1>
          <p className="text-[11px] text-kia-gray font-mono tracking-wide uppercase">
            Know It All
          </p>
        </div>
        <div className="ml-auto flex flex-col items-end gap-1">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${statusColor}`} />
          <span className="text-[9px] font-mono text-kia-gray uppercase tracking-wider">{statusLabel}</span>
        </div>
      </div>

      {/* Speaking / listening indicator bar */}
      <div className="mb-4 flex h-11 items-center justify-center rounded-xl bg-kia-warm px-3">
        {adaSpeaking ? (
          <div className="flex items-center gap-1.5">
            {[0, 1, 2, 3, 4].map((i) => (
              <span
                key={i}
                className="inline-block w-1 rounded-full bg-kia-blue"
                style={{
                  height: `${10 + Math.sin(i * 1.2) * 7}px`,
                  animation: `pulse ${0.45 + i * 0.1}s ease-in-out infinite alternate`,
                }}
              />
            ))}
            <span className="ml-2 text-[11px] font-mono text-kia-blue uppercase tracking-wide">
              KIA is speaking
            </span>
          </div>
        ) : waitForStudent ? (
          <span className="text-[11px] font-mono font-bold text-kia-black animate-pulse uppercase tracking-wide">
            ✏️ Your turn — show your work
          </span>
        ) : (
          <span className="text-[11px] font-mono text-kia-gray uppercase tracking-wide">
            {isConnected ? "Hold Space or button to talk" : "Start a session to begin"}
          </span>
        )}
      </div>

      {/* Conversation transcript */}
      <div className="flex-1 space-y-2.5 overflow-y-auto text-sm">
        {conversationHistory.length === 0 ? (
          <p className="mt-4 text-center text-[11px] font-mono text-kia-gray uppercase tracking-wide">
            Say hello to Professor KIA to get started.
          </p>
        ) : (
          conversationHistory
            .filter((turn) => turn.content !== "[checking my work on the board]")
            .map((turn, i) => (
              <div
                key={i}
                className={`rounded-xl px-3 py-2.5 ${
                  turn.role === "assistant"
                    ? "bg-kia-blue/10 text-kia-black border border-kia-blue/20"
                    : "bg-kia-warm text-kia-black"
                }`}
              >
                <span
                  className={`mb-0.5 block text-[9px] font-mono font-bold uppercase tracking-widest ${
                    turn.role === "assistant" ? "text-kia-blue" : "text-kia-gray"
                  }`}
                >
                  {turn.role === "assistant" ? "KIA" : "You"}
                </span>
                <span className="text-[13px] leading-snug">{turn.content}</span>
              </div>
            ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
