import "@testing-library/jest-dom";

// Recharts uses ResizeObserver which jsdom doesn't provide
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
