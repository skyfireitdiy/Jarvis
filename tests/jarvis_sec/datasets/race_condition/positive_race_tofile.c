/*
 * 预期检测结果: 应检测到TOCTOU竞态条件
 * 漏洞类型: Time-of-check to time-of-use
 */
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

void race_condition_vuln(char *filename) {
  // TOCTOU: 检查和使用之间存在竞态窗口
  if (access(filename, R_OK) == 0) {
    // 竞态窗口: 攻击者可能替换文件
    FILE *fp = fopen(filename, "r"); // 可能打开不同文件
    if (fp) {
      char buffer[100];
      fgets(buffer, sizeof(buffer), fp);
      fclose(fp);
    }
  }
}

void race_symlink_vuln(char *path) {
  // 竞态条件: lstat后使用
  struct stat st;
  if (lstat(path, &st) == 0) {
    // 竞态窗口
    FILE *fp = fopen(path, "w"); // 可能是符号链接攻击
    if (fp)
      fclose(fp);
  }
}
