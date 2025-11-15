/* Analytics types and interfaces */

export interface AnalyticsEvent {
  event_type: string;
  event_data?: Record<string, unknown>;
  user_properties?: Record<string, unknown>;
  session_id?: string;
  provider?: "amplitude" | "mixpanel" | "both";
}

export interface AnalyticsConfig {
  enabled: boolean;
  amplitudeApiKey?: string;
  mixpanelToken?: string;
  piiTrackingEnabled: boolean;
  sandboxMode: boolean;
  batchSize: number;
  flushInterval: number;
}

export interface AnalyticsProvider {
  name: string;
  isInitialized: boolean;
  track(event: string, properties?: Record<string, unknown>): Promise<void>;
  identify(userId: string, properties?: Record<string, unknown>): Promise<void>;
  setUserProperties(properties: Record<string, unknown>): Promise<void>;
  reset(): Promise<void>;
}

export interface AnalyticsEventQueue {
  events: AnalyticsEvent[];
  isProcessing: boolean;
  lastFlush: number;
}

export interface UserProperties {
  userId?: string;
  email?: string;
  name?: string;
  subscriptionLevel?: string;
  registrationDate?: string;
  lastLoginDate?: string;
  [key: string]: unknown;
}

export interface PageViewEvent {
  path: string;
  title?: string;
  referrer?: string;
  search?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_term?: string;
  utm_content?: string;
}

export interface FeatureUsageEvent {
  feature_name: string;
  category?: string;
  action?: string;
  label?: string;
  value?: number;
}

export interface FormInteractionEvent {
  form_name: string;
  form_type: string;
  action: "start" | "submit" | "abandon" | "validate";
  field_errors?: string[];
  completion_time?: number;
}

export interface ErrorEvent {
  error_type: string;
  error_message: string;
  error_stack?: string;
  context?: Record<string, unknown>;
  user_agent?: string;
  url?: string;
}
