<template>
  <div class="management-view">
    <div class="header">
      <h1>Subscription Management</h1>
      <div class="header-actions">
        <button class="btn-secondary" @click="downloadExport('csv')">Export CSV</button>
        <button class="btn-secondary" @click="downloadExport('json')">
          Export JSON
        </button>
      </div>
    </div>

    <div class="filters">
      <select v-model="filters.tier" class="filter-select" @change="fetchSubscriptions">
        <option value="">All Tiers</option>
        <option value="free">Free</option>
        <option value="pro">Pro</option>
        <option value="enterprise">Enterprise</option>
      </select>
      <select
        v-model="filters.status"
        class="filter-select"
        @change="fetchSubscriptions"
      >
        <option value="">All Status</option>
        <option value="active">Active</option>
        <option value="canceled">Canceled</option>
        <option value="past_due">Past Due</option>
      </select>
    </div>

    <div v-if="loading" class="loading">Loading subscriptions...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <div v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>User ID</th>
            <th>Tier</th>
            <th>Status</th>
            <th>Quota Used / Limit</th>
            <th>Auto Renew</th>
            <th>Period End</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sub in subscriptions" :key="sub.id">
            <td>{{ sub.id }}</td>
            <td>{{ sub.user_id }}</td>
            <td>
              <span class="badge badge-user">{{ sub.tier }}</span>
            </td>
            <td>
              <span class="status-badge" :class="sub.status">
                {{ sub.status }}
              </span>
            </td>
            <td>{{ sub.quota_used }} / {{ sub.quota_limit }}</td>
            <td>{{ sub.auto_renew ? "Yes" : "No" }}</td>
            <td>{{ formatDate(sub.current_period_end) }}</td>
            <td class="actions">
              <button class="btn-icon" @click="editSubscription(sub)">✏️</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="pagination">
        <button
          :disabled="pagination.page <= 1"
          class="btn-page"
          @click="goToPage(pagination.page - 1)"
        >
          Previous
        </button>
        <span class="page-info">
          Page {{ pagination.page }} of {{ pagination.total_pages }}
        </span>
        <button
          :disabled="pagination.page >= pagination.total_pages"
          class="btn-page"
          @click="goToPage(pagination.page + 1)"
        >
          Next
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import * as adminService from "@/services/adminService";
import type { AdminSubscription } from "@/services/adminService";

const subscriptions = ref<AdminSubscription[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const filters = reactive({
  tier: "" as string | undefined,
  status: "" as string | undefined,
  page: 1,
  page_size: 20,
});

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0,
});

async function fetchSubscriptions() {
  loading.value = true;
  error.value = null;
  try {
    const response = await adminService.listSubscriptions(filters);
    subscriptions.value = response.items;
    Object.assign(pagination, response);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to fetch subscriptions";
  } finally {
    loading.value = false;
  }
}

function goToPage(page: number) {
  filters.page = page;
  fetchSubscriptions();
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString();
}

async function downloadExport(format: "csv" | "json") {
  try {
    const blob = await adminService.exportSubscriptions(format);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `subscriptions_export.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Export failed";
  }
}

function editSubscription(sub: AdminSubscription) {
  const newStatus = prompt("Enter new status (active/canceled):", sub.status);
  if (newStatus) {
    updateSubscription(sub.id, { status: newStatus });
  }
}

async function updateSubscription(
  subId: number,
  payload: adminService.AdminSubscriptionUpdate,
) {
  try {
    await adminService.updateSubscription(subId, payload);
    await fetchSubscriptions();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to update subscription";
  }
}

onMounted(() => {
  fetchSubscriptions();
});
</script>

<style scoped>
@import url("./management-styles.css");
</style>
