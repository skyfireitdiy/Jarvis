/*
 * 正例：使用gets函数
 * 预期：应该检测到 buffer_overflow
 */
#include <stdio.h>
void vulnerable_input() {
  char buffer[100];
  gets(buffer); // 危险：gets不检查边界，可能导致缓冲区溢出
}
