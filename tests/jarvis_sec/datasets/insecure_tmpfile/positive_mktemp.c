/*
 * 正例：mktemp使用
 * 预期：应该检测到 insecure_tmpfile
 */
#include <stdlib.h>
void foo() {
  char template[] = "fileXXXXXX";
  mktemp(template); // 真实风险：不安全临时文件
}
