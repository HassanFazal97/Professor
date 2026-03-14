"use client";

import { useCallback, useEffect, useRef } from "react";
import { useTutorSession } from "@/hooks/useTutorSession";
import { useVoicePipeline } from "@/hooks/useVoicePipeline";
import { audioPlayer } from "@/lib/audioPlayer";

export default function SessionControls() {
  const spaceHeldRef = useRef(false);
  const { isConnected, sessionId, startSession, endSession, adaSpeaking, setAdaSpeaking } =
    useTutorSession();
  const { startListening, stopListening, isListening } = useVoicePipeline();

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
    startSession();
  };

  const handleEnd = () => {
    stopListening();
    endSession();
  };

  const beginPushToTalk = useCallback(() => {
    if (!isConnected || isListening) return;
    if (adaSpeaking) {
      // Interrupt Ada first, then start capturing mic.
      useTutorSession.getState().send({ type: "barge_in" });
    }
    startListening();
  }, [isConnected, isListening, adaSpeaking, startListening]);

  const endPushToTalk = useCallback(() => {
    if (!isListening) return;
    stopListening();
  }, [isListening, stopListening]);

  useEffect(() => {
    if (!isConnected) return;

    const isEditableTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName.toLowerCase();
      if (target.isContentEditable) return true;
      return tag === "input" || tag === "textarea" || tag === "select";
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      if (e.repeat || spaceHeldRef.current) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;
      e.preventDefault();
      spaceHeldRef.current = true;
      beginPushToTalk();
    };

    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      if (!spaceHeldRef.current) return;
      e.preventDefault();
      spaceHeldRef.current = false;
      endPushToTalk();
    };

    const onBlur = () => {
      if (!spaceHeldRef.current) return;
      spaceHeldRef.current = false;
      endPushToTalk();
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, [isConnected, beginPushToTalk, endPushToTalk]);

  return (
    <div className="space-y-3">
      {!isConnected ? (
        <>
          <button
            onClick={handleStart}
            className="w-full rounded-xl bg-kia-blue px-4 py-2.5 text-sm font-bold font-heading text-white hover:bg-[#003a8a] active:scale-95 transition-transform uppercase tracking-wide"
          >
            Start Session
          </button>
        </>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[10px] font-mono text-kia-gray uppercase tracking-wide">
            <span>Conversation</span>
            <span className="font-mono">{sessionId?.slice(0, 8)}…</span>
          </div>

          {/* Push-to-talk */}
          <button
            onPointerDown={beginPushToTalk}
            onPointerUp={endPushToTalk}
            onPointerCancel={endPushToTalk}
            onPointerLeave={endPushToTalk}
            title={
              adaSpeaking
                ? "Interrupt KIA and speak"
                : "Hold to talk"
            }
            className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold font-heading uppercase tracking-wide transition-all ${
              adaSpeaking
                ? "border border-kia-blue/30 bg-kia-blue/10 text-kia-blue"
                : isListening
                  ? "bg-kia-blue text-white"
                  : "border border-kia-warm bg-white text-kia-gray hover:bg-kia-cream"
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
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-kia-blue" />
                Hold to interrupt + talk
              </span>
            ) : isListening ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-white" />
                Listening... release to send
              </span>
            ) : (
              "Hold Space (or hold button) to talk"
            )}
          </button>

          <button
            onClick={handleEnd}
            className="w-full rounded-xl bg-kia-black px-4 py-2 text-sm font-bold font-heading text-white hover:bg-kia-gray active:scale-95 transition-transform uppercase tracking-wide"
          >
            End Session
          </button>
        </div>
      )}
    </div>
  );
}
