// terminalCreationTracker 的单元测试（vitest）。
//
// 覆盖核心行为：本设备发起创建后 terminal_created 回包应切换（shouldSwitch=true）；
// 他端共享的 terminal_created（未发起创建）不应切换；超时后标志自动复位，避免残留
// 导致后续他端共享终端被误切换。
import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";
import { createTerminalCreationTracker } from "./terminalCreationTracker.js";

describe("createTerminalCreationTracker", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  test("本设备发起创建后，terminal_created 回包应切换", () => {
    const tracker = createTerminalCreationTracker();
    tracker.mark();
    expect(tracker.shouldSwitch()).toBe(true);
  });

  test("他端共享的 terminal_created（未发起创建）不应切换", () => {
    const tracker = createTerminalCreationTracker();
    expect(tracker.shouldSwitch()).toBe(false);
  });

  test("shouldSwitch 消费后复位，后续共享终端不再切换", () => {
    const tracker = createTerminalCreationTracker();
    tracker.mark();
    expect(tracker.shouldSwitch()).toBe(true);
    // 第二次（模拟另一个共享终端到达）不应再切换
    expect(tracker.shouldSwitch()).toBe(false);
  });

  test("超时后标志自动复位，避免残留导致误切换", () => {
    const tracker = createTerminalCreationTracker(10000);
    tracker.mark();
    expect(tracker.isPending()).toBe(true);
    vi.advanceTimersByTime(10001);
    expect(tracker.isPending()).toBe(false);
    expect(tracker.shouldSwitch()).toBe(false);
  });

  test("isPending 反映当前是否等待回包", () => {
    const tracker = createTerminalCreationTracker();
    expect(tracker.isPending()).toBe(false);
    tracker.mark();
    expect(tracker.isPending()).toBe(true);
  });
});
