<template>
  <div class="management-view">
    <div class="header">
      <h1>User Management</h1>
      <div class="header-actions">
        <button class="btn-secondary" @click="downloadExport('csv')">Export CSV</button>
        <button class="btn-secondary" @click="downloadExport('json')">
          Export JSON
        </button>
        <button class="btn-primary" @click="openCreateModal">Create User</button>
      </div>
    </div>

    <div class="filters">
      <input
        v-model="filters.search"
        placeholder="Search by email..."
        class="search-input"
        @input="debouncedFetch"
      />
      <select v-model="filters.role" class="filter-select" @change="fetchUsers">
        <option value="">All Roles</option>
        <option value="admin">Admin</option>
        <option value="user">User</option>
      </select>
      <select v-model="filters.is_active" class="filter-select" @change="fetchUsers">
        <option :value="undefined">All Status</option>
        <option :value="true">Active</option>
        <option :value="false">Inactive</option>
      </select>
    </div>

    <div v-if="loading" class="loading">Loading users...</div>

    <div v-else-if="error" class="error">{{ error }}</div>

    <div v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Email</th>
            <th>Role</th>
            <th>Balance</th>
            <th>Status</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td>{{ user.email }}</td>
            <td>
              <span class="badge" :class="`badge-${user.role}`">{{ user.role }}</span>
            </td>
            <td>${{ parseFloat(user.balance).toFixed(2) }}</td>
            <td>
              <span
                class="status-badge"
                :class="user.is_active ? 'active' : 'inactive'"
              >
                {{ user.is_active ? "Active" : "Inactive" }}
              </span>
            </td>
            <td>{{ formatDate(user.created_at) }}</td>
            <td class="actions">
              <button class="btn-icon" @click="editUser(user)">✏️</button>
              <button class="btn-icon" @click="deleteUser(user)">🗑️</button>
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
          Page {{ pagination.page }} of {{ pagination.total_pages }} ({{
            pagination.total
          }}
          total)
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
import type { AdminUser, PaginatedResponse } from "@/services/adminService";

const users = ref<AdminUser[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const filters = reactive({
  search: "",
  role: "" as string | undefined,
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
    fetchUsers();
  }, 300);
}

async function fetchUsers() {
  loading.value = true;
  error.value = null;
  try {
    const response: PaginatedResponse<AdminUser> =
      await adminService.listUsers(filters);
    users.value = response.items;
    pagination.page = response.page;
    pagination.page_size = response.page_size;
    pagination.total = response.total;
    pagination.total_pages = response.total_pages;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to fetch users";
  } finally {
    loading.value = false;
  }
}

function goToPage(page: number) {
  filters.page = page;
  fetchUsers();
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString();
}

async function downloadExport(format: "csv" | "json") {
  try {
    const blob = await adminService.exportUsers(format);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `users_export.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Export failed";
  }
}

function openCreateModal() {
  const email = prompt("Enter email:");
  const password = prompt("Enter password:");
  if (email && password) {
    createUser(email, password);
  }
}

async function createUser(email: string, password: string) {
  try {
    await adminService.createUser({ email, password });
    await fetchUsers();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to create user";
  }
}

function editUser(user: AdminUser) {
  const newRole = prompt("Enter new role (admin/user):", user.role);
  if (newRole && (newRole === "admin" || newRole === "user")) {
    updateUser(user.id, { role: newRole });
  }
}

async function updateUser(userId: number, payload: adminService.AdminUserUpdate) {
  try {
    await adminService.updateUser(userId, payload);
    await fetchUsers();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to update user";
  }
}

async function deleteUser(user: AdminUser) {
  if (confirm(`Delete user ${user.email}?`)) {
    try {
      await adminService.deleteUser(user.id);
      await fetchUsers();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to delete user";
    }
  }
}

onMounted(() => {
  fetchUsers();
});
</script>

<style scoped>
@import url("./management-styles.css");
</style>
