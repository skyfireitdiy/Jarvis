/*
 * 正例：malloc后未释放
 * 预期：应该检测到 memory_leak
 */
#include <stdlib.h>
void leak_memory(int size) {
  char *buffer = (char *)malloc(size);
  // 使用buffer...
  // 危险：函数结束前没有free(buffer)，导致内存泄漏
}
