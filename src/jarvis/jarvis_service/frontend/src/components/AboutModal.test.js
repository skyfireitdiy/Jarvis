// AboutModal 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/AboutModal.test.js   # 只跑本文件
//   npm run test:vitest                                 # 跑全部 vitest 用例
//
// 说明：AboutModal 是纯展示型组件——由 props 驱动渲染、通过 emit 向外
// 通知关闭，自身不发起请求，故可直接 mount 测试，无需 mock 网络。
import { describe, test, expect } from "vitest";
import { mount } from "@vue/test-utils";
import AboutModal from "./AboutModal.vue";

const baseProps = {
  visible: true,
  frontendVersion: "6.0.7",
  backendVersion: "6.0.7",
  nodes: [{ node_id: "master", status: "online", version: "6.0.7" }],
  daemonSessions: [
    {
      session_id: "s1",
      name: "skyfire-pc",
      platform: "windows",
      daemon_version: "6.0.7",
    },
  ],
  browserExtSessions: [
    {
      session_id: "e1",
      name: "Edge",
      extension_version: "6.0.7",
      browser_info: { name: "Edge" },
    },
  ],
};

function mountAbout(props = {}) {
  return mount(AboutModal, {
    props: { ...baseProps, ...props },
  });
}

describe("AboutModal 渲染", () => {
  test("visible=false 时不渲染内容", () => {
    const wrapper = mountAbout({ visible: false });
    expect(wrapper.find(".modal-overlay").exists()).toBe(false);
  });

  test("visible=true 时渲染标题与软件信息", () => {
    const wrapper = mountAbout();
    expect(wrapper.find(".modal-overlay").exists()).toBe(true);
    expect(wrapper.find(".modal-header h2").text()).toBe("关于");
    expect(wrapper.find(".about-title").text()).toBe("Jarvis Web Gateway");
    expect(wrapper.find(".about-subtitle").text()).toContain("6.0.7");
  });

  test("展示 MIT 开源协议与作者 skyfire", () => {
    const wrapper = mountAbout();
    const tags = wrapper.findAll(".about-tag").map((t) => t.text());
    expect(tags).toContain("MIT 开源协议");
    expect(tags).toContain("作者：skyfire");
  });

  test("展示节点版本", () => {
    const wrapper = mountAbout();
    const item = wrapper.find(".about-item");
    expect(item.text()).toContain("master");
    expect(item.text()).toContain("6.0.7");
  });

  test("展示 daemon 版本", () => {
    const wrapper = mountAbout();
    const text = wrapper.text();
    expect(text).toContain("skyfire-pc");
    expect(text).toContain("windows");
  });

  test("展示浏览器扩展版本", () => {
    const wrapper = mountAbout();
    const text = wrapper.text();
    expect(text).toContain("Edge");
    expect(text).toContain("6.0.7");
  });

  test("无数据时显示空态", () => {
    const wrapper = mountAbout({
      nodes: [],
      daemonSessions: [],
      browserExtSessions: [],
    });
    const text = wrapper.text();
    expect(text).toContain("暂无节点信息");
    expect(text).toContain("暂无在线后台服务");
    expect(text).toContain("暂无在线浏览器扩展");
  });

  test("点击关闭按钮 emit update:visible false", () => {
    const wrapper = mountAbout();
    wrapper.find(".close-btn").trigger("click");
    expect(wrapper.emitted("update:visible")).toBeTruthy();
    expect(wrapper.emitted("update:visible")[0]).toEqual([false]);
  });

  test("点击遮罩空白处关闭", () => {
    const wrapper = mountAbout();
    wrapper.find(".modal-overlay").trigger("click");
    expect(wrapper.emitted("update:visible")).toBeTruthy();
    expect(wrapper.emitted("update:visible")[0]).toEqual([false]);
  });
});
