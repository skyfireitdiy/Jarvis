/*
 * 正例：alloca使用变量大小
 * 预期：应该检测到 alloca_unbounded
 */
#include <alloca.h>
void foo(size_t n) {
  char *p = alloca(n); // 真实风险：无界分配
}
