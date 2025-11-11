/* Tests for analytics composables */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ref } from "vue";

import {
  useAnalytics,
  useFormAnalytics,
  useFeatureAnalytics,
} from "@/composables/useAnalytics";
import { getAnalytics, type AnalyticsClient } from "@/services/analytics";

const mockedGetAnalytics = vi.mocked(getAnalytics);

// Mock analytics client
vi.mock("@/services/analytics", () => ({
  getAnalytics: vi.fn(),
  AnalyticsClient: vi.fn().mockImplementation(() => ({
    track: vi.fn(),
    identify: vi.fn(),
    setUserProperties: vi.fn(),
    reset: vi.fn(),
    trackPageView: vi.fn(),
    trackFeatureUsage: vi.fn(),
    trackError: vi.fn(),
  })),
}));

// Mock auth store
vi.mock("@/stores/auth", () => ({
  useAuthStore: vi.fn().mockReturnValue({
    isAuthenticated: ref(true),
    user: ref({
      id: "test-user-id",
      email: "test@example.com",
      name: "Test User",
      subscriptionLevel: "pro",
      createdAt: "2024-01-01T00:00:00Z",
    }),
  }),
}));

// Mock vue router
vi.mock("vue-router", () => ({
  useRoute: vi.fn().mockReturnValue({
    path: "/test",
    meta: { title: "Test Page" },
  }),
}));

describe("useAnalytics", () => {
  let mockAnalytics: AnalyticsClient;

  beforeEach(() => {
    mockAnalytics = {
      track: vi.fn(),
      identify: vi.fn(),
      setUserProperties: vi.fn(),
      reset: vi.fn(),
      trackPageView: vi.fn(),
      trackFeatureUsage: vi.fn(),
      trackFormInteraction: vi.fn(),
      trackError: vi.fn(),
      destroy: vi.fn(),
    } as unknown as AnalyticsClient;

    mockedGetAnalytics.mockReturnValue(mockAnalytics);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should return analytics functions", () => {
    const analytics = useAnalytics();

    expect(analytics).toHaveProperty("trackPageView");
    expect(analytics).toHaveProperty("trackFeatureUsage");
    expect(analytics).toHaveProperty("trackFormInteraction");
    expect(analytics).toHaveProperty("trackUserEvent");
    expect(analytics).toHaveProperty("trackAuth");
    expect(analytics).toHaveProperty("trackGeneration");
    expect(analytics).toHaveProperty("trackPayment");
    expect(analytics).toHaveProperty("trackReferral");
    expect(analytics).toHaveProperty("trackError");
    expect(analytics).toHaveProperty("updateUserProperties");
  });

  it("should track page view correctly", () => {
    const { trackPageView } = useAnalytics();

    trackPageView("/test-path", "Test Title");

    expect(mockAnalytics.trackPageView).toHaveBeenCalledWith(
      "/test-path",
      "Test Title",
    );
  });

  it("should track feature usage correctly", () => {
    const { trackFeatureUsage } = useAnalytics();

    trackFeatureUsage("test-feature", { action: "click", value: 42 });

    expect(mockAnalytics.trackFeatureUsage).toHaveBeenCalledWith("test-feature", {
      action: "click",
      value: 42,
    });
  });

  it("should track form interaction correctly", () => {
    const { trackFormInteraction } = useAnalytics();

    trackFormInteraction("signup-form", "submit", { completion_time: 1500 });

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "form_interaction",
      event_data: {
        form_name: "signup-form",
        action: "submit",
        completion_time: 1500,
      },
    });
  });

  it("should track user event correctly", () => {
    const { trackUserEvent } = useAnalytics();

    trackUserEvent("custom_event", { prop1: "value1" }, { user_prop: "value2" });

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "custom_event",
      event_data: { prop1: "value1" },
    });
    expect(mockAnalytics.setUserProperties).toHaveBeenCalledWith({
      user_prop: "value2",
    });
  });

  it("should track authentication events correctly", () => {
    const { trackAuth } = useAnalytics();

    trackAuth("login", { method: "email" });

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "login",
      event_data: { method: "email" },
    });
  });

  it("should track generation events correctly", () => {
    const { trackGeneration } = useAnalytics();

    trackGeneration("completed", { type: "image", duration: 5000 });

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "generation_completed",
      event_data: {
        timestamp: expect.any(String),
        type: "image",
        duration: 5000,
      },
    });
  });

  it("should track payment events correctly", () => {
    const { trackPayment } = useAnalytics();

    trackPayment("completed", {
      amount: 29.99,
      currency: "USD",
      payment_method: "card",
    });

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "payment_completed",
      event_data: {
        timestamp: expect.any(String),
        amount: 29.99,
        currency: "USD",
        payment_method: "card",
      },
    });
  });

  it("should track referral events correctly", () => {
    const { trackReferral } = useAnalytics();

    trackReferral("accepted", { referral_code: "ABC123" });

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "referral_accepted",
      event_data: {
        timestamp: expect.any(String),
        referral_code: "ABC123",
      },
    });
  });

  it("should track errors correctly", () => {
    const { trackError } = useAnalytics();

    trackError("validation_error", "Invalid email format", { field: "email" });

    expect(mockAnalytics.trackError).toHaveBeenCalledWith(
      "validation_error",
      "Invalid email format",
      { field: "email" },
    );
  });
});

