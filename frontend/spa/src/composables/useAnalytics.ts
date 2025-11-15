/* Vue composables for analytics tracking */

import { computed, getCurrentInstance, onMounted, watch } from "vue";
import { useRoute } from "vue-router";

import { getAnalytics, type UserProperties } from "@/services/analytics";
import { useAuthStore } from "@/stores/auth";

export function useAnalytics() {
  const authStore = useAuthStore();
  const route = useRoute();
  const analytics = getAnalytics();
  const instance = getCurrentInstance();

  // Track page views
  const trackPageView = (path?: string, title?: string) => {
    if (!analytics) return;

    const currentPath = path || route.path;
    const currentTitle = title || (route.meta?.title as string) || document.title;

    analytics.trackPageView(currentPath, currentTitle);
  };

  // Track feature usage
  const trackFeatureUsage = (
    featureName: string,
    properties?: Record<string, unknown>,
  ) => {
    if (!analytics) return;
    analytics.trackFeatureUsage(featureName, properties);
  };

  // Track form interactions
  const trackFormInteraction = (
    formName: string,
    action: "start" | "submit" | "abandon" | "validate",
    properties?: Record<string, unknown>,
  ) => {
    if (!analytics) return;
    analytics.track({
      event_type: "form_interaction",
      event_data: {
        form_name: formName,
        action,
        ...properties,
      },
    });
  };

  // Track user events
  const trackUserEvent = (
    eventType: string,
    properties?: Record<string, unknown>,
    userProperties?: UserProperties,
  ) => {
    if (!analytics) return;

    const event = {
      event_type: eventType,
      event_data: properties,
    };

    if (userProperties && authStore.user) {
      analytics.setUserProperties(userProperties);
    }

    analytics.track(event);
  };

  // Track authentication events
  const trackAuth = (
    action: "login" | "logout" | "signup",
    properties?: Record<string, unknown>,
  ) => {
    trackUserEvent(action, properties);
  };

  // Track generation events
  const trackGeneration = (
    status: "started" | "completed" | "failed",
    properties?: Record<string, unknown>,
  ) => {
    trackUserEvent(`generation_${status}`, {
      timestamp: new Date().toISOString(),
      ...properties,
    });
  };

  // Track payment events
  const trackPayment = (
    status: "initiated" | "completed" | "failed",
    properties: {
      amount: number;
      currency: string;
      payment_method?: string;
    },
  ) => {
    trackUserEvent(`payment_${status}`, {
      timestamp: new Date().toISOString(),
      ...properties,
    });
  };

  // Track referral events
  const trackReferral = (
    action: "sent" | "accepted" | "milestone_reached",
    properties?: Record<string, unknown>,
  ) => {
    trackUserEvent(`referral_${action}`, {
      timestamp: new Date().toISOString(),
      ...properties,
    });
  };

  // Track errors
  const trackError = (
    errorType: string,
    errorMessage: string,
    context?: Record<string, unknown>,
  ) => {
    if (!analytics) return;
    analytics.trackError(errorType, errorMessage, context);
  };

  // Update user properties when auth state changes
  const updateUserProperties = () => {
    if (!analytics || !authStore.user) return;

    const userProperties: UserProperties = {
      userId: authStore.user.id,
      subscriptionLevel: authStore.user.subscriptionLevel || "free",
      registrationDate: authStore.user.createdAt,
    };

    // Only include PII if enabled (this would be determined by backend config)
    if (authStore.user.email) {
      userProperties.email = authStore.user.email;
    }
    if (authStore.user.name) {
      userProperties.name = authStore.user.name;
    }

    analytics.identify(authStore.user.id, userProperties);
  };

  // Auto-track page views on route changes
  const setupPageTracking = () => {
    let lastPath = route.path;

    watch(
      () => route.path,
      (newPath) => {
        if (newPath !== lastPath) {
          trackPageView();
          lastPath = newPath;
        }
      },
      { immediate: true },
    );
  };

  // Auto-track user authentication state
  const setupAuthTracking = () => {
    watch(
      () => authStore.isAuthenticated,
      (isAuthenticated, wasAuthenticated) => {
        if (isAuthenticated && !wasAuthenticated) {
          // User just logged in
          updateUserProperties();
          trackAuth("login");
        } else if (!isAuthenticated && wasAuthenticated) {
          // User just logged out
          analytics?.reset();
          trackAuth("logout");
        }
      },
      { immediate: true },
    );

    // Also watch for user data changes
    watch(
      () => authStore.user,
      () => {
        if (authStore.isAuthenticated) {
          updateUserProperties();
        }
      },
      { deep: true },
    );
  };

  // Initialize tracking on mount
  if (instance) {
    onMounted(() => {
      setupPageTracking();
      setupAuthTracking();

      // Track initial page view
      if (analytics) {
        trackPageView();

        // Update user properties if already authenticated
        if (authStore.isAuthenticated) {
          updateUserProperties();
        }
      }
    });
  }

  return {
    // Core tracking methods
    trackPageView,
    trackFeatureUsage,
    trackFormInteraction,
    trackUserEvent,
    trackError,

    // Specific event tracking
    trackAuth,
    trackGeneration,
    trackPayment,
    trackReferral,

    // Utility methods
    updateUserProperties,

    // Computed properties
    isAnalyticsEnabled: computed(() => !!analytics),
  };
}

