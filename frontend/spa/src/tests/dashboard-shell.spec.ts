import { render, screen } from "@testing-library/vue";
import { describe, expect, it } from "vitest";

import DashboardShell from "@/components/layout/DashboardShell.vue";

describe("DashboardShell", () => {
  it("renders header, main content, and footer slots", () => {
    render(DashboardShell, {
      slots: {
        header: "Header content",
        default: "Main content",
        footer: "Footer content",
      },
    });

    expect(screen.getByText("Header content")).toBeInTheDocument();
    expect(screen.getByText("Main content")).toBeInTheDocument();
    expect(screen.getByText("Footer content")).toBeInTheDocument();
  });
});
