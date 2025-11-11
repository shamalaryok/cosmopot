import type { RouteRecordRaw } from "vue-router";

export const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "dashboard",
    component: () => import("@/views/dashboard/DashboardView.vue"),
    meta: {
      requiresAuth: true,
      title: "Dashboard",
    },
  },
  {
    path: "/settings",
    name: "settings",
    component: () => import("@/views/dashboard/SettingsView.vue"),
    meta: {
      requiresAuth: true,
      title: "Settings",
    },
  },
  {
    path: "/admin",
    component: () => import("@/views/admin/AdminLayout.vue"),
    meta: {
      requiresAuth: true,
      requiresAdmin: true,
    },
    children: [
      {
        path: "",
        name: "admin-dashboard",
        component: () => import("@/views/admin/AdminDashboard.vue"),
        meta: {
          title: "Admin Dashboard",
        },
      },
      {
        path: "users",
        name: "admin-users",
        component: () => import("@/views/admin/UsersManagement.vue"),
        meta: {
          title: "User Management",
        },
      },
      {
        path: "subscriptions",
        name: "admin-subscriptions",
        component: () => import("@/views/admin/SubscriptionsManagement.vue"),
        meta: {
          title: "Subscription Management",
        },
      },
      {
        path: "prompts",
        name: "admin-prompts",
        component: () => import("@/views/admin/PromptsManagement.vue"),
        meta: {
          title: "Prompt Management",
        },
      },
      {
        path: "generations",
        name: "admin-generations",
        component: () => import("@/views/admin/GenerationsManagement.vue"),
        meta: {
          title: "Generation Management",
        },
      },
    ],
  },
  {
    path: "/auth/login",
    name: "login",
    component: () => import("@/views/auth/LoginView.vue"),
    meta: {
      guestOnly: true,
      title: "Sign In",
    },
  },
  {
    path: "/:pathMatch(.*)*",
    name: "not-found",
    component: () => import("@/views/errors/NotFoundView.vue"),
    meta: {
      title: "Page not found",
    },
  },
];

export default routes;
