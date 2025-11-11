import { defineStore } from "pinia";

export type NotificationVariant = "info" | "success" | "warning" | "error";

export interface NotificationMessage {
  id: string;
  message: string;
  variant: NotificationVariant;
  detail?: string;
  createdAt: number;
  timeout?: number;
}

const DEFAULT_TIMEOUT = 5000;

export const useNotificationsStore = defineStore("notifications", {
  state: () => ({
    messages: [] as NotificationMessage[],
  }),
  getters: {
    active: (state) => state.messages,
  },
  actions: {
    push(message: Omit<NotificationMessage, "id" | "createdAt"> & { id?: string }) {
      const id = message.id ?? crypto.randomUUID();
      const payload: NotificationMessage = {
        ...message,
        id,
        createdAt: Date.now(),
        timeout: message.timeout ?? DEFAULT_TIMEOUT,
      };
      this.messages.push(payload);

      if (payload.timeout && payload.timeout > 0) {
        window.setTimeout(() => this.dismiss(id), payload.timeout);
      }

      return id;
    },
    dismiss(id: string) {
      this.messages = this.messages.filter((message) => message.id !== id);
    },
    clear() {
      this.messages = [];
    },
  },
});
