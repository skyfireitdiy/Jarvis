/*
 * 正例：rand使用
 * 预期：应该检测到 rand_insecure
 */
#include <stdlib.h>
void foo() {
  int x = rand(); // 真实风险：不安全随机数
}
