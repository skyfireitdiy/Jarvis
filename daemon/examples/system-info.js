// system-info.js — 读取系统信息示例
//
// 用法：jarvis-daemon run-script examples/system-info.js
//
// 展示：
//   - jarvis.cap() 通用调用能力
//   - print() / console.log() 输出到 stdout
//   - 脚本顶层返回值打印到 stdout

// 方式一：jarvis.cap(name, params) 通用入口（返回 {success, data, error}）
const res = jarvis.cap("linux.system.info", {});
if (res.success) {
  print("主机名:", res.data.hostname);
  print("操作系统:", res.data.os_name, res.data.os_version, res.data.arch);
  print("内核:", res.data.kernel);
  print(
    "内存:",
    Math.round(res.data.mem_available_kb / 1024) +
      " MB 可用 / " +
      Math.round(res.data.mem_total_kb / 1024) +
      " MB 总计",
  );
} else {
  console.error("获取系统信息失败:", res.error);
}

// 方式二：jarvis.caps.<域>.<动作>(params) 嵌套命名空间（失败抛异常）
try {
  const info = jarvis.caps.linux.system.info({});
  print("CPU 核心数:", info.cpu_count);
} catch (e) {
  console.error("嵌套调用失败:", e.message);
}

// 顶层返回值会被 run-script 打印到 stdout
("系统信息读取完成");
