/*
 * 正例：malloc中使用乘法
 * 预期：应该检测到 alloc_size_overflow
 */
#include <stdlib.h>
void foo(size_t n, size_t m) {
  char *p = malloc(n * m); // 真实风险：可能整数溢出
}
