/*
 * 反例：刚分配成功后的立即使用
 * 预期：不应该检测到 possible_null_deref
 */
#include <stdlib.h>
void foo() {
  char *p = malloc(100);
  p[0] = 'x'; // 安全：刚分配成功
}
