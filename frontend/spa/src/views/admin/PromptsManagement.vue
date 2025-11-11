<template>
  <div class="management-view">
    <div class="header">
      <h1>Prompt Management</h1>
      <div class="header-actions">
        <button class="btn-secondary" @click="downloadExport('csv')">Export CSV</button>
        <button class="btn-primary" @click="openCreateModal">Create Prompt</button>
      </div>
    </div>

    <div class="filters">
      <input
        v-model="filters.search"
        placeholder="Search prompts..."
        class="search-input"
        @input="debouncedFetch"
      />
      <select v-model="filters.category" class="filter-select" @change="fetchPrompts">
        <option value="">All Categories</option>
        <option value="generic">Generic</option>
        <option value="art">Art</option>
        <option value="photography">Photography</option>
      </select>
      <select v-model="filters.is_active" class="filter-select" @change="fetchPrompts">
        <option :value="undefined">All Status</option>
        <option :value="true">Active</option>
        <option :value="false">Inactive</option>
      </select>
    </div>

    <div v-if="loading" class="loading">Loading prompts...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <div v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Slug</th>
            <th>Name</th>
            <th>Category</th>
            <th>Version</th>
            <th>Status</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="prompt in prompts" :key="prompt.id">
            <td>{{ prompt.id }}</td>
            <td>{{ prompt.slug }}</td>
            <td>{{ prompt.name }}</td>
            <td>
              <span class="badge badge-user">{{ prompt.category }}</span>
            </td>
            <td>v{{ prompt.version }}</td>
            <td>
              <span
                class="status-badge"
                :class="prompt.is_active ? 'active' : 'inactive'"
              >
                {{ prompt.is_active ? "Active" : "Inactive" }}
              </span>
            </td>
            <td>{{ formatDate(prompt.created_at) }}</td>
            <td class="actions">
              <button class="btn-icon" @click="editPrompt(prompt)">✏️</button>
              <button class="btn-icon" @click="deletePrompt(prompt)">🗑️</button>
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
import type { AdminPrompt } from "@/services/adminService";

const prompts = ref<AdminPrompt[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const filters = reactive({
  search: "",
  category: "" as string | undefined,
  is_active: undefined as boolean | undefined,
  page: 1,
  page_size: 20,
});

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0,
});

let debounceTimer: number | undefined;

function debouncedFetch() {
  clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => {
    filters.page = 1;
    fetchPrompts();
  }, 300);
}

async function fetchPrompts() {
  loading.value = true;
  error.value = null;
  try {
    const response = await adminService.listPrompts(filters);
    prompts.value = response.items;
    Object.assign(pagination, response);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to fetch prompts";
  } finally {
    loading.value = false;
  }
}

function goToPage(page: number) {
  filters.page = page;
  fetchPrompts();
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString();
}

async function downloadExport(format: "csv" | "json") {
  try {
    const blob = await adminService.exportPrompts(format);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `prompts_export.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Export failed";
  }
}

function openCreateModal() {
  const slug = prompt("Enter slug:");
  const name = prompt("Enter name:");
  if (slug && name) {
    createPrompt(slug, name);
  }
}

async function createPrompt(slug: string, name: string) {
  try {
    await adminService.createPrompt({ slug, name });
    await fetchPrompts();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to create prompt";
  }
}

function editPrompt(prompt: AdminPrompt) {
  const newName = prompt("Enter new name:", prompt.name);
  if (newName) {
    updatePrompt(prompt.id, { name: newName });
  }
}

async function updatePrompt(promptId: number, payload: adminService.AdminPromptUpdate) {
  try {
    await adminService.updatePrompt(promptId, payload);
    await fetchPrompts();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to update prompt";
  }
}

async function deletePrompt(prompt: AdminPrompt) {
  if (confirm(`Delete prompt ${prompt.name}?`)) {
    try {
      await adminService.deletePrompt(prompt.id);
      await fetchPrompts();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to delete prompt";
    }
  }
}

onMounted(() => {
  fetchPrompts();
});
</script>

<style scoped>
@import url("./management-styles.css");
</style>
