// list-dir.js — 列出目录内容示例
//
// 用法：jarvis-daemon run-script examples/list-dir.js --arg path=/tmp
//
// 展示：
//   - jarvis.args 脚本参数注入（--arg key=value）
//   - jarvis.cap() 调用 linux.fs.list
//   - 遍历返回的 entries 数组

// 从 jarvis.args 读取目录路径（默认当前目录）
const path = jarvis.args.path || ".";

const res = jarvis.cap("linux.fs.list", { path: path });
if (!res.success) {
  console.error("列出目录失败:", res.error);
  throw new Error("目录列表失败: " + path);
}

print("目录:", res.data.path, "（共 " + res.data.count + " 个条目）");
print("----------------------------------------");

// 遍历条目，目录加 [D] 前缀
for (const entry of res.data.entries) {
  const prefix = entry.is_dir ? "[D] " : "    ";
  print(prefix + entry.name);
}

// 顶层返回值
("目录列表完成");
