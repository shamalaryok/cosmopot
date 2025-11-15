<template>
  <div class="admin-dashboard">
    <h1>Admin Dashboard</h1>

    <div v-if="loading" class="loading">Loading analytics...</div>

    <div v-else-if="error" class="error">
      <p>Failed to load analytics: {{ error }}</p>
      <button class="btn-retry" @click="loadAnalytics">Retry</button>
    </div>

    <div v-else-if="analytics" class="dashboard-grid">
      <div class="stat-card">
        <div class="stat-icon">👥</div>
        <div class="stat-content">
          <h3>Total Users</h3>
          <p class="stat-value">{{ analytics.total_users }}</p>
          <p class="stat-meta">{{ analytics.active_users }} active</p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">💳</div>
        <div class="stat-content">
          <h3>Subscriptions</h3>
          <p class="stat-value">{{ analytics.total_subscriptions }}</p>
          <p class="stat-meta">{{ analytics.active_subscriptions }} active</p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">🖼️</div>
        <div class="stat-content">
          <h3>Total Generations</h3>
          <p class="stat-value">{{ analytics.total_generations }}</p>
          <p class="stat-meta">{{ analytics.failed_generations }} failed</p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">💰</div>
        <div class="stat-content">
          <h3>Revenue</h3>
          <p class="stat-value">
            ${{ parseFloat(analytics.revenue_total).toFixed(2) }}
          </p>
          <p class="stat-meta">
            ${{ parseFloat(analytics.revenue_this_month).toFixed(2) }} this month
          </p>
        </div>
      </div>

      <div class="chart-card">
        <h3>Generations Timeline</h3>
        <div class="timeline-stats">
          <div class="timeline-item">
            <span class="timeline-label">Today</span>
            <span class="timeline-value">{{ analytics.generations_today }}</span>
          </div>
          <div class="timeline-item">
            <span class="timeline-label">This Week</span>
            <span class="timeline-value">{{ analytics.generations_this_week }}</span>
          </div>
          <div class="timeline-item">
            <span class="timeline-label">This Month</span>
            <span class="timeline-value">{{ analytics.generations_this_month }}</span>
          </div>
        </div>
      </div>

      <div class="chart-card">
        <h3>Quick Stats</h3>
        <div class="quick-stats">
          <div class="quick-stat">
            <span class="quick-stat-label">User Activity Rate</span>
            <span class="quick-stat-value"> {{ userActivityRate }}% </span>
          </div>
          <div class="quick-stat">
            <span class="quick-stat-label">Subscription Rate</span>
            <span class="quick-stat-value"> {{ subscriptionRate }}% </span>
          </div>
          <div class="quick-stat">
            <span class="quick-stat-label">Generation Success Rate</span>
            <span class="quick-stat-value"> {{ generationSuccessRate }}% </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import * as adminService from "@/services/adminService";
import type { AdminAnalytics } from "@/services/adminService";

const analytics = ref<AdminAnalytics | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const userActivityRate = computed(() => {
  if (!analytics.value || analytics.value.total_users === 0) return 0;
  return ((analytics.value.active_users / analytics.value.total_users) * 100).toFixed(
    1,
  );
});

const subscriptionRate = computed(() => {
  if (!analytics.value || analytics.value.total_users === 0) return 0;
  return (
    (analytics.value.active_subscriptions / analytics.value.total_users) *
    100
  ).toFixed(1);
});

const generationSuccessRate = computed(() => {
  if (!analytics.value || analytics.value.total_generations === 0) return 0;
  const successful =
    analytics.value.total_generations - analytics.value.failed_generations;
  return ((successful / analytics.value.total_generations) * 100).toFixed(1);
});

async function loadAnalytics() {
  loading.value = true;
  error.value = null;
  try {
    analytics.value = await adminService.getAnalytics();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Unknown error";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadAnalytics();
});
</script>

<style scoped>
.admin-dashboard {
  max-width: 1400px;
}

h1 {
  color: #1a1a1a;
  margin-bottom: 2rem;
}

.loading,
.error {
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 10%);
  padding: 2rem;
  text-align: center;
}

.btn-retry {
  background: #4f46e5;
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 1rem;
  margin-top: 1rem;
  padding: 0.5rem 1rem;
}

.btn-retry:hover {
  background: #4338ca;
}

.dashboard-grid {
  display: grid;
  gap: 1.5rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.stat-card {
  align-items: center;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 10%);
  display: flex;
  gap: 1rem;
  padding: 1.5rem;
  transition: transform 0.2s;
}

.stat-card:hover {
  box-shadow: 0 4px 6px rgb(0 0 0 / 10%);
  transform: translateY(-2px);
}

.stat-icon {
  font-size: 2.5rem;
}

.stat-content h3 {
  color: #6b7280;
  font-size: 0.875rem;
  font-weight: 500;
  margin: 0 0 0.5rem;
}

.stat-value {
  color: #1a1a1a;
  font-size: 2rem;
  font-weight: 700;
  margin: 0;
}

.stat-meta {
  color: #9ca3af;
  font-size: 0.875rem;
  margin: 0.25rem 0 0;
}

.chart-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 10%);
  grid-column: span 2;
  padding: 1.5rem;
}

.chart-card h3 {
  color: #1a1a1a;
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0 0 1rem;
}

.timeline-stats {
  display: flex;
  gap: 1rem;
  justify-content: space-around;
}

.timeline-item {
  align-items: center;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.timeline-label {
  color: #6b7280;
  font-size: 0.875rem;
}

.timeline-value {
  color: #4f46e5;
  font-size: 1.75rem;
  font-weight: 700;
}

.quick-stats {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.quick-stat {
  align-items: center;
  background: #f9fafb;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  padding: 0.75rem;
}

.quick-stat-label {
  color: #6b7280;
  font-size: 0.875rem;
}

.quick-stat-value {
  color: #10b981;
  font-size: 1.25rem;
  font-weight: 600;
}
</style>
