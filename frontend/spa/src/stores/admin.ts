import { defineStore } from "pinia";

import * as adminService from "@/services/adminService";
import type { AdminAnalytics } from "@/services/adminService";

interface AdminState {
  analytics: AdminAnalytics | null;
  loading: boolean;
  error: string | null;
}

export const useAdminStore = defineStore("admin", {
  state: (): AdminState => ({
    analytics: null,
    loading: false,
    error: null,
  }),
  actions: {
    async fetchAnalytics() {
      this.loading = true;
      this.error = null;
      try {
        this.analytics = await adminService.getAnalytics();
      } catch (error) {
        this.error =
          error instanceof Error ? error.message : "Failed to fetch analytics";
        throw error;
      } finally {
        this.loading = false;
      }
    },
    clearAnalytics() {
      this.analytics = null;
      this.error = null;
    },
  },
});
