import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import MarketStatusBar from "../components/MarketStatusBar.jsx";

// Mock the store so tests don't need a real API
vi.mock("../store", () => ({
  useStore: vi.fn(),
}));

import { useStore } from "../store";

describe("MarketStatusBar", () => {
  it("shows MARKET OPEN when market is open", () => {
    useStore.mockReturnValue({
      marketStatus: { is_open: true, next_expiry: "Thu 26 Apr", days_to_expiry: 3 },
      lastUpdated: null,
    });
    render(<MarketStatusBar />);
    expect(screen.getByText("MARKET OPEN")).toBeInTheDocument();
  });

  it("shows MARKET CLOSED when market is closed", () => {
    useStore.mockReturnValue({
      marketStatus: { is_open: false },
      lastUpdated: null,
    });
    render(<MarketStatusBar />);
    expect(screen.getByText("MARKET CLOSED")).toBeInTheDocument();
  });

  it("renders without crashing when marketStatus is null", () => {
    useStore.mockReturnValue({ marketStatus: null, lastUpdated: null });
    expect(() => render(<MarketStatusBar />)).not.toThrow();
  });
});
