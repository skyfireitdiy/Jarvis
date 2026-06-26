/*
 * 预期检测结果: 应检测到不安全库函数使用
 * 漏洞类型: 使用已废弃或不安全的函数
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void unsafe_functions() {
  char buffer[100];

  // 不安全: scanf无边界检查
  scanf("%s", buffer);

  // 不安全: strtok非线程安全
  char str[] = "hello world";
  char *token = strtok(str, " ");

  // 不安全: rand不可用于安全目的
  int random = rand();

  // 不安全: localtime非线程安全
  time_t t = time(NULL);
  struct tm *tm = localtime(&t);

  // 不安全: getenv返回静态缓冲区
  char *home = getenv("HOME");
}
