import { create } from "zustand";
import type { TutorMode, ServerMessage, ClientMessage } from "@/types";
import { TutorWebSocket } from "@/lib/websocket";
import { audioPlayer } from "@/lib/audioPlayer";
import { useWhiteboard } from "./useWhiteboard";

interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

interface TutorSessionState {
  sessionId: string | null;
  tutorMode: TutorMode;
  conversationHistory: ConversationTurn[];
  isConnected: boolean;
  adaSpeaking: boolean;     // true while Ada's audio is playing
  waitForStudent: boolean;  // true when Ada asked a question and is waiting
  ws: TutorWebSocket | null;

  // Actions
  startSession: () => void;
  endSession: () => void;
  send: (msg: ClientMessage) => void;
  sendTranscript: (text: string) => void;
  setAdaSpeaking: (val: boolean) => void;
  _handleServerMessage: (msg: ServerMessage) => void;
}

export const useTutorSession = create<TutorSessionState>((set, get) => {
  const resolveWsUrl = (sessionId: string): string => {
    const configured = process.env.NEXT_PUBLIC_BACKEND_WS_URL?.trim();
    if (configured) {
      const normalized = configured
        .replace(/^http:\/\//i, "ws://")
        .replace(/^https:\/\//i, "wss://")
        .replace(/\/+$/, "");
      const base = normalized.startsWith("ws://") || normalized.startsWith("wss://")
        ? normalized
        : `ws://${normalized}`;
      return `${base}/ws/${sessionId}`;
    }

    if (typeof window !== "undefined") {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${window.location.hostname}:8000/ws/${sessionId}`;
    }

    return `ws://localhost:8000/ws/${sessionId}`;
  };

  // When Ada finishes speaking naturally (queue drained), clear the speaking
  // flag so the microphone gate opens and the student can be heard again.
  audioPlayer.onDrained = () => set({ adaSpeaking: false });

  return {
  sessionId: null,
  tutorMode: "listening",
  conversationHistory: [],
  isConnected: false,
  adaSpeaking: false,
  waitForStudent: false,
  ws: null,

  startSession: () => {
    // Unlock AudioContext while we're still inside the click handler
    audioPlayer.resume();

    const sessionId = crypto.randomUUID();
    const ws = new TutorWebSocket(
      resolveWsUrl(sessionId),
      (msg: ServerMessage) => get()._handleServerMessage(msg),
    );

    ws.connect();
    set({ sessionId, ws, isConnected: false });

    // Send session_start once connected
    ws.onOpen(() => {
      set({ isConnected: true });
      get().send({ type: "session_start", subject: "" });
    });

    ws.onClose(() => {
      set({ isConnected: false, adaSpeaking: false });
    });
  },

  setAdaSpeaking: (val: boolean) => set({ adaSpeaking: val }),

  endSession: () => {
    const { ws } = get();
    ws?.disconnect();
    audioPlayer.stop();
    set({
      sessionId: null,
      ws: null,
      isConnected: false,
      adaSpeaking: false,
      waitForStudent: false,
      conversationHistory: [],
      tutorMode: "listening",
    });
  },

  send: (msg: ClientMessage) => {
    const { ws } = get();
    ws?.send(msg);
  },

  sendTranscript: (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    // Optimistically add to conversation so UI updates immediately
    set((state) => ({
      conversationHistory: [
        ...state.conversationHistory,
        { role: "user", content: trimmed },
      ],
    }));
    get().send({ type: "transcript", text: trimmed });
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

      case "barge_in":
        // User started speaking — cut Ada's audio and stroke animation immediately
        audioPlayer.stop();
        set({ adaSpeaking: false, waitForStudent: false });
        useWhiteboard.getState().cancelStrokes();
        break;

      case "audio_chunk":
        set({ adaSpeaking: true });
        audioPlayer.enqueue(msg.data);
        break;

      case "strokes":
        useWhiteboard.getState().setIncomingStrokes(msg.strokes);
        break;

      case "board_action":
        useWhiteboard.getState().addBoardAction(msg.action);
        break;

      case "transcript_interim":
        // Add the user's spoken words to the conversation immediately,
        // before Ada's response arrives, so the UI feels responsive.
        // Also clear waitForStudent — the student is responding.
        set((state) => {
          const last = state.conversationHistory[state.conversationHistory.length - 1];
          if (last?.role === "user" && last.content === msg.text) {
            return { waitForStudent: false };
          }
          return {
            conversationHistory: [
              ...state.conversationHistory,
              { role: "user", content: msg.text },
            ],
            waitForStudent: false,
          };
        });
        break;

      case "state_update":
        set({ tutorMode: msg.tutor_state, waitForStudent: msg.wait_for_student });
        break;

      case "scroll_board":
        useWhiteboard.getState().scrollBoard(msg.scroll_by);
        break;

      case "error":
        console.error("Server error:", msg.message);
        break;

      // strokes and board_action are handled by useWhiteboard
      default:
        break;
    }
  },
  };
});
