/*
 * 正例：函数返回指针未检查
 * 预期：应该检测到 function_return_ptr_no_check
 */
#include <stdlib.h>
char *get_buffer() { return malloc(100); }
void foo() {
  char *p = get_buffer();
  p[0] = 'x'; // 真实风险：未检查返回值
}
