// DirectoryDialog 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/DirectoryDialog.test.js   # 只跑本文件
//   npm run test:vitest                                     # 跑全部 vitest 用例
//
// 说明：DirectoryDialog 是纯展示型组件——由 props 驱动渲染、通过 emit 向外
// 通知交互，自身不发起请求，故可直接 mount 测试，无需 mock 网络。
import { describe, test, expect } from "vitest";
import { mount } from "@vue/test-utils";
import DirectoryDialog from "./DirectoryDialog.vue";

// 构造目录项
const dir = (name, path) => ({ name, path });

// 默认挂载参数：visible + 一个目录
function mountDialog(props = {}) {
  return mount(DirectoryDialog, {
    props: {
      visible: true,
      currentPath: "/home/user",
      filteredDirs: [dir("proj", "/home/user/proj")],
      ...props,
    },
  });
}

describe("DirectoryDialog 渲染", () => {
  test("visible=false 时不渲染内容", () => {
    const wrapper = mountDialog({ visible: false });
    expect(wrapper.find(".palette-overlay").exists()).toBe(false);
    expect(wrapper.find(".dir-modal").exists()).toBe(false);
  });

  test("visible=true 时渲染遮罩、标题与当前路径", () => {
    const wrapper = mountDialog({ title: "选择工作目录" });
    expect(wrapper.find(".palette-overlay").exists()).toBe(true);
    expect(wrapper.find(".dir-modal-header h2").text()).toBe("选择工作目录");
    expect(wrapper.find(".current-path").text()).toBe("/home/user");
  });

  test("title 默认值为「选择工作目录」", () => {
    const wrapper = mountDialog();
    expect(wrapper.find(".dir-modal-header h2").text()).toBe("选择工作目录");
  });

  test("渲染目录项（图标/名称/路径）", () => {
    const wrapper = mountDialog({
      filteredDirs: [dir("a", "/p/a"), dir("b", "/p/b")],
    });
    const items = wrapper.findAll(".dir-item");
    expect(items).toHaveLength(2);
    expect(items[0].find(".dir-name").text()).toBe("a");
    expect(items[0].find(".dir-path").text()).toBe("/p/a");
    expect(items[0].find(".dir-icon").text()).toBe("📁");
  });

  test("selectedDir 命中的目录项带 selected 类", () => {
    const wrapper = mountDialog({
      filteredDirs: [dir("a", "/p/a"), dir("b", "/p/b")],
      selectedDir: "/p/b",
    });
    const items = wrapper.findAll(".dir-item");
    expect(items[0].classes()).not.toContain("selected");
    expect(items[1].classes()).toContain("selected");
  });

  test("searchText 回显到搜索框", () => {
    const wrapper = mountDialog({ searchText: "proj" });
    expect(wrapper.find(".dir-search-input").element.value).toBe("proj");
  });
});

describe("DirectoryDialog 空态", () => {
  test("非文件模式：无目录时显示「该目录下没有子目录」", () => {
    const wrapper = mountDialog({ filteredDirs: [] });
    expect(wrapper.find(".dir-list").exists()).toBe(false);
    expect(wrapper.find(".empty-state p").text()).toBe("该目录下没有子目录");
  });

  test("文件模式：无目录无文件时显示「该目录下没有子目录或文件」", () => {
    const wrapper = mountDialog({
      filteredDirs: [],
      fileSelectable: true,
      fileList: [],
    });
    expect(wrapper.find(".empty-state p").text()).toBe(
      "该目录下没有子目录或文件",
    );
  });
});

