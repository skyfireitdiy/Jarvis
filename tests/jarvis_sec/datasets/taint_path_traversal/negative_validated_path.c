/*
 * 反例：验证路径安全性
 * 预期：不应该检测到 taint_path_traversal
 */
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
bool is_safe_filename(const char *filename) {
  // 检查是否包含路径遍历字符
  return strstr(filename, "..") == NULL && strchr(filename, '/') == NULL;
}
void safe_open_file(const char *filename) {
  if (is_safe_filename(filename)) {
    char path[256] = "/home/user/data/";
    strcat(path, filename); // 安全：已验证filename不包含危险字符
    FILE *fp = fopen(path, "r");
  }
}
