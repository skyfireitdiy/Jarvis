// 格式化字符串漏洞反例：常量格式字符串
// 不应该检测到：使用常量格式字符串

#include <stdio.h>
#include <stdlib.h>

void safe_printf(char *user_input) {
  // 污点汇：使用常量格式字符串
  printf("User input: %s\n", user_input); // 安全：常量格式
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    safe_printf(argv[1]);
  }
  return 0;
}