describe("DirectoryDialog 文件选择模式", () => {
  test("fileSelectable=false 时不渲染文件项（即使传了 fileList）", () => {
    const wrapper = mountDialog({
      fileSelectable: false,
      fileList: [{ name: "a.yaml", path: "/p/a.yaml" }],
    });
    expect(wrapper.findAll(".file-item")).toHaveLength(0);
  });

  test("fileSelectable=true 时渲染文件项，图标默认 📄", () => {
    const wrapper = mountDialog({
      fileSelectable: true,
      fileList: [
        { name: "a.yaml", path: "/p/a.yaml" },
        { name: "b.yml", path: "/p/b.yml" },
      ],
    });
    const files = wrapper.findAll(".file-item");
    expect(files).toHaveLength(2);
    expect(files[0].find(".dir-name").text()).toBe("a.yaml");
    expect(files[0].find(".dir-icon").text()).toBe("📄");
  });

  test("fileIcon 可自定义文件项图标", () => {
    const wrapper = mountDialog({
      fileSelectable: true,
      fileIcon: "📃",
      fileList: [{ name: "a.yaml", path: "/p/a.yaml" }],
    });
    expect(wrapper.find(".file-item .dir-icon").text()).toBe("📃");
  });

  test("selectedFile 命中的文件项带 selected 类", () => {
    const wrapper = mountDialog({
      fileSelectable: true,
      selectedFile: "/p/b.yml",
      fileList: [
        { name: "a.yaml", path: "/p/a.yaml" },
        { name: "b.yml", path: "/p/b.yml" },
      ],
    });
    const files = wrapper.findAll(".file-item");
    expect(files[0].classes()).not.toContain("selected");
    expect(files[1].classes()).toContain("selected");
  });

  test("仅有文件无目录时仍渲染列表（不显示空态）", () => {
    const wrapper = mountDialog({
      filteredDirs: [],
      fileSelectable: true,
      fileList: [{ name: "a.yaml", path: "/p/a.yaml" }],
    });
    expect(wrapper.find(".dir-list").exists()).toBe(true);
    expect(wrapper.find(".empty-state").exists()).toBe(false);
  });
});

describe("DirectoryDialog 交互 emit", () => {
  test("点击目录项 emit select 与 enter", async () => {
    const wrapper = mountDialog({
      filteredDirs: [dir("proj", "/home/user/proj")],
    });
    await wrapper.find(".dir-item").trigger("click");
    expect(wrapper.emitted("select")).toBeTruthy();
    expect(wrapper.emitted("select")[0]).toEqual(["/home/user/proj"]);
    expect(wrapper.emitted("enter")).toBeTruthy();
    expect(wrapper.emitted("enter")[0]).toEqual(["/home/user/proj", false]);
  });

  test("点击文件项 emit select-file", async () => {
    const wrapper = mountDialog({
      fileSelectable: true,
      fileList: [{ name: "a.yaml", path: "/p/a.yaml" }],
    });
    await wrapper.find(".file-item").trigger("click");
    expect(wrapper.emitted("select-file")).toBeTruthy();
    expect(wrapper.emitted("select-file")[0]).toEqual(["/p/a.yaml"]);
  });

  test("搜索框输入 emit update:searchText", async () => {
    const wrapper = mountDialog();
    const input = wrapper.find(".dir-search-input");
    await input.setValue("abc");
    expect(wrapper.emitted("update:searchText")).toBeTruthy();
    expect(wrapper.emitted("update:searchText")[0]).toEqual(["abc"]);
  });

  test("搜索框按键 emit search-keydown", async () => {
    const wrapper = mountDialog();
    await wrapper
      .find(".dir-search-input")
      .trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("search-keydown")).toBeTruthy();
  });

  test("刷新与上级按钮 emit refresh / go-parent", async () => {
    const wrapper = mountDialog();
    const btns = wrapper.findAll(".path-btn");
    await btns[0].trigger("click");
    await btns[1].trigger("click");
    expect(wrapper.emitted("refresh")[0]).toEqual(["/home/user"]);
    expect(wrapper.emitted("go-parent")).toBeTruthy();
  });

  test("非内嵌模式：取消/确认/关闭按钮 emit cancel / confirm", async () => {
    const wrapper = mountDialog();
    await wrapper.find(".dir-close-btn").trigger("click");
    const actionBtns = wrapper.findAll(".dir-modal-actions .btn");
    await actionBtns[0].trigger("click"); // 取消
    await actionBtns[1].trigger("click"); // 确认
    expect(wrapper.emitted("cancel")).toHaveLength(2);
    expect(wrapper.emitted("confirm")).toHaveLength(1);
  });
});

describe("DirectoryDialog 内嵌模式", () => {
  test("embedded=true 时不渲染遮罩、标题栏与底部按钮", () => {
    const wrapper = mountDialog({ embedded: true });
    expect(wrapper.find(".palette-overlay").exists()).toBe(false);
    expect(wrapper.find(".dir-modal-embedded").exists()).toBe(true);
    expect(wrapper.find(".dir-modal-header").exists()).toBe(false);
    expect(wrapper.find(".dir-modal-actions").exists()).toBe(false);
  });

  test("embedded=true 仍渲染路径/搜索/列表", () => {
    const wrapper = mountDialog({ embedded: true });
    expect(wrapper.find(".current-path").text()).toBe("/home/user");
    expect(wrapper.find(".dir-search-input").exists()).toBe(true);
    expect(wrapper.find(".dir-item").exists()).toBe(true);
  });
});
