"use client";

import { useEffect } from "react";
import { useVoicePipeline } from "@/hooks/useVoicePipeline";

/**
 * Hidden component that manages microphone input and speaker output.
 * Lives outside the visible UI so audio capture runs independently.
 */
export default function AudioManager() {
  const { startListening, stopListening, isListening } = useVoicePipeline();

  useEffect(() => {
    // Cleanup on unmount
    return () => {
      stopListening();
    };
  }, [stopListening]);

  // This component renders nothing visible
  return null;
}
