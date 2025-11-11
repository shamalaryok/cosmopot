<template>
  <div class="management-view">
    <div class="header">
      <h1>Generation Management & Moderation</h1>
      <div class="header-actions">
        <button class="btn-secondary" @click="downloadExport('csv')">Export CSV</button>
      </div>
    </div>

    <div class="filters">
      <select v-model="filters.status" class="filter-select" @change="fetchGenerations">
        <option value="">All Status</option>
        <option value="pending">Pending</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
      </select>
    </div>

    <div v-if="loading" class="loading">Loading generations...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <div v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>User ID</th>
            <th>Prompt ID</th>
            <th>Status</th>
            <th>Source</th>
            <th>Result</th>
            <th>Created</th>
            <th>Moderation</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="gen in generations" :key="gen.id">
            <td>{{ gen.id }}</td>
            <td>{{ gen.user_id }}</td>
            <td>{{ gen.prompt_id }}</td>
            <td>
              <span class="status-badge" :class="gen.status">
                {{ gen.status }}
              </span>
            </td>
            <td>{{ gen.source }}</td>
            <td>
              <a
                v-if="gen.result_asset_url"
                :href="gen.result_asset_url"
                target="_blank"
                class="result-link"
              >
                View
              </a>
              <span v-else>-</span>
            </td>
            <td>{{ formatDate(gen.created_at) }}</td>
            <td class="actions">
              <button
                class="btn-icon"
                title="Approve"
                @click="moderateGeneration(gen, 'approve')"
              >
                ✅
              </button>
              <button
                class="btn-icon"
                title="Reject"
                @click="moderateGeneration(gen, 'reject')"
              >
                ❌
              </button>
              <button
                class="btn-icon"
                title="Flag"
                @click="moderateGeneration(gen, 'flag')"
              >
                🚩
              </button>
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
import type { AdminGeneration, AdminModerationAction } from "@/services/adminService";

const generations = ref<AdminGeneration[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const filters = reactive({
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

async function fetchGenerations() {
  loading.value = true;
  error.value = null;
  try {
    const response = await adminService.listGenerations(filters);
    generations.value = response.items;
    Object.assign(pagination, response);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to fetch generations";
  } finally {
    loading.value = false;
  }
}

function goToPage(page: number) {
  filters.page = page;
  fetchGenerations();
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString();
}

async function downloadExport(format: "csv" | "json") {
  try {
    const blob = await adminService.exportGenerations(format);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `generations_export.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Export failed";
  }
}

async function moderateGeneration(
  gen: AdminGeneration,
  action: "approve" | "reject" | "flag",
) {
  let reason: string | null = null;

  if (action === "reject") {
    reason = prompt("Enter rejection reason:");
    if (!reason) return;
  }

  const payload: AdminModerationAction = {
    action,
    reason,
  };

  try {
    await adminService.moderateGeneration(gen.id, payload);
    await fetchGenerations();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Moderation action failed";
  }
}

onMounted(() => {
  fetchGenerations();
});
</script>

<style scoped>
@import url("./management-styles.css");

.result-link {
  color: #4f46e5;
  font-weight: 500;
  text-decoration: none;
}

.result-link:hover {
  text-decoration: underline;
}
</style>
