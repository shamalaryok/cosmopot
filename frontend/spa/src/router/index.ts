import { createRouter, createWebHistory } from "vue-router";

import routes from "./routes";

import { pinia } from "@/stores";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior() {
    return { left: 0, top: 0 };
  },
});

const appName = import.meta.env.VITE_APP_NAME ?? "Platform";

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia);

  if (to.meta?.title) {
    document.title = `${to.meta.title} · ${appName}`;
  }

  if (to.meta?.requiresAuth && !auth.isAuthenticated) {
    return {
      name: "login",
      query: { redirect: to.fullPath },
    };
  }

  if (to.meta?.requiresAdmin) {
    if (!auth.isAuthenticated) {
      return {
        name: "login",
        query: { redirect: to.fullPath },
      };
    }
    if (auth.user?.role !== "admin") {
      return { name: "dashboard" };
    }
  }

  if (to.meta?.guestOnly && auth.isAuthenticated) {
    return { name: "dashboard" };
  }

  return true;
});

export default router;
