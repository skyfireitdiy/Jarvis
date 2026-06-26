/*
 * 正例：move后使用
 * 预期：应该检测到 move_after_use
 */
#include <string>
#include <utility>
void foo() {
  std::string s = "hello";
  std::string t = std::move(s);
  s.size(); // 真实风险：move后使用
}
