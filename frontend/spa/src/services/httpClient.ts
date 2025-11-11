import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios";

import router from "@/router";
import { pinia } from "@/stores";
import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
  skipAuthRedirect?: boolean;
}

const API_TIMEOUT = 15_000;
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

const httpClient = axios.create({
  baseURL: BASE_URL,
  timeout: API_TIMEOUT,
  withCredentials: true,
});

let refreshPromise: Promise<AxiosResponse | void> | null = null;

function notifyError(message: string, detail?: string) {
  const notifications = useNotificationsStore(pinia);
  notifications.push({ message, detail, variant: "error" });
}

async function refreshSession() {
  const auth = useAuthStore(pinia);
  if (!refreshPromise) {
    refreshPromise = auth
      .refreshTokens()
      .catch((error) => {
        auth.purge();
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  await refreshPromise;
}

httpClient.interceptors.request.use((config) => {
  const auth = useAuthStore(pinia);
  if (auth.accessToken && config.headers) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  return config;
});

httpClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const { response, config } = error;
    const requestConfig = config as RetryableRequestConfig | undefined;
    const requestUrl = requestConfig?.url ?? "";
    const isAuthLogin =
      typeof requestUrl === "string" && requestUrl.includes("/auth/login");
    const isAuthRefresh =
      typeof requestUrl === "string" && requestUrl.includes("/auth/refresh");

    if (
      response?.status === 401 &&
      requestConfig &&
      !requestConfig._retry &&
      !isAuthLogin &&
      !isAuthRefresh
    ) {
      requestConfig._retry = true;
      try {
        await refreshSession();
        const auth = useAuthStore(pinia);
        if (requestConfig.headers && auth.accessToken) {
          requestConfig.headers.Authorization = `Bearer ${auth.accessToken}`;
        }
        return httpClient(requestConfig);
      } catch (refreshError) {
        if (!requestConfig.skipAuthRedirect) {
          await router.replace({ name: "login" });
          notifyError("Your session has expired", "Please sign in again to continue.");
        }
        return Promise.reject(refreshError);
      }
    }

    if (isAuthLogin) {
      return Promise.reject(error);
    }

    if (response?.status === 429) {
      notifyError("Too many requests", "Please wait a moment before trying again.");
    } else if (response?.status && response.status >= 400) {
      let detail: string | undefined;
      if (typeof response.data === "string") {
        detail = response.data;
      } else if (
        response.data &&
        typeof response.data === "object" &&
        "detail" in response.data
      ) {
        detail = String((response.data as Record<string, unknown>).detail);
      }
      notifyError(
        "Something went wrong",
        detail ?? `The server responded with status ${response.status}.`,
      );
    }

    return Promise.reject(error);
  },
);

export default httpClient;
