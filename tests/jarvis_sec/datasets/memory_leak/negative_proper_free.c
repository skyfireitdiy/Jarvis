/*
 * 反例：正确释放内存
 * 预期：不应该检测到 memory_leak
 */
#include <stdlib.h>
void no_leak(int size) {
  char *buffer = (char *)malloc(size);
  if (buffer != NULL) {
    // 使用buffer...
    free(buffer); // 安全：正确释放内存
  }
}
