// 命令注入正例：getenv -> system 污点传播
// 应该检测到：环境变量数据直接用于执行系统命令

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[]) {
  // 污点源：从环境变量获取数据
  char *cmd = getenv("CMD");

  if (cmd != NULL) {
    // 污点汇：执行系统命令
    // 污点传播路径：getenv -> cmd -> system
    system(cmd); // 命令注入风险
  }

  return 0;
}
