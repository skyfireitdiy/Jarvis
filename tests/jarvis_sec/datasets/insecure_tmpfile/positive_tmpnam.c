/*
 * 正例：tmpnam使用
 * 预期：应该检测到 insecure_tmpfile
 */
#include <stdio.h>
void foo() {
  char name[L_tmpnam];
  tmpnam(name); // 真实风险：不安全临时文件
}
