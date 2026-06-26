// 缓冲区溢出正例：用户输入 -> strcpy 污点传播
// 应该检测到：用户输入复制到固定大小缓冲区

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void vulnerable_copy(const char *user_input) {
  char buffer[64];

  // 污点汇：用户输入复制到固定大小缓冲区
  // 污点传播路径：argv -> user_input -> strcpy -> buffer
  strcpy(buffer, user_input); // 缓冲区溢出风险

  printf("Copied: %s\n", buffer);
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    vulnerable_copy(argv[1]);
  }
  return 0;
}
