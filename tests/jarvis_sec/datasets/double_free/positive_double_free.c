/*
 * 正例：重复释放内存
 * 预期：应该检测到 double_free
 */
#include <stdlib.h>
void double_free_example(char *ptr) {
  free(ptr);
  // ... 一些代码 ...
  free(ptr); // 危险：重复释放同一块内存
}
