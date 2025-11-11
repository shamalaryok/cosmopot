import httpClient from "@/services/httpClient";
import type { components } from "@/types/generated/schema";

export type LoginRequest = components["schemas"]["LoginRequest"];
export type LogoutRequest = components["schemas"]["LogoutRequest"];
export type RefreshRequest = components["schemas"]["RefreshRequest"];
export type TokenResponse = components["schemas"]["TokenResponse"];

const basePath = "/api/v1/auth";

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const { data } = await httpClient.post<TokenResponse>(`${basePath}/login`, payload, {
    skipAuthRedirect: true,
  });
  return data;
}

export async function refresh(payload?: RefreshRequest): Promise<TokenResponse> {
  const { data } = await httpClient.post<TokenResponse>(
    `${basePath}/refresh`,
    payload ?? {},
  );
  return data;
}

export async function logout(payload: LogoutRequest): Promise<void> {
  await httpClient.post(`${basePath}/logout`, payload ?? {});
}
