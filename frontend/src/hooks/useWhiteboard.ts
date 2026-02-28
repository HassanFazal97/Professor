import { create } from "zustand";
import type { BoardAction, StrokeData } from "@/types";
import { useTutorSession } from "./useTutorSession";

interface WhiteboardState {
  pendingStrokes: StrokeData | null;
  strokeQueue: StrokeData[];
  pendingBoardActions: BoardAction[];

  // Called by Whiteboard.tsx when a snapshot is ready
  onSnapshotReady: (imageBase64: string) => void;

  // Called by WhiteboardOverlay after animation completes — advances the queue
  clearPendingStrokes: () => void;

  // Called by the WebSocket handler when strokes arrive from the server
  setIncomingStrokes: (strokes: StrokeData) => void;

  // Called by useTutorSession when a board_action message arrives
  addBoardAction: (action: BoardAction) => void;

  // Called by Whiteboard.tsx after it processes the queue
  clearBoardActions: () => void;
}

export const useWhiteboard = create<WhiteboardState>((set, get) => ({
  pendingStrokes: null,
  strokeQueue: [],
  pendingBoardActions: [],

  onSnapshotReady: (imageBase64: string) => {
    const { send } = useTutorSession.getState();
    send({ type: "board_snapshot", image_base64: imageBase64 });
  },

  // When the current animation finishes, dequeue the next stroke batch.
  clearPendingStrokes: () =>
    set((state) => {
      const [next, ...rest] = state.strokeQueue;
      return { pendingStrokes: next ?? null, strokeQueue: rest };
    }),

  // If nothing is animating right now, start immediately; otherwise enqueue.
  setIncomingStrokes: (strokes: StrokeData) =>
    set((state) => {
      if (state.pendingStrokes === null) {
        return { pendingStrokes: strokes };
      }
      return { strokeQueue: [...state.strokeQueue, strokes] };
    }),

  addBoardAction: (action: BoardAction) =>
    set((state) => ({ pendingBoardActions: [...state.pendingBoardActions, action] })),

  clearBoardActions: () => set({ pendingBoardActions: [] }),
}));
