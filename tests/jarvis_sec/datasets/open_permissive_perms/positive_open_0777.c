/*
 * 正例：open使用0777权限
 * 预期：应该检测到 open_permissive_perms
 */
#include <fcntl.h>
void foo() {
  int fd = open("test.txt", O_CREAT, 0777); // 真实风险：权限过于宽松
}
