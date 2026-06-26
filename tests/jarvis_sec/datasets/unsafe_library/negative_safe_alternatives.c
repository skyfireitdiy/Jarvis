/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: 使用安全的替代函数
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <time.h>

void safe_functions() {
  char buffer[100];

  // 安全: 使用带边界检查的scanf
  scanf("%99s", buffer);

  // 安全: 使用strtok_r线程安全版本
  char str[] = "hello world";
  char *saveptr;
  char *token = strtok_r(str, " ", &saveptr);

  // 安全: 使用getrandom或arc4random
  unsigned int random;
  getrandom(&random, sizeof(random), 0);

  // 安全: 使用localtime_r线程安全版本
  time_t t = time(NULL);
  struct tm tm_result;
  localtime_r(&t, &tm_result);

  // 安全: 复制getenv结果
  char *home = getenv("HOME");
  if (home) {
    char home_copy[256];
    strncpy(home_copy, home, sizeof(home_copy) - 1);
    home_copy[sizeof(home_copy) - 1] = '\0';
  }
}
