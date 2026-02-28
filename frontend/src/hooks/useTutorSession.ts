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
  adaSpeaking: boolean;  // true while Ada's audio is playing
  ws: TutorWebSocket | null;

  // Actions
  startSession: (subject: string) => void;
  endSession: () => void;
  send: (msg: ClientMessage) => void;
  sendTranscript: (text: string) => void;
  setAdaSpeaking: (val: boolean) => void;
  _handleServerMessage: (msg: ServerMessage) => void;
}

export const useTutorSession = create<TutorSessionState>((set, get) => ({
  sessionId: null,
  tutorMode: "listening",
  conversationHistory: [],
  isConnected: false,
  adaSpeaking: false,
  ws: null,

  startSession: (subject: string) => {
    // Unlock AudioContext while we're still inside the click handler
    audioPlayer.resume();

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
        // User started speaking — cut Ada's audio immediately
        audioPlayer.stop();
        set({ adaSpeaking: false });
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
        // before Ada's response arrives, so the UI feels responsive
        set((state) => ({
          conversationHistory: [
            ...state.conversationHistory,
            { role: "user", content: msg.text },
          ],
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
