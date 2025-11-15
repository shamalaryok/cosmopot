/* Analytics client for Amplitude and Mixpanel */

import type {
  AnalyticsConfig,
  AnalyticsEvent,
  AnalyticsProvider,
  UserProperties,
} from "@/types/analytics";

type AmplitudeIdentify = {
  set: (key: string, value: unknown) => void;
};

type AmplitudeInstance = {
  init: (apiKey: string, options: Record<string, unknown>) => Promise<void> | void;
  track: (event: string, properties?: Record<string, unknown>) => void;
  setUserId: (userId: string) => void;
  Identify: () => AmplitudeIdentify;
  identify: (identify: AmplitudeIdentify) => void;
  reset: () => void;
};

type MixpanelInstance = {
  init: (token: string, options: Record<string, unknown>) => void;
  track: (event: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string) => void;
  people: {
    set: (properties: Record<string, unknown>) => void;
  };
  reset: () => void;
};

class AmplitudeProvider implements AnalyticsProvider {
  name = "amplitude";
  isInitialized = false;
  private client: AmplitudeInstance | null = null;

  async initialize(apiKey: string, config: AnalyticsConfig): Promise<void> {
    try {
      const { amplitude } = await import("@amplitude/analytics-browser");

      const instance = amplitude.createInstance() as AmplitudeInstance;
      this.client = instance;
      await instance.init(apiKey, {
        defaultTracking: {
          pageViews: false, // We'll handle page views manually
          sessions: config.sandboxMode ? false : true,
          formInteractions: false,
          fileDownloads: false,
        },
        optOut: !config.enabled,
        trackingOptions: {
          ipAddress: config.piiTrackingEnabled,
          city: config.piiTrackingEnabled,
          country: config.piiTrackingEnabled,
          dma: config.piiTrackingEnabled,
          region: config.piiTrackingEnabled,
        },
      });

      this.isInitialized = true;
      console.log("Amplitude client initialized");
    } catch (error) {
      console.error("Failed to initialize Amplitude:", error);
      this.isInitialized = false;
    }
  }

  async track(event: string, properties?: Record<string, unknown>): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.track(event, properties);
    } catch (error) {
      console.error("Amplitude track error:", error);
    }
  }

  async identify(userId: string, properties?: Record<string, unknown>): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.setUserId(userId);
      if (properties) {
        const identify = this.client.Identify();
        Object.entries(properties).forEach(([key, value]) => {
          identify.set(key, value);
        });
        this.client.identify(identify);
      }
    } catch (error) {
      console.error("Amplitude identify error:", error);
    }
  }

  async setUserProperties(properties: Record<string, unknown>): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      const identify = this.client.Identify();
      Object.entries(properties).forEach(([key, value]) => {
        identify.set(key, value);
      });
      this.client.identify(identify);
    } catch (error) {
      console.error("Amplitude setUserProperties error:", error);
    }
  }

  async reset(): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.reset();
    } catch (error) {
      console.error("Amplitude reset error:", error);
    }
  }
}

class MixpanelProvider implements AnalyticsProvider {
  name = "mixpanel";
  isInitialized = false;
  private client: MixpanelInstance | null = null;

  async initialize(token: string, config: AnalyticsConfig): Promise<void> {
    try {
      const mixpanel = await import("mixpanel-browser");

      const instance = mixpanel.default as MixpanelInstance;
      this.client = instance;
      instance.init(token, {
        debug: config.sandboxMode,
        track_pageview: false, // We'll handle page views manually
        persistence: config.piiTrackingEnabled ? "localStorage" : "cookie",
        property_blacklist: config.piiTrackingEnabled
          ? []
          : ["$email", "$name", "$first_name", "$last_name", "$phone"],
      });

      this.isInitialized = true;
      console.log("Mixpanel client initialized");
    } catch (error) {
      console.error("Failed to initialize Mixpanel:", error);
      this.isInitialized = false;
    }
  }

  async track(event: string, properties?: Record<string, unknown>): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.track(event, properties);
    } catch (error) {
      console.error("Mixpanel track error:", error);
    }
  }

  async identify(userId: string, properties?: Record<string, unknown>): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.identify(userId);
      if (properties) {
        this.client.people.set(properties);
      }
    } catch (error) {
      console.error("Mixpanel identify error:", error);
    }
  }

  async setUserProperties(properties: Record<string, unknown>): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.people.set(properties);
    } catch (error) {
      console.error("Mixpanel setUserProperties error:", error);
    }
  }

  async reset(): Promise<void> {
    if (!this.isInitialized || !this.client) return;

    try {
      this.client.reset();
    } catch (error) {
      console.error("Mixpanel reset error:", error);
    }
  }
}

export class AnalyticsClient {
  private config: AnalyticsConfig;
  private providers: AnalyticsProvider[] = [];
  private eventQueue: AnalyticsEvent[] = [];
  private isProcessing = false;
  private lastFlush = 0;
  private sessionId: string;
  private userId: string | null = null;