describe("useFormAnalytics", () => {
  let mockAnalytics: AnalyticsClient;

  beforeEach(() => {
    mockAnalytics = {
      track: vi.fn(),
      identify: vi.fn(),
      setUserProperties: vi.fn(),
      reset: vi.fn(),
      trackPageView: vi.fn(),
      trackFeatureUsage: vi.fn(),
      trackFormInteraction: vi.fn(),
      trackError: vi.fn(),
      destroy: vi.fn(),
    } as unknown as AnalyticsClient;

    mockedGetAnalytics.mockReturnValue(mockAnalytics);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should track form start correctly", () => {
    const { startForm } = useFormAnalytics("signup-form", "registration");

    startForm();

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "form_interaction",
      event_data: {
        form_name: "signup-form",
        action: "start",
        form_type: "registration",
      },
    });
  });

  it("should track form submit correctly", () => {
    const { submitForm } = useFormAnalytics("signup-form", "registration");

    submitForm(true);

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "form_interaction",
      event_data: {
        form_name: "signup-form",
        action: "submit",
        form_type: "registration",
        success: true,
        completion_time: expect.any(Number),
      },
    });
  });

  it("should track form submit with errors correctly", () => {
    const { submitForm } = useFormAnalytics("signup-form", "registration");

    submitForm(false, ["email", "password"]);

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "form_interaction",
      event_data: {
        form_name: "signup-form",
        action: "submit",
        form_type: "registration",
        success: false,
        completion_time: expect.any(Number),
        field_errors: ["email", "password"],
      },
    });
  });

  it("should track form abandon correctly", () => {
    const { abandonForm } = useFormAnalytics("signup-form", "registration");

    abandonForm();

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "form_interaction",
      event_data: {
        form_name: "signup-form",
        action: "abandon",
        form_type: "registration",
        completion_time: expect.any(Number),
      },
    });
  });

  it("should track form validation correctly", () => {
    const { validateForm } = useFormAnalytics("signup-form", "registration");

    validateForm(["email"]);

    expect(mockAnalytics.track).toHaveBeenCalledWith({
      event_type: "form_interaction",
      event_data: {
        form_name: "signup-form",
        action: "validate",
        form_type: "registration",
        field_errors: ["email"],
      },
    });
  });
});

describe("useFeatureAnalytics", () => {
  let mockAnalytics: AnalyticsClient;

  beforeEach(() => {
    mockAnalytics = {
      track: vi.fn(),
      identify: vi.fn(),
      setUserProperties: vi.fn(),
      reset: vi.fn(),
      trackPageView: vi.fn(),
      trackFeatureUsage: vi.fn(),
      trackFormInteraction: vi.fn(),
      trackError: vi.fn(),
      destroy: vi.fn(),
    } as unknown as AnalyticsClient;

    mockedGetAnalytics.mockReturnValue(mockAnalytics);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should track feature usage correctly", () => {
    const { trackFeature } = useFeatureAnalytics("image-generator", "generation");

    trackFeature("click", { button: "generate" });

    expect(mockAnalytics.trackFeatureUsage).toHaveBeenCalledWith("image-generator", {
      category: "generation",
      action: "click",
      button: "generate",
    });
  });

  it("should track feature click correctly", () => {
    const { trackFeatureClick } = useFeatureAnalytics("image-generator");

    trackFeatureClick("generate-button");

    expect(mockAnalytics.trackFeatureUsage).toHaveBeenCalledWith("image-generator", {
      element: "generate-button",
    });
  });

  it("should track feature view correctly", () => {
    const { trackFeatureView } = useFeatureAnalytics("image-generator");

    trackFeatureView({ source: "navigation" });

    expect(mockAnalytics.trackFeatureUsage).toHaveBeenCalledWith("image-generator", {
      action: "view",
      source: "navigation",
    });
  });
});
