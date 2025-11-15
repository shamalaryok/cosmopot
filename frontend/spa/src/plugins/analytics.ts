/* Vue plugin for analytics */

import type { App } from "vue";

import type { AnalyticsConfig, AnalyticsClient } from "@/services/analytics";
import { initializeAnalytics } from "@/services/analytics";

export interface AnalyticsPluginOptions {
  config: AnalyticsConfig;
  autoTrack?: {
    pageViews?: boolean;
    clicks?: boolean;
    formSubmissions?: boolean;
    errors?: boolean;
  };
}

export const AnalyticsPlugin = {
  install(app: App, options: AnalyticsPluginOptions) {
    const { config, autoTrack = {} } = options;

    // Initialize analytics client
    const analyticsClient = initializeAnalytics(config);

    // Provide analytics client globally
    app.provide("analytics", analyticsClient);

    // Auto-track features if enabled
    if (autoTrack.pageViews !== false) {
      setupAutoPageTracking(analyticsClient);
    }

    if (autoTrack.clicks) {
      setupAutoClickTracking(analyticsClient);
    }

    if (autoTrack.formSubmissions) {
      setupAutoFormTracking(analyticsClient);
    }

    if (autoTrack.errors) {
      setupAutoErrorTracking(analyticsClient);
    }
  },
};

function setupAutoPageTracking(analytics: AnalyticsClient) {
  // Track initial page view
  analytics.trackPageView(window.location.pathname, document.title);

  // Track page changes for SPA
  let lastPath = window.location.pathname;

  const observer = new MutationObserver(() => {
    if (window.location.pathname !== lastPath) {
      lastPath = window.location.pathname;
      analytics.trackPageView(window.location.pathname, document.title);
    }
  });

  observer.observe(document, { subtree: true, childList: true });
}

function setupAutoClickTracking(analytics: AnalyticsClient) {
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement;
    const element = target.closest("[data-analytics-track]") as HTMLElement;

    if (element) {
      const eventName = element.dataset.analyticsTrack || "click";
      const eventData = {
        element: element.tagName.toLowerCase(),
        text: element.textContent?.slice(0, 100),
        id: element.id,
        class: element.className,
        href: (element as HTMLAnchorElement).href,
      };

      // Remove empty values
      Object.keys(eventData).forEach((key) => {
        if (!eventData[key as keyof typeof eventData]) {
          delete eventData[key as keyof typeof eventData];
        }
      });

      analytics.track({
        event_type: eventName,
        event_data: eventData,
      });
    }
  });
}

function setupAutoFormTracking(analytics: AnalyticsClient) {
  const forms = document.querySelectorAll("form[data-analytics-form]");

  forms.forEach((form) => {
    const formName = (form as HTMLFormElement).dataset.analyticsForm || "unknown_form";
    let startTime: number;

    // Track form start
    form.addEventListener(
      "focus",
      () => {
        startTime = Date.now();
        analytics.track({
          event_type: "form_interaction",
          event_data: {
            form_name: formName,
            action: "start",
          },
        });
      },
      { once: true },
    );

    // Track form submission
    form.addEventListener("submit", (_event) => {
      const completionTime = startTime ? Date.now() - startTime : undefined;
      const formData = new FormData(form);
      const fieldCount = formData.keys();

      analytics.track({
        event_type: "form_interaction",
        event_data: {
          form_name: formName,
          action: "submit",
          completion_time: completionTime,
          field_count: Array.from(fieldCount).length,
        },
      });
    });

    // Track form abandonment
    const handleVisibilityChange = () => {
      if (document.hidden) {
        const completionTime = startTime ? Date.now() - startTime : undefined;
        analytics.track({
          event_type: "form_interaction",
          event_data: {
            form_name: formName,
            action: "abandon",
            completion_time: completionTime,
          },
        });
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    // Cleanup on page unload
    window.addEventListener("beforeunload", () => {
      const completionTime = startTime ? Date.now() - startTime : undefined;
      analytics.track({
        event_type: "form_interaction",
        event_data: {
          form_name: formName,
          action: "abandon",
          completion_time: completionTime,
        },
      });
    });
  });
}

function setupAutoErrorTracking(analytics: AnalyticsClient) {
  // Track JavaScript errors
  window.addEventListener("error", (event) => {
    analytics.track({
      event_type: "error_occurred",
      event_data: {
        error_type: "javascript",
        error_message: event.message,
        error_filename: event.filename,
        error_lineno: event.lineno,
        error_colno: event.colno,
        url: window.location.href,
        user_agent: navigator.userAgent,
      },
    });
  });

  // Track unhandled promise rejections
  window.addEventListener("unhandledrejection", (event) => {
    analytics.track({
      event_type: "error_occurred",
      event_data: {
        error_type: "promise_rejection",
        error_message: event.reason?.message || String(event.reason),
        url: window.location.href,
        user_agent: navigator.userAgent,
      },
    });
  });

  // Track API errors (intercept fetch/XHR)
  const originalFetch = window.fetch;
  window.fetch = async (...args) => {
    try {
      const response = await originalFetch(...args);

      if (!response.ok) {
        analytics.track({
          event_type: "error_occurred",
          event_data: {
            error_type: "api_error",
            error_message: `HTTP ${response.status}: ${response.statusText}`,
            url: args[0],
            method: args[1]?.method || "GET",
            status_code: response.status,
          },
        });
      }

      return response;
    } catch (error) {
      analytics.track({
        event_type: "error_occurred",
        event_data: {
          error_type: "network_error",
          error_message: (error as Error).message,
          url: args[0],
          method: args[1]?.method || "GET",
        },
      });

      throw error;
    }
  };
}

// Export plugin installation helper
export function installAnalytics(app: App, options: AnalyticsPluginOptions) {
  app.use(AnalyticsPlugin, options);
}
