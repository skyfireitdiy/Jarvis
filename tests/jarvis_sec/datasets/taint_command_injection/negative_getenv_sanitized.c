// 命令注入反例：getenv -> system 有净化
// 不应该检测到：环境变量数据经过净化后用于执行系统命令

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// 净化函数：移除危险字符
void sanitize_command(char *cmd) {
  char *dangerous_chars = ";&|`$\"";
  char *p = cmd;
  while (*p) {
    if (strchr(dangerous_chars, *p)) {
      *p = ' '; // 替换为空格
    }
    p++;
  }
}

int main(int argc, char *argv[]) {
  // 污点源：从环境变量获取数据
  char *cmd = getenv("CMD");

  if (cmd != NULL) {
    // 净化：移除危险字符
    sanitize_command(cmd);

    // 污点汇：执行系统命令（已净化）
    system(cmd); // 安全：已净化
  }

  return 0;
}
