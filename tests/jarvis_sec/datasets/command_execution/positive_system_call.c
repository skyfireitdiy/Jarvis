/*
 * 正例：system调用
 * 预期：应该检测到 command_execution
 */
#include <stdlib.h>
void foo(char *cmd) {
  system(cmd); // 真实风险：命令注入
}
