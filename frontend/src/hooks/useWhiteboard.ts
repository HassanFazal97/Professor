import { create } from "zustand";
import type { StrokeData } from "@/types";
import { useTutorSession } from "./useTutorSession";

interface WhiteboardState {
  pendingStrokes: StrokeData | null;

  // Called by Whiteboard.tsx when a snapshot is ready
  onSnapshotReady: (imageBase64: string) => void;

  // Called by WhiteboardOverlay after animation completes
  clearPendingStrokes: () => void;

  // Called by the WebSocket handler when strokes arrive from the server
  setIncomingStrokes: (strokes: StrokeData) => void;
}

export const useWhiteboard = create<WhiteboardState>((set) => ({
  pendingStrokes: null,

  onSnapshotReady: (imageBase64: string) => {
    // Send snapshot to backend via the session WebSocket
    const { send } = useTutorSession.getState();
    send({ type: "board_snapshot", image_base64: imageBase64 });
  },

  clearPendingStrokes: () => set({ pendingStrokes: null }),

  setIncomingStrokes: (strokes: StrokeData) => set({ pendingStrokes: strokes }),
}));
