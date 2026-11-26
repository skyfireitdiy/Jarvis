---
name: frontend-visual-feature-verification
description: 当需要开发或验证前端视觉类功能（壁纸、主题、透明度、背景、毛玻璃、动画、布局）时触发。每当用户提及"壁纸"、"透明度"、"半透明"、"毛玻璃"、"背景图"、"主题"、"视觉验证"、"截图验证"时触发。不触发：纯逻辑/接口开发不涉及视觉；仅后端改动；仅单元测试编写。
---
# 前端视觉类功能开发与验证规则

本规则述 Jarvis 前端（Vue3 + src/jarvis/jarvis_service/frontend）视觉类功能之开发要点与验证方法。

## 一、层叠上下文陷阱（务必先读）

前端"背景/壁纸不显示"之故障，九成源于层叠上下文，而非 CSS 语法错误。开发前须确认：

1. **全屏固定背景层须挂根级，不可挂 `.app`**
   - `body` 有不透明渐变背景，且 `.app` 设 `isolation: isolate`
   - 故 `.app` 内 `z-index: -1` 之伪元素被锁在 `.app` 层叠上下文内，被 body 背景遮挡
   - 正解：根级 `<div class="jarvis-wallpaper-layer">`（`position:fixed; inset:0; z-index:-1; pointer-events:none`）

2. **`:root`（html）之 background 须透明**
   - `:root` 默认 `background: var(--color-bg-primary)`，会压住 `z-index:-1` 之背景层
   - 改为 `transparent`，无背景图时由 body 渐变负责视觉

3. **有背景图时给 body 去底色**
   - `body.jarvis-has-wallpaper { background: transparent }`，否则 body 渐变盖住背景层

4. **全屏遮罩须一并处理**
   - 登录遮罩 `.connect-overlay` 为 `z-index:9999` 之不透明全屏层，会完全盖住背景图
   - 启用半透明时须同步改为半透明 + 毛玻璃

## 二、透明度实现铁律

**禁止用父级 `opacity` 实现"半透明"**。实测（headless chromium）：父元素带 `opacity` 时，子元素 `backdrop-filter` 完全失效，毛玻璃与背景透出同时丢失。

正解：CSS 变量驱动底色 alpha，再配 `backdrop-filter`：

```css
:root {
  --jarvis-ui-opacity: 1;
  --jarvis-panel-bg: color-mix(
    in srgb,
    #0b1424 calc(var(--jarvis-ui-opacity) * 100%),
    transparent
  );
}
.app.ui-translucent .workspace-panel {
  background: var(--jarvis-panel-bg);
  backdrop-filter: blur(18px) saturate(1.15);
  -webkit-backdrop-filter: blur(18px) saturate(1.15);
}
```

## 三、验证方法（不可只靠"看起来对"）

1. **构建 + 单测**：`npx vite build`、`npx vitest run`、`npx eslint <改动文件>`（须 0 error）
2. **真实渲染截图**：用 playwright 无头浏览器加载 `dist`，注入 localStorage 设置后截图
3. **像素级比对**：用 PIL 采样对比不同设置下之差异均值与关键点像素值，确认效果真实生效
   - 差异过小（如 < 0.5）→ 功能未生效，须排查层叠
4. **跳过协议弹窗**：截图前须设 `localStorage['jarvis_user_agreement_v1']='1'`，否则测到的是协议弹窗
5. **确认素材可访问**：先用 `curl -o /dev/null -w "%{http_code}"` 确认图片返回 200，否则 404 会被误判为 CSS 失效
6. **清理测试素材**：临时放入 `dist/` 之测试图片须删除，避免随构建产物发布

## 四、设置项持久化约定

- 每浏览器本地设置 → `localStorage`，参考 `HIDE_WORKING_DIR_STORAGE_KEY` 模式（`load*` / `save*` 成对，try/catch 静默降级）
- 跨终端共享资源（如壁纸文件）→ 存网关，本地只记 URL
- 设置弹窗 `SettingsModal.vue` 通过 props + emit 与 `App.vue` 通信，新增设置须同时改两处

## 检查清单

- [ ] 背景层挂根级，未挂 `.app`
- [ ] `:root` background 已透明
- [ ] 有背景图时 body 已去底色
- [ ] 全屏遮罩已同步半透明
- [ ] 未使用父级 `opacity` 实现透明度
- [ ] 已做像素级比对验证，非仅肉眼判断
- [ ] 测试素材已清理
