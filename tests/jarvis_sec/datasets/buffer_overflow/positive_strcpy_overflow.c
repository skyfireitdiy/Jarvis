/*
 * 正例：strcpy无边界检查
 * 预期：应该检测到 buffer_overflow
 */
#include <string.h>
void copy_user_input(char *user_input) {
  char buffer[100];
  strcpy(buffer, user_input); // 危险：如果user_input超过100字节会溢出
}
