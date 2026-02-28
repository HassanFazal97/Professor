// ── Tutor state ──────────────────────────────────────────────────────────────

export type TutorMode = "listening" | "guiding" | "demonstrating" | "evaluating";

// ── Whiteboard / Strokes ─────────────────────────────────────────────────────

export interface StrokePoint {
  x: number;
  y: number;
  pressure: number;
}

export interface Stroke {
  points: StrokePoint[];
  color: string;
  width: number;
}

export interface Position {
  x: number;
  y: number;
}

export interface StrokeData {
  strokes: Stroke[];
  position: Position;
  animation_speed: number;
}

// ── Board actions from LLM ───────────────────────────────────────────────────

export type BoardActionType = "write" | "underline" | "clear";
export type ContentFormat = "text" | "latex";

export interface WriteBoardAction {
  type: "write";
  content: string;
  format: ContentFormat;
  position: Position;
  color: string;
}

export interface UnderlineBoardAction {
  type: "underline";
  target_area: { x: number; y: number; width: number; height: number };
  color: string;
}

export interface ClearBoardAction {
  type: "clear";
}

export type BoardAction = WriteBoardAction | UnderlineBoardAction | ClearBoardAction;

// ── LLM response ─────────────────────────────────────────────────────────────

export interface LLMResponse {
  speech: string;
  board_actions: BoardAction[];
  tutor_state: TutorMode;
  wait_for_student: boolean;
}

// ── WebSocket message protocol ───────────────────────────────────────────────

// Client → Server
export interface SessionStartMessage {
  type: "session_start";
  subject: string;
}

export interface TranscriptMessage {
  type: "transcript";
  text: string;
}

export interface BoardSnapshotMessage {
  type: "board_snapshot";
  image_base64: string;
}

export interface AudioStartMessage {
  type: "audio_start";
}

export interface AudioDataMessage {
  type: "audio_data";
  data: string; // base64-encoded audio chunk (webm/opus)
}

export interface AudioStopMessage {
  type: "audio_stop";
}

export type ClientMessage =
  | SessionStartMessage
  | TranscriptMessage
  | BoardSnapshotMessage
  | AudioStartMessage
  | AudioDataMessage
  | AudioStopMessage;

// Server → Client
export interface ConnectedMessage {
  type: "connected";
  session_id: string;
  message: string;
}

export interface SpeechTextMessage {
  type: "speech_text";
  text: string;
}

export interface AudioChunkMessage {
  type: "audio_chunk";
  data: string; // base64-encoded audio bytes
}

export interface StrokesMessage {
  type: "strokes";
  strokes: StrokeData;
}

export interface BoardActionMessage {
  type: "board_action";
  action: BoardAction;
}

export interface TranscriptInterimMessage {
  type: "transcript_interim";
  text: string;
}

export interface BargeinMessage {
  type: "barge_in";
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage =
  | ConnectedMessage
  | SpeechTextMessage
  | AudioChunkMessage
  | StrokesMessage
  | BoardActionMessage
  | TranscriptInterimMessage
  | BargeinMessage
  | ErrorMessage;
