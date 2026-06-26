/*
 * 反例：open使用0600权限
 * 预期：不应该检测到 open_permissive_perms
 */
#include <fcntl.h>
void foo() {
  int fd = open("test.txt", O_CREAT, 0600); // 安全：权限合理
}
