<template>
  <div class="dashboard-shell">
    <header class="dashboard-shell__header">
      <slot name="header" />
    </header>

    <aside
      v-if="$slots.sidebar"
      class="dashboard-shell__sidebar"
      aria-label="Sidebar navigation"
    >
      <slot name="sidebar" />
    </aside>

    <main class="dashboard-shell__main" aria-live="polite">
      <slot />
    </main>

    <footer class="dashboard-shell__footer">
      <slot name="footer" />
    </footer>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.dashboard-shell {
  background: var(--surface-subtle);
  color: var(--text-primary);
  display: grid;
  grid-template-areas:
    "header"
    "main"
    "footer";
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}

.dashboard-shell__header {
  backdrop-filter: blur(8px);
  background: var(--surface-elevated);
  border-bottom: 1px solid var(--border-subtle);
  grid-area: header;
  position: sticky;
  top: 0;
  z-index: 10;
}

.dashboard-shell__sidebar {
  background: var(--surface-base);
  border-right: 1px solid var(--border-subtle);
  grid-area: sidebar;
  padding: var(--space-6) var(--space-4);
}

.dashboard-shell__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  grid-area: main;
  padding: var(--space-6) clamp(var(--space-4), 5vw, var(--space-10));
}

.dashboard-shell__footer {
  background: var(--surface-elevated);
  border-top: 1px solid var(--border-subtle);
  grid-area: footer;
  padding: var(--space-4) clamp(var(--space-4), 5vw, var(--space-10));
}

@media (width >= 992px) {
  .dashboard-shell {
    grid-template-areas:
      "sidebar header"
      "sidebar main"
      "sidebar footer";
    grid-template-columns: 260px 1fr;
  }

  .dashboard-shell__header {
    position: sticky;
    top: 0;
  }

  .dashboard-shell__sidebar {
    bottom: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    position: sticky;
    top: 0;
  }
}
</style>
