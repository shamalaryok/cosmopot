import httpClient from "./httpClient";

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminUser {
  id: number;
  email: string;
  role: string;
  balance: string;
  is_active: boolean;
  subscription_id: number | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface AdminUserCreate {
  email: string;
  password: string;
  role?: string;
  is_active?: boolean;
}

export interface AdminUserUpdate {
  email?: string;
  role?: string;
  is_active?: boolean;
  balance?: string;
}

export interface AdminSubscription {
  id: number;
  user_id: number;
  tier: string;
  status: string;
  auto_renew: boolean;
  quota_limit: number;
  quota_used: number;
  current_period_start: string;
  current_period_end: string;
  canceled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminSubscriptionUpdate {
  tier?: string;
  status?: string;
  auto_renew?: boolean;
  quota_limit?: number;
  quota_used?: number;
}

export interface AdminPrompt {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  category: string;
  source: string;
  version: number;
  parameters: Record<string, unknown>;
  is_active: boolean;
  preview_asset_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminPromptCreate {
  slug: string;
  name: string;
  description?: string | null;
  category?: string;
  source?: string;
  version?: number;
  parameters_schema?: Record<string, unknown>;
  parameters?: Record<string, unknown>;
  is_active?: boolean;
  preview_asset_url?: string | null;
}

export interface AdminPromptUpdate {
  name?: string;
  description?: string | null;
  category?: string;
  parameters?: Record<string, unknown>;
  is_active?: boolean;
  preview_asset_url?: string | null;
}

export interface AdminGeneration {
  id: number;
  user_id: number;
  prompt_id: number;
  status: string;
  source: string;
  parameters: Record<string, unknown>;
  result_parameters: Record<string, unknown>;
  input_asset_url: string | null;
  result_asset_url: string | null;
  error: string | null;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminGenerationUpdate {
  status?: string;
  error?: string | null;
}

export interface AdminModerationAction {
  action: "approve" | "reject" | "flag";
  reason?: string | null;
}

export interface AdminAnalytics {
  total_users: number;
  active_users: number;
  total_subscriptions: number;
  active_subscriptions: number;
  total_generations: number;
  generations_today: number;
  generations_this_week: number;
  generations_this_month: number;
  failed_generations: number;
  revenue_total: string;
  revenue_this_month: string;
}

export interface FilterParams {
  page?: number;
  page_size?: number;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

export interface UserFilters extends FilterParams {
  role?: string;
  is_active?: boolean;
}

export interface SubscriptionFilters extends FilterParams {
  user_id?: number;
  tier?: string;
  status?: string;
}

export interface PromptFilters extends FilterParams {
  category?: string;
  is_active?: boolean;
}

export interface GenerationFilters extends FilterParams {
  user_id?: number;
  prompt_id?: number;
  status?: string;
}

// Analytics
export async function getAnalytics(): Promise<AdminAnalytics> {
  const { data } = await httpClient.get<AdminAnalytics>("/api/v1/admin/analytics");
  return data;
}

// Users
export async function listUsers(
  filters?: UserFilters,
): Promise<PaginatedResponse<AdminUser>> {
  const { data } = await httpClient.get<PaginatedResponse<AdminUser>>(
    "/api/v1/admin/users",
    { params: filters },
  );
  return data;
}

export async function getUser(userId: number): Promise<AdminUser> {
  const { data } = await httpClient.get<AdminUser>(`/api/v1/admin/users/${userId}`);
  return data;
}

export async function createUser(payload: AdminUserCreate): Promise<AdminUser> {
  const { data } = await httpClient.post<AdminUser>("/api/v1/admin/users", payload);
  return data;
}

export async function updateUser(
  userId: number,
  payload: AdminUserUpdate,
): Promise<AdminUser> {
  const { data } = await httpClient.patch<AdminUser>(
    `/api/v1/admin/users/${userId}`,
    payload,
  );
  return data;
}

export async function deleteUser(userId: number): Promise<void> {
  await httpClient.delete(`/api/v1/admin/users/${userId}`);
}

export async function exportUsers(format: "csv" | "json"): Promise<Blob> {
  const { data } = await httpClient.get(`/api/v1/admin/users/export/${format}`, {
    responseType: "blob",
  });
  return data;
}

// Subscriptions
export async function listSubscriptions(
  filters?: SubscriptionFilters,
): Promise<PaginatedResponse<AdminSubscription>> {
  const { data } = await httpClient.get<PaginatedResponse<AdminSubscription>>(
    "/api/v1/admin/subscriptions",
    { params: filters },
  );
  return data;
}

export async function getSubscription(
  subscriptionId: number,
): Promise<AdminSubscription> {
  const { data } = await httpClient.get<AdminSubscription>(
    `/api/v1/admin/subscriptions/${subscriptionId}`,
  );
  return data;
}

export async function updateSubscription(
  subscriptionId: number,
  payload: AdminSubscriptionUpdate,
): Promise<AdminSubscription> {
  const { data } = await httpClient.patch<AdminSubscription>(
    `/api/v1/admin/subscriptions/${subscriptionId}`,
    payload,
  );
  return data;
}

export async function exportSubscriptions(format: "csv" | "json"): Promise<Blob> {
  const { data } = await httpClient.get(
    `/api/v1/admin/subscriptions/export/${format}`,
    {
      responseType: "blob",
    },
  );
  return data;
}

// Prompts
export async function listPrompts(
  filters?: PromptFilters,
): Promise<PaginatedResponse<AdminPrompt>> {
  const { data } = await httpClient.get<PaginatedResponse<AdminPrompt>>(
    "/api/v1/admin/prompts",
    { params: filters },
  );
  return data;
}

export async function getPrompt(promptId: number): Promise<AdminPrompt> {
  const { data } = await httpClient.get<AdminPrompt>(
    `/api/v1/admin/prompts/${promptId}`,
  );
  return data;
}

export async function createPrompt(payload: AdminPromptCreate): Promise<AdminPrompt> {
  const { data } = await httpClient.post<AdminPrompt>("/api/v1/admin/prompts", payload);
  return data;
}

export async function updatePrompt(
  promptId: number,
  payload: AdminPromptUpdate,
): Promise<AdminPrompt> {
  const { data } = await httpClient.patch<AdminPrompt>(
    `/api/v1/admin/prompts/${promptId}`,
    payload,
  );
  return data;
}

export async function deletePrompt(promptId: number): Promise<void> {
  await httpClient.delete(`/api/v1/admin/prompts/${promptId}`);
}

export async function exportPrompts(format: "csv" | "json"): Promise<Blob> {
  const { data } = await httpClient.get(`/api/v1/admin/prompts/export/${format}`, {
    responseType: "blob",
  });
  return data;
}

// Generations
export async function listGenerations(
  filters?: GenerationFilters,
): Promise<PaginatedResponse<AdminGeneration>> {
  const { data } = await httpClient.get<PaginatedResponse<AdminGeneration>>(
    "/api/v1/admin/generations",
    { params: filters },
  );
  return data;
}

export async function getGeneration(generationId: number): Promise<AdminGeneration> {
  const { data } = await httpClient.get<AdminGeneration>(
    `/api/v1/admin/generations/${generationId}`,
  );
  return data;
}

export async function updateGeneration(
  generationId: number,
  payload: AdminGenerationUpdate,
): Promise<AdminGeneration> {
  const { data } = await httpClient.patch<AdminGeneration>(
    `/api/v1/admin/generations/${generationId}`,
    payload,
  );
  return data;
}

export async function moderateGeneration(
  generationId: number,
  payload: AdminModerationAction,
): Promise<AdminGeneration> {
  const { data } = await httpClient.post<AdminGeneration>(
    `/api/v1/admin/generations/${generationId}/moderate`,
    payload,
  );
  return data;
}

export async function exportGenerations(format: "csv" | "json"): Promise<Blob> {
  const { data } = await httpClient.get(`/api/v1/admin/generations/export/${format}`, {
    responseType: "blob",
  });
  return data;
}
