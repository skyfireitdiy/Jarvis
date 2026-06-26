/*
 * 正例：strtok使用
 * 预期：应该检测到 strtok_nonreentrant
 */
#include <string.h>
void foo(char *s) {
  char *token = strtok(s, ","); // 真实风险：不可重入
}
