// 格式化字符串漏洞正例：用户输入 -> printf 污点传播
// 应该检测到：用户输入直接用作格式化字符串

#include <stdio.h>
#include <stdlib.h>

void vulnerable_printf(char *user_input) {
  // 污点汇：用户输入用作格式化字符串
  // 污点传播路径：argv -> user_input -> printf
  printf(user_input); // 格式化字符串漏洞
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    vulnerable_printf(argv[1]);
  }
  return 0;
}