// Composable for form analytics
export function useFormAnalytics(formName: string, formType: string) {
  const { trackFormInteraction } = useAnalytics();
  let startTime: number | null = null;

  const ensureStartTime = () => {
    if (startTime === null) {
      startTime = Date.now();
    }

    return startTime;
  };

  const calculateCompletionTime = () => {
    const startedAt = ensureStartTime();
    return Date.now() - startedAt;
  };

  const resetStartTime = () => {
    startTime = null;
  };

  const startForm = () => {
    startTime = Date.now();
    trackFormInteraction(formName, "start", {
      form_type: formType,
    });
  };

  const submitForm = (success: boolean, errors?: string[]) => {
    const completionTime = calculateCompletionTime();

    const payload: Record<string, unknown> = {
      form_type: formType,
      success,
      completion_time: completionTime,
    };

    if (errors && errors.length > 0) {
      payload.field_errors = errors;
    }

    trackFormInteraction(formName, "submit", payload);
    resetStartTime();
  };

  const abandonForm = () => {
    const completionTime = calculateCompletionTime();

    trackFormInteraction(formName, "abandon", {
      form_type: formType,
      completion_time: completionTime,
    });
    resetStartTime();
  };

  const validateForm = (errors: string[]) => {
    trackFormInteraction(formName, "validate", {
      form_type: formType,
      field_errors: errors,
    });
  };

  return {
    startForm,
    submitForm,
    abandonForm,
    validateForm,
  };
}

// Composable for feature analytics
export function useFeatureAnalytics(featureName: string, category?: string) {
  const { trackFeatureUsage } = useAnalytics();

  const trackFeature = (action?: string, properties?: Record<string, unknown>) => {
    const payload: Record<string, unknown> = {};

    if (category !== undefined) {
      payload.category = category;
    }

    if (action !== undefined) {
      payload.action = action;
    }

    if (properties) {
      Object.assign(payload, properties);
    }

    trackFeatureUsage(featureName, payload);
  };

  const trackFeatureClick = (element?: string) => {
    const payload: Record<string, unknown> = {};

    if (element !== undefined) {
      payload.element = element;
    }

    trackFeatureUsage(featureName, payload);
  };

  const trackFeatureView = (properties?: Record<string, unknown>) => {
    const payload: Record<string, unknown> = {
      action: "view",
    };

    if (category !== undefined) {
      payload.category = category;
    }

    if (properties) {
      Object.assign(payload, properties);
    }

    trackFeatureUsage(featureName, payload);
  };

  return {
    trackFeature,
    trackFeatureClick,
    trackFeatureView,
  };
}
