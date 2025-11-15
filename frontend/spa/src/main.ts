import "./styles/tokens.css";
import "./styles/global.css";

import { createApp } from "vue";

import App from "./App.vue";
import { installAnalytics } from "./plugins/analytics";
import router from "./router";
import { pinia } from "./stores";

const app = createApp(App);

app.use(pinia);
app.use(router);

// Initialize analytics
installAnalytics(app, {
  config: {
    enabled: import.meta.env.VITE_ANALYTICS_ENABLED !== "false",
    amplitudeApiKey: import.meta.env.VITE_AMPLITUDE_API_KEY,
    mixpanelToken: import.meta.env.VITE_MIXPANEL_TOKEN,
    piiTrackingEnabled: import.meta.env.VITE_ANALYTICS_PII_TRACKING === "true",
    sandboxMode: import.meta.env.VITE_ANALYTICS_SANDBOX_MODE === "true",
    batchSize: parseInt(import.meta.env.VITE_ANALYTICS_BATCH_SIZE || "10"),
    flushInterval: parseInt(import.meta.env.VITE_ANALYTICS_FLUSH_INTERVAL || "5000"),
  },
  autoTrack: {
    pageViews: true,
    clicks: true,
    formSubmissions: true,
    errors: true,
  },
});

app.mount("#app");
