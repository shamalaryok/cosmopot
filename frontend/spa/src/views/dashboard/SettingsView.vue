<template>
  <section class="settings-view">
    <header class="settings-view__header">
      <h1>Workspace settings</h1>
      <p>
        Control theming, notifications, and credential rotation from a single surface.
      </p>
    </header>

    <div class="settings-view__panel">
      <h2>Theme</h2>
      <div class="settings-view__options" role="group" aria-label="Theme selection">
        <label class="settings-view__option">
          <input v-model="theme" type="radio" name="theme" value="system" />
          <span>System</span>
        </label>
        <label class="settings-view__option">
          <input v-model="theme" type="radio" name="theme" value="light" />
          <span>Light</span>
        </label>
        <label class="settings-view__option">
          <input v-model="theme" type="radio" name="theme" value="dark" />
          <span>Dark</span>
        </label>
      </div>
    </div>

    <div class="settings-view__panel">
      <h2>Notifications</h2>
      <p class="settings-view__hint">
        Choose delivery channels when rate limits or errors occur.
      </p>
      <label class="settings-view__toggle">
        <input v-model="emailAlerts" type="checkbox" />
        <span>Email alerts</span>
      </label>
      <label class="settings-view__toggle">
        <input v-model="slackAlerts" type="checkbox" />
        <span>Slack alerts</span>
      </label>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watchEffect } from "vue";

const theme = ref("system");
const emailAlerts = ref(true);
const slackAlerts = ref(false);

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
});
</script>

<style scoped>
.settings-view {
  display: grid;
  gap: var(--space-6);
}

.settings-view__header {
  display: grid;
  gap: var(--space-2);
}

.settings-view__panel {
  background: var(--surface-base);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  display: grid;
  gap: var(--space-4);
  padding: var(--space-5);
}

.settings-view__options {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.settings-view__option {
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  display: inline-flex;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
}

.settings-view__option input {
  margin: 0;
}

.settings-view__hint {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.settings-view__toggle {
  align-items: center;
  display: inline-flex;
  font-weight: 500;
  gap: var(--space-2);
}
</style>
