<template>
  <DashboardShell>
    <template #header>
      <AppHeader />
    </template>

    <RouterView />

    <template #footer>
      <AppFooter />
    </template>
  </DashboardShell>

  <NotificationCenter />
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";

import AppFooter from "@/components/layout/AppFooter.vue";
import AppHeader from "@/components/layout/AppHeader.vue";
import DashboardShell from "@/components/layout/DashboardShell.vue";
import NotificationCenter from "@/components/ui/NotificationCenter.vue";
</script>
