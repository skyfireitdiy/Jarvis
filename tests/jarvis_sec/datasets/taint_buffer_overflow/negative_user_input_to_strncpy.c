// 缓冲区溢出反例：使用strncpy限制长度
// 不应该检测到：使用strncpy限制复制长度

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void safe_copy(const char *user_input) {
  char buffer[64];

  // 使用strncpy限制复制长度
  strncpy(buffer, user_input, sizeof(buffer) - 1); // 安全：限制长度
  buffer[sizeof(buffer) - 1] = '\0';

  printf("Copied: %s\n", buffer);
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    safe_copy(argv[1]);
  }
  return 0;
}
