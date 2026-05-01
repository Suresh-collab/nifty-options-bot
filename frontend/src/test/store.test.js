import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "../store/index.js";
import { act } from "@testing-library/react";

describe("Zustand store — initial state", () => {
  beforeEach(() => {
    // Reset store to defaults before each test
    act(() => {
      useStore.setState({
        ticker: "NIFTY",
        signalData: null,
        signalLoading: false,
        signalError: null,
        lastUpdated: null,
      });
    });
  });

  it("defaults ticker to NIFTY", () => {
    expect(useStore.getState().ticker).toBe("NIFTY");
  });

  it("setTicker updates ticker and clears signal", () => {
    act(() => useStore.getState().setTicker("BANKNIFTY"));
    const state = useStore.getState();
    expect(state.ticker).toBe("BANKNIFTY");
    expect(state.signalData).toBeNull();
  });

  it("signalLoading starts false", () => {
    expect(useStore.getState().signalLoading).toBe(false);
  });
});
