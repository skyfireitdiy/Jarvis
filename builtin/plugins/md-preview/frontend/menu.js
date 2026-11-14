// md-preview 插件前端（context_menu_items 扩展点）。
// 本扩展点不需要加载 Vue 组件：菜单条目与回调由 useFileTree.js 直接处理
// （点击后经 /function-call 调用 plugin/api.py 的 preview_markdown）。
// 此文件仅作为 entry 占位，满足 fetchPluginExtensions 对 entry 字段的校验。
// 若后续需要"预览面板"等交互，可在此导出 Vue 组件，并在 config.yaml 增加
// 对应的 pane_views / sidebar_views 扩展。
export default {};
