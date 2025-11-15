import { defineStore } from "pinia";

import * as authService from "@/services/authService";
import httpClient from "@/services/httpClient";
import { useNotificationsStore } from "@/stores/notifications";
import type { components } from "@/types/generated/schema";

export type TokenResponse = components["schemas"]["TokenResponse"];
export type UserRead = components["schemas"]["UserRead"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type RefreshRequest = components["schemas"]["RefreshRequest"];

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  accessExpiresAt: number | null;
  refreshExpiresAt: number | null;
  sessionId: string | null;
  user: UserRead | null;
  status: "idle" | "loading" | "authenticated";
}

const toEpochSeconds = (duration: number) => Math.floor(Date.now() / 1000) + duration;

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    accessToken: null,
    refreshToken: null,
    accessExpiresAt: null,
    refreshExpiresAt: null,
    sessionId: null,
    user: null,
    status: "idle",
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken && state.user),
    accessTokenRemaining(state) {
      if (!state.accessExpiresAt) return 0;
      return state.accessExpiresAt - Math.floor(Date.now() / 1000);
    },
  },
  actions: {
    setSession(payload: TokenResponse) {
      this.accessToken = payload.access_token ?? null;
      this.refreshToken = payload.refresh_token ?? null;
      this.sessionId = payload.session_id ?? null;
      this.accessExpiresAt = payload.expires_in
        ? toEpochSeconds(payload.expires_in)
        : null;
      this.refreshExpiresAt = payload.refresh_expires_in
        ? toEpochSeconds(payload.refresh_expires_in)
        : null;
      this.user = payload.user ?? null;
      this.status = this.accessToken ? "authenticated" : "idle";
    },
    async login(credentials: LoginRequest) {
      this.status = "loading";
      try {
        const session = await authService.login(credentials);
        this.setSession(session);
        if (!this.user) {
          this.user = session.user ?? null;
        }
        if (!this.user) {
          await this.fetchCurrentUser();
        }
        this.status = "authenticated";
      } catch (error) {
        this.status = "idle";
        throw error;
      }
    },
    async fetchCurrentUser() {
      const { data } = await httpClient.get<UserRead>("/api/v1/auth/me");
      this.user = data;
      return data;
    },
    async refreshTokens(payload?: RefreshRequest) {
      const session = await authService.refresh(payload);
      this.setSession(session);
      this.notifySessionExtended();
      return session;
    },
    async logout() {
      try {
        await authService.logout({ refresh_token: this.refreshToken ?? undefined });
      } finally {
        this.purge();
      }
    },
    purge() {
      this.accessToken = null;
      this.refreshToken = null;
      this.accessExpiresAt = null;
      this.refreshExpiresAt = null;
      this.sessionId = null;
      this.user = null;
      this.status = "idle";
    },
    notifySessionExtended() {
      const notifications = useNotificationsStore();
      notifications.push({
        message: "Session refreshed",
        detail: "We renewed your access token in the background.",
        variant: "info",
        timeout: 4000,
      });
    },
  },
  persist: {
    paths: [
      "accessToken",
      "refreshToken",
      "accessExpiresAt",
      "refreshExpiresAt",
      "sessionId",
      "user",
    ],
  },
});
