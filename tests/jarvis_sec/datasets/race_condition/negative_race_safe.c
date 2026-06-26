/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: 使用原子操作或文件描述符
 */
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

void safe_file_access(char *filename) {
  // 安全: 使用open和fstat，避免TOCTOU
  int fd = open(filename, O_RDONLY);
  if (fd == -1)
    return;

  struct stat st;
  if (fstat(fd, &st) == 0) {
    // 使用文件描述符，避免竞态
    FILE *fp = fdopen(fd, "r");
    if (fp) {
      char buffer[100];
      fgets(buffer, sizeof(buffer), fp);
      fclose(fp);
      return;
    }
  }
  close(fd);
}
