import type { ClientMessage, ServerMessage } from "@/types";

type MessageHandler = (msg: ServerMessage) => void;
type OpenHandler = () => void;
type CloseHandler = (code: number, reason: string) => void;

const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_ATTEMPTS = 5;

export class TutorWebSocket {
  private url: string;
  private ws: WebSocket | null = null;
  private messageHandler: MessageHandler;
  private openHandler: OpenHandler | null = null;
  private closeHandler: CloseHandler | null = null;
  private reconnectAttempts = 0;
  private shouldReconnect = true;

  constructor(url: string, messageHandler: MessageHandler) {
    this.url = url;
    this.messageHandler = messageHandler;
  }

  connect(): void {
    this.shouldReconnect = true;
    this._open();
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.ws?.close(1000, "Client disconnected");
    this.ws = null;
  }

  send(msg: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    } else {
      console.warn("WebSocket not open, dropping message:", msg.type);
    }
  }

  onOpen(handler: OpenHandler): void {
    this.openHandler = handler;
  }

  onClose(handler: CloseHandler): void {
    this.closeHandler = handler;
  }

  private _open(): void {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("WebSocket connected:", this.url);
        this.reconnectAttempts = 0;
        this.openHandler?.();
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
          this.messageHandler(msg);
        } catch (err) {
          console.error("Failed to parse server message:", err);
        }
      };

      this.ws.onclose = (event) => {
        console.log("WebSocket closed:", event.code, event.reason);
        this.closeHandler?.(event.code, event.reason);
        // 1000 = normal close, 1011 = server error — don't reconnect on these,
        // only reconnect on network-level drops (1006 = abnormal, no code)
        const isServerError = event.code === 1011;
        const isNormalClose = event.code === 1000;
        if (this.shouldReconnect && !isServerError && !isNormalClose && this.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          this.reconnectAttempts++;
          console.log(`Reconnecting in ${RECONNECT_DELAY_MS}ms (attempt ${this.reconnectAttempts})`);
          setTimeout(() => this._open(), RECONNECT_DELAY_MS);
        }
      };

      this.ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
    } catch (err) {
      console.error("Failed to create WebSocket:", err);
    }
  }
}