  constructor(config: AnalyticsConfig) {
    this.config = config;
    this.sessionId = this.generateSessionId();
    this.initializeProviders();
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private async initializeProviders(): Promise<void> {
    if (!this.config.enabled) return;

    const promises: Promise<void>[] = [];

    if (this.config.amplitudeApiKey) {
      const amplitudeProvider = new AmplitudeProvider();
      promises.push(
        amplitudeProvider.initialize(this.config.amplitudeApiKey, this.config),
      );
      this.providers.push(amplitudeProvider);
    }

    if (this.config.mixpanelToken) {
      const mixpanelProvider = new MixpanelProvider();
      promises.push(
        mixpanelProvider.initialize(this.config.mixpanelToken, this.config),
      );
      this.providers.push(mixpanelProvider);
    }

    try {
      await Promise.all(promises);
    } catch (error) {
      console.error("Error initializing analytics providers:", error);
    }
  }

  async track(event: AnalyticsEvent): Promise<void> {
    if (!this.config.enabled) return;

    const enrichedEvent: AnalyticsEvent = {
      ...event,
      session_id: event.session_id || this.sessionId,
      provider: event.provider || "both",
    };

    // Add to queue for batching
    this.eventQueue.push(enrichedEvent);

    // Auto-flush if queue is full or it's time to flush
    if (
      this.eventQueue.length >= this.config.batchSize ||
      Date.now() - this.lastFlush >= this.config.flushInterval
    ) {
      await this.flush();
    }
  }

  async identify(userId: string, properties?: UserProperties): Promise<void> {
    if (!this.config.enabled) return;

    this.userId = userId;

    const promises = this.providers.map((provider) =>
      provider.identify(userId, properties),
    );

    await Promise.allSettled(promises);
  }

  async setUserProperties(properties: UserProperties): Promise<void> {
    if (!this.config.enabled) return;

    const promises = this.providers.map((provider) =>
      provider.setUserProperties(properties),
    );

    await Promise.allSettled(promises);
  }

  async reset(): Promise<void> {
    if (!this.config.enabled) return;

    this.userId = null;
    this.sessionId = this.generateSessionId();

    const promises = this.providers.map((provider) => provider.reset());
    await Promise.allSettled(promises);
  }

  private async flush(): Promise<void> {
    if (this.isProcessing || this.eventQueue.length === 0) return;

    this.isProcessing = true;
    this.lastFlush = Date.now();

    const events = [...this.eventQueue];
    this.eventQueue = [];

    try {
      for (const event of events) {
        const promises: Promise<void>[] = [];

        if (event.provider === "both" || event.provider === "amplitude") {
          const amplitudeProvider = this.providers.find((p) => p.name === "amplitude");
          if (amplitudeProvider?.isInitialized) {
            promises.push(amplitudeProvider.track(event.event_type, event.event_data));
          }
        }

        if (event.provider === "both" || event.provider === "mixpanel") {
          const mixpanelProvider = this.providers.find((p) => p.name === "mixpanel");
          if (mixpanelProvider?.isInitialized) {
            promises.push(mixpanelProvider.track(event.event_type, event.event_data));
          }
        }

        await Promise.allSettled(promises);
      }
    } catch (error) {
      console.error("Error flushing analytics events:", error);
      // Re-queue failed events for retry
      this.eventQueue.unshift(...events);
    } finally {
      this.isProcessing = false;
    }
  }

  // Public methods for specific event types
  async trackPageView(path: string, title?: string): Promise<void> {
    await this.track({
      event_type: "page_view",
      event_data: {
        path,
        title,
        url: window.location.href,
        referrer: document.referrer,
        timestamp: new Date().toISOString(),
      },
    });
  }

  async trackFeatureUsage(
    featureName: string,
    properties?: Record<string, unknown>,
  ): Promise<void> {
    await this.track({
      event_type: "feature_used",
      event_data: {
        feature_name: featureName,
        ...properties,
      },
    });
  }

  async trackFormInteraction(
    formName: string,
    action: "start" | "submit" | "abandon" | "validate",
    properties?: Record<string, unknown>,
  ): Promise<void> {
    await this.track({
      event_type: "form_interaction",
      event_data: {
        form_name: formName,
        action,
        ...properties,
      },
    });
  }

  async trackError(
    errorType: string,
    errorMessage: string,
    properties?: Record<string, unknown>,
  ): Promise<void> {
    await this.track({
      event_type: "error_occurred",
      event_data: {
        error_type: errorType,
        error_message: errorMessage,
        url: window.location.href,
        user_agent: navigator.userAgent,
        ...properties,
      },
    });
  }

  // Cleanup method
  destroy(): void {
    this.eventQueue = [];
    this.providers = [];
  }
}

// Global analytics instance
let analyticsClient: AnalyticsClient | null = null;

export function initializeAnalytics(config: AnalyticsConfig): AnalyticsClient {
  analyticsClient = new AnalyticsClient(config);
  return analyticsClient;
}

export function getAnalytics(): AnalyticsClient | null {
  return analyticsClient;
}

export function useAnalytics(): AnalyticsClient | null {
  return getAnalytics();
}
