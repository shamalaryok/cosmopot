import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as adminService from "@/services/adminService";
import { useAdminStore } from "@/stores/admin";

vi.mock("@/services/adminService");

describe("Admin Store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("should initialize with null analytics", () => {
    const store = useAdminStore();
    expect(store.analytics).toBeNull();
    expect(store.loading).toBe(false);
    expect(store.error).toBeNull();
  });

  it("should fetch analytics successfully", async () => {
    const mockAnalytics = {
      total_users: 100,
      active_users: 80,
      total_subscriptions: 50,
      active_subscriptions: 40,
      total_generations: 1000,
      generations_today: 50,
      generations_this_week: 300,
      generations_this_month: 800,
      failed_generations: 10,
      revenue_total: "10000.00",
      revenue_this_month: "2000.00",
    };

    vi.mocked(adminService.getAnalytics).mockResolvedValue(mockAnalytics);

    const store = useAdminStore();
    await store.fetchAnalytics();

    expect(store.analytics).toEqual(mockAnalytics);
    expect(store.loading).toBe(false);
    expect(store.error).toBeNull();
  });

  it("should handle fetch analytics error", async () => {
    const errorMessage = "Failed to fetch";
    vi.mocked(adminService.getAnalytics).mockRejectedValue(new Error(errorMessage));

    const store = useAdminStore();

    await expect(store.fetchAnalytics()).rejects.toThrow(errorMessage);
    expect(store.error).toBe(errorMessage);
    expect(store.analytics).toBeNull();
  });

  it("should clear analytics", () => {
    const store = useAdminStore();
    store.analytics = {
      total_users: 100,
      active_users: 80,
      total_subscriptions: 50,
      active_subscriptions: 40,
      total_generations: 1000,
      generations_today: 50,
      generations_this_week: 300,
      generations_this_month: 800,
      failed_generations: 10,
      revenue_total: "10000.00",
      revenue_this_month: "2000.00",
    };
    store.error = "Some error";

    store.clearAnalytics();

    expect(store.analytics).toBeNull();
    expect(store.error).toBeNull();
  });
});
