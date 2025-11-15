<template>
  <div class="app-footer">
    <p>&copy; {{ currentYear }} Platform. Crafted for resilient deployments.</p>
    <nav class="app-footer__links" aria-label="Secondary navigation">
      <a
        class="app-footer__link"
        href="https://example.com/docs"
        target="_blank"
        rel="noreferrer noopener"
        >Docs</a
      >
      <a
        class="app-footer__link"
        href="https://example.com/status"
        target="_blank"
        rel="noreferrer noopener"
        >Status</a
      >
      <a
        class="app-footer__link"
        href="https://example.com/support"
        target="_blank"
        rel="noreferrer noopener"
        >Support</a
      >
    </nav>
  </div>
</template>

<script setup lang="ts">
const currentYear = new Date().getFullYear();
</script>

<style scoped>
.app-footer {
  align-items: flex-start;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  font-size: 0.9rem;
  gap: var(--space-3);
  margin: 0 auto;
  max-width: var(--layout-max-width);
}

.app-footer__links {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.app-footer__link {
  color: inherit;
  text-decoration: none;
  transition: color 160ms ease;
}

.app-footer__link:hover {
  color: var(--text-primary);
}

@media (width >= 768px) {
  .app-footer {
    align-items: center;
    flex-direction: row;
    justify-content: space-between;
  }
}
</style>
