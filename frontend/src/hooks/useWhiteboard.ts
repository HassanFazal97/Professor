import { create } from "zustand";
import type { Editor } from "@tldraw/tldraw";
import type { BoardAction, StrokeData } from "@/types";
import { useTutorSession } from "./useTutorSession";

interface WhiteboardState {
  pendingStrokes: StrokeData | null;
  strokeQueue: StrokeData[];
  pendingBoardActions: BoardAction[];
  editor: Editor | null;
  overlayResetVersion: number;

  // The overlay canvas element — registered by WhiteboardOverlay on mount,
  // read by Whiteboard.tsx when compositing snapshots.
  overlayCanvas: HTMLCanvasElement | null;

  // Called by Whiteboard.tsx when a snapshot is ready
  onSnapshotReady: (imageBase64: string, width: number, height: number, studentMaxY?: number) => void;

  // Called by WhiteboardOverlay after animation completes — advances the queue
  clearPendingStrokes: () => void;

  // Called by the WebSocket handler when strokes arrive from the server
  setIncomingStrokes: (strokes: StrokeData) => void;

  // Called by useTutorSession when a board_action message arrives
  addBoardAction: (action: BoardAction) => void;

  // Called by Whiteboard.tsx after it processes the queue
  clearBoardActions: () => void;

  // Called by WhiteboardOverlay to register/unregister its canvas
  setOverlayCanvas: (canvas: HTMLCanvasElement | null) => void;
  setEditor: (editor: Editor | null) => void;

  // Called on barge-in to stop the current animation and clear the queue
  cancelStrokes: () => void;

  // Called when a "clear" board action is received — wipes Ada's overlay canvas
  clearOverlay: () => void;

  // Called when a "scroll_board" message arrives — pans the tldraw camera down
  scrollBoard: (scrollBy: number) => void;
}

export const useWhiteboard = create<WhiteboardState>((set, get) => ({
  pendingStrokes: null,
  strokeQueue: [],
  pendingBoardActions: [],
  editor: null,
  overlayResetVersion: 0,
  overlayCanvas: null,

  onSnapshotReady: (imageBase64: string, width: number, height: number, studentMaxY?: number) => {
    const { send } = useTutorSession.getState();
    send({
      type: "board_snapshot",
      image_base64: imageBase64,
      width,
      height,
      ...(studentMaxY !== undefined ? { student_max_y: studentMaxY } : {}),
    });
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

  setOverlayCanvas: (canvas) => set({ overlayCanvas: canvas }),
  setEditor: (editor) => set({ editor }),

  // Clear pending strokes and the queue — WhiteboardOverlay's cancelRef handles the RAF loop
  cancelStrokes: () => set({ pendingStrokes: null, strokeQueue: [] }),

  // Wipe Ada's handwriting off the overlay canvas (called on board "clear" action)
  clearOverlay: () => {
    const canvas = get().overlayCanvas;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx?.clearRect(0, 0, canvas.width, canvas.height);
    }
    set((state) => ({ overlayResetVersion: state.overlayResetVersion + 1 }));
  },

  // Pan the tldraw camera down by scrollBy pixels to reveal fresh blank space.
  // Temporarily unlocks the camera for the programmatic move, then re-locks.
  scrollBoard: (scrollBy: number) => {
    const { editor } = get();
    if (!editor) return;
    editor.setCameraOptions({ isLocked: false });
    const cam = editor.getCamera();
    // Negative y shift moves the viewport DOWN in world space (reveals higher world-y values).
    editor.setCamera({ x: cam.x, y: cam.y - scrollBy, z: cam.z });
    editor.setCameraOptions({ isLocked: true });
  },
}));
