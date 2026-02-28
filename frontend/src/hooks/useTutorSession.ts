import { create } from "zustand";
import type { TutorMode, ServerMessage, ClientMessage } from "@/types";
import { TutorWebSocket } from "@/lib/websocket";

interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

interface TutorSessionState {
  sessionId: string | null;
  tutorMode: TutorMode;
  conversationHistory: ConversationTurn[];
  isConnected: boolean;
  ws: TutorWebSocket | null;

  // Actions
  startSession: (subject: string) => void;
  endSession: () => void;
  send: (msg: ClientMessage) => void;
  _handleServerMessage: (msg: ServerMessage) => void;
}

export const useTutorSession = create<TutorSessionState>((set, get) => ({
  sessionId: null,
  tutorMode: "listening",
  conversationHistory: [],
  isConnected: false,
  ws: null,

  startSession: (subject: string) => {
    const sessionId = crypto.randomUUID();
    const ws = new TutorWebSocket(
      `ws://localhost:8000/ws/${sessionId}`,
      (msg: ServerMessage) => get()._handleServerMessage(msg),
    );

    ws.connect();
    set({ sessionId, ws, isConnected: false });

    // Send session_start once connected
    ws.onOpen(() => {
      set({ isConnected: true });
      get().send({ type: "session_start", subject });
    });
  },

  endSession: () => {
    const { ws } = get();
    ws?.disconnect();
    set({
      sessionId: null,
      ws: null,
      isConnected: false,
      conversationHistory: [],
      tutorMode: "listening",
    });
  },

  send: (msg: ClientMessage) => {
    const { ws } = get();
    ws?.send(msg);
  },

  _handleServerMessage: (msg: ServerMessage) => {
    switch (msg.type) {
      case "connected":
        set({ isConnected: true });
        break;

      case "speech_text":
        set((state) => ({
          conversationHistory: [
            ...state.conversationHistory,
            { role: "assistant", content: msg.text },
          ],
          tutorMode: "guiding",
        }));
        break;

      case "error":
        console.error("Server error:", msg.message);
        break;

      // strokes and board_action are handled by useWhiteboard
      default:
        break;
    }
  },
}));
