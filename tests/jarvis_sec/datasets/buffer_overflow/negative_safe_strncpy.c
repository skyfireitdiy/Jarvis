/*
 * 反例：使用安全的strncpy
 * 预期：不应该检测到 buffer_overflow
 */
#include <string.h>
void safe_copy(const char *input) {
  char buffer[100];
  strncpy(buffer, input, sizeof(buffer) - 1);
  buffer[sizeof(buffer) - 1] = '\0'; // 安全：限制了长度并手动添加终止符
}
