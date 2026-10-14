// AdminPanel 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/AdminPanel.test.js   # 只跑本文件
//   npm run test:vitest                                 # 跑全部 vitest 用例
//
// 说明：AdminPanel 打开时会触发 loadUsers/loadGroups/loadPermissionSchema 等
// API 调用，测试中通过 mock fetchWithAuth 返回空数据避免真实网络请求。
import { describe, test, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import AdminPanel from "./AdminPanel.vue";

// 空数据响应，模拟后端返回无用户/无权限组/无权限清单
const emptyJson = () => Promise.resolve({ json: () => Promise.resolve({ success: true, data: {} }) });
const mockFetchWithAuth = vi.fn(() => emptyJson());

const baseProps = {
  visible: true,
  auth: { userInfo: { user_id: "admin", username: "admin", is_admin: true } },
  fetchWithAuth: mockFetchWithAuth,
  gatewayUrl: "127.0.0.1:8000",
  showToast: () => {},
  getHttpProtocol: () => "http",
  availableNodeOptions: [
    { node_id: "node-1", status: "online" },
    { node_id: "node-2", status: "online" },
  ],
};

function mountAdmin(props = {}) {
  return mount(AdminPanel, {
    props: { ...baseProps, ...props },
    global: {
      stubs: {
        ConfigEditorModal: true,
      },
    },
  });
}

describe("AdminPanel 配置备份与恢复节点下拉", () => {
  test("传 getNodeDisplayName 时下拉显示别名", async () => {
    const getNodeDisplayName = (nodeId) => (nodeId === "node-1" ? "生产节点" : nodeId);
    const wrapper = mountAdmin({ getNodeDisplayName });
    await flushPromises();
    // 切换到「配置文件」tab
    const configTab = wrapper.findAll(".admin-tab").find((b) => b.text() === "配置文件");
    await configTab.trigger("click");
    await flushPromises();
    const options = wrapper.findAll(".config-backup-row .node-select option");
    const labels = options.map((o) => o.text());
    expect(labels).toContain("生产节点");
    expect(labels).toContain("node-2");
  });

  test("不传 getNodeDisplayName 时回退 node_id", async () => {
    const wrapper = mountAdmin();
    await flushPromises();
    const configTab = wrapper.findAll(".admin-tab").find((b) => b.text() === "配置文件");
    await configTab.trigger("click");
    await flushPromises();
    const options = wrapper.findAll(".config-backup-row .node-select option");
    const labels = options.map((o) => o.text());
    expect(labels).toContain("node-1");
    expect(labels).toContain("node-2");
  });
});
