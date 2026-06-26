/*
 * 正例：popen调用
 * 预期：应该检测到 command_execution
 */
#include <stdio.h>
void foo(char *cmd) {
  FILE *fp = popen(cmd, "r"); // 真实风险：命令注入
}
