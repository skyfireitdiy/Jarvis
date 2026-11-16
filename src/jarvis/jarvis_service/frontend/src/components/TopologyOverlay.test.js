// TopologyOverlay 组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/TopologyOverlay.test.js   # 只跑本文件
//   npm run test:vitest                                     # 跑全部 vitest 用例
//
// 说明：本组件是纯前端渲染（自绘 SVG 拓扑图），不依赖后端接口。
// 本测试重点覆盖「daemon 去重」：daemon 会话同时存在于 availableNodeOptions
// （nodes prop）与 daemonSessions prop，组件应只把它渲染为圆形接入端一次，
// 不得再以服务器机箱（普通节点）造型重复渲染。
import { describe, test, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import TopologyOverlay from "./TopologyOverlay.vue";

// 构造基础 props：一个普通子节点 + master + 一个 daemon 节点（同时出现在 nodes 与 daemonSessions）
function baseProps(overrides = {}) {
  const nodes = [
    { node_id: "master", status: "online" },
    { node_id: "node-a", status: "online" },
    // daemon 节点：availableNodeOptions 合并进来的（带 daemon: true 标志）
    { node_id: "daemon-host-1", status: "running", daemon: true, name: "my-daemon" },
  ];
  const agents = [];
  const daemonSessions = [
    { session_id: "s1", node_id: "daemon-host-1", name: "my-daemon", platform: "linux", daemon_version: "v5.0.5" },
  ];
  return {
    visible: true,
    nodes,
    agents,
    getStatusClass: () => "running",
    nodeDisplayNames: {},
    extensionSessions: [],
    daemonSessions,
    ...overrides,
  };
}

describe("TopologyOverlay daemon 去重", () => {
  test("daemon 节点不渲染为服务器机箱（普通节点），仅渲染为圆形接入端一次", () => {
    const wrapper = mount(TopologyOverlay, { props: baseProps() });

    // 机箱节点：普通节点（node-a）+ master；daemon 不应出现在机箱节点中
    const serverNodes = wrapper.findAll(".topo-node:not(.is-local)");
    // master 是 is-center，node-a 是普通机箱；daemon 不应被渲染为机箱
    const nodeLabels = serverNodes.map(n => n.text()).join(" ");
    expect(nodeLabels).toContain("node-a");
    expect(nodeLabels).not.toContain("my-daemon");

    // 圆形接入端：daemon 以 is-local 渲染一次
    const localNodes = wrapper.findAll(".topo-node.is-local");
    const localText = localNodes.map(n => n.text()).join(" ");
    expect(localText).toContain("my-daemon");
  });

  test("daemon 会话缺失时（nodes 含 daemon 但 daemonSessions 为空）不渲染任何 daemon 节点", () => {
    const props = baseProps({ daemonSessions: [] });
    const wrapper = mount(TopologyOverlay, { props });

    const allText = wrapper.text();
    expect(allText).not.toContain("my-daemon");
    // 普通节点仍正常渲染
    expect(allText).toContain("node-a");
  });

  test("无 daemon 时普通节点正常渲染，不受过滤逻辑影响", () => {
    const props = baseProps({
      nodes: [
        { node_id: "master", status: "online" },
        { node_id: "node-a", status: "online" },
        { node_id: "node-b", status: "online" },
      ],
      daemonSessions: [],
    });
    const wrapper = mount(TopologyOverlay, { props });

    const allText = wrapper.text();
    expect(allText).toContain("node-a");
    expect(allText).toContain("node-b");
  });
});
