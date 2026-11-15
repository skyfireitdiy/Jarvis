// TopologyOverlay 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/TopologyOverlay.test.js   # 只跑本文件
//   npm run test:vitest                                     # 跑全部 vitest 用例
//
// 说明：本组件是纯前端渲染（自绘 SVG 拓扑图），不依赖后端接口；
// 接入端节点（浏览器扩展 / 后台服务）由 props.extensionSessions / props.daemonSessions 注入。
// 本测试聚焦「后台服务（daemon）节点右键菜单 → 创建终端」这条新增链路。
import { describe, test, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import TopologyOverlay from "./TopologyOverlay.vue";

const baseProps = {
  visible: true,
  nodes: [],
  agents: [],
  getStatusClass: () => "running",
  nodeDisplayNames: {},
  extensionSessions: [],
  daemonSessions: [
    {
      session_id: "sess-1",
      node_id: "daemon-host-123",
      name: "本机后台服务",
      platform: "linux",
      daemon_version: "v5.0.5",
    },
  ],
};

function mountTopology(props = {}) {
  return mount(TopologyOverlay, { props: { ...baseProps, ...props } });
}

// 在渲染出的 SVG 中定位「后台服务（daemon）」节点 <g>
function findDaemonNode(wrapper) {
  const locals = wrapper.findAll("g.topo-node.is-local");
  return locals.find((g) => g.find("title").text().includes("后台服务")) || null;
}

describe("TopologyOverlay daemon 节点右键菜单", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  test("daemon 会话渲染为 local 节点（后台服务）", () => {
    const wrapper = mountTopology();
    const node = findDaemonNode(wrapper);
    expect(node).not.toBeNull();
    // 节点 <g> 上绑定了右键处理（contextmenu.prevent.stop）
    expect(node.attributes("class")).toContain("is-local");
    // 节点 title 展示后台服务信息（会话名 + 平台 + 版本）
    expect(node.find("title").text()).toContain("本机后台服务");
  });

  test("右键 daemon 节点弹出「创建终端」菜单", async () => {
    const wrapper = mountTopology();
    const node = findDaemonNode(wrapper);
    await node.trigger("contextmenu", { clientX: 200, clientY: 300 });

    const menu = wrapper.find(".file-tree-context-menu");
    expect(menu.exists()).toBe(true);
    const item = menu.find(".file-tree-context-item");
    expect(item.exists()).toBe(true);
    expect(item.text()).toContain("创建终端");
  });

  test("点击「创建终端」emit daemon-context-menu 并携带 nodeId", async () => {
    const wrapper = mountTopology();
    const node = findDaemonNode(wrapper);
    await node.trigger("contextmenu", { clientX: 200, clientY: 300 });

    await wrapper.find(".file-tree-context-item").trigger("click");
    const emitted = wrapper.emitted("daemon-context-menu");
    expect(emitted).toBeTruthy();
    expect(emitted[0][0]).toBe("daemon-host-123");
    // 点击后菜单关闭
    expect(wrapper.find(".file-tree-context-menu").exists()).toBe(false);
  });

  test("浏览器扩展节点右键不弹菜单", async () => {
    const wrapper = mountTopology({
      extensionSessions: [
        {
          session_id: "ext-1",
          name: "Chrome",
          browser_info: { name: "Chrome" },
          extension_version: "1.0.0",
        },
      ],
    });
    const locals = wrapper.findAll("g.topo-node.is-local");
    const extNode = locals.find((g) => g.find("title").text().includes("浏览器扩展"));
    expect(extNode).not.toBeNull();
    await extNode.trigger("contextmenu", { clientX: 100, clientY: 200 });
    expect(wrapper.find(".file-tree-context-menu").exists()).toBe(false);
  });

  test("菜单坐标在视口边界内收敛", async () => {
    const wrapper = mountTopology();
    const node = findDaemonNode(wrapper);
    // 视口 1024x768（jsdom 默认），右键在右下角，菜单应被收敛进视口
    await node.trigger("contextmenu", { clientX: 2000, clientY: 2000 });
    const menu = wrapper.find(".file-tree-context-menu");
    const style = menu.attributes("style");
    expect(style).toContain("left:");
    expect(style).toContain("top:");
    // 解析出坐标并断言不越界
    const left = Number(style.match(/left:\s*([\d.]+)px/)?.[1] || 0);
    const top = Number(style.match(/top:\s*([\d.]+)px/)?.[1] || 0);
    expect(left + 220).toBeLessThanOrEqual(1024);
    expect(top + 120).toBeLessThanOrEqual(768);
  });
});
