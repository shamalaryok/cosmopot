<template>
  <div class="admin-layout">
    <nav class="admin-nav">
      <div class="admin-nav-header">
        <h2>Admin Panel</h2>
      </div>
      <ul class="admin-nav-links">
        <li>
          <router-link :to="{ name: 'admin-dashboard' }" class="nav-link">
            <span class="icon">📊</span>
            <span>Dashboard</span>
          </router-link>
        </li>
        <li>
          <router-link :to="{ name: 'admin-users' }" class="nav-link">
            <span class="icon">👥</span>
            <span>Users</span>
          </router-link>
        </li>
        <li>
          <router-link :to="{ name: 'admin-subscriptions' }" class="nav-link">
            <span class="icon">💳</span>
            <span>Subscriptions</span>
          </router-link>
        </li>
        <li>
          <router-link :to="{ name: 'admin-prompts' }" class="nav-link">
            <span class="icon">📝</span>
            <span>Prompts</span>
          </router-link>
        </li>
        <li>
          <router-link :to="{ name: 'admin-generations' }" class="nav-link">
            <span class="icon">🖼️</span>
            <span>Generations</span>
          </router-link>
        </li>
      </ul>
      <div class="admin-nav-footer">
        <router-link :to="{ name: 'dashboard' }" class="nav-link">
          <span class="icon">⬅️</span>
          <span>Back to App</span>
        </router-link>
      </div>
    </nav>
    <main class="admin-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.admin-layout {
  background: #f5f5f5;
  display: flex;
  min-height: 100vh;
}

.admin-nav {
  background: #1a1a1a;
  color: white;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  position: fixed;
  width: 250px;
}

.admin-nav-header {
  border-bottom: 1px solid #333;
  padding: 1.5rem;
}

.admin-nav-header h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
}

.admin-nav-links {
  flex: 1;
  list-style: none;
  margin: 0;
  padding: 1rem 0;
}

.admin-nav-links li {
  margin: 0;
}

.nav-link {
  align-items: center;
  color: #aaa;
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  text-decoration: none;
  transition: all 0.2s;
}

.nav-link:hover {
  background: #252525;
  color: white;
}

.nav-link.router-link-active {
  background: #333;
  border-left: 3px solid #4f46e5;
  color: white;
}

.icon {
  font-size: 1.25rem;
}

.admin-nav-footer {
  border-top: 1px solid #333;
  padding: 1rem 0;
}

.admin-content {
  flex: 1;
  margin-left: 250px;
  overflow-x: auto;
  padding: 2rem;
}
</style>
