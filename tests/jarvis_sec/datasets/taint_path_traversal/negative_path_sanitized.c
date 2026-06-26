// 路径遍历反例：用户输入 -> open 有净化
// 不应该检测到：用户输入经过路径净化后用于文件操作

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

// 净化函数：移除路径遍历字符
void sanitize_path(char *path) {
  char *p = path;
  while (*p) {
    if (*p == '/' || *p == '\\' || *p == '..') {
      *p = '_'; // 替换为安全字符
    }
    p++;
  }
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    char filename[256];
    strncpy(filename, argv[1], sizeof(filename) - 1);
    filename[sizeof(filename) - 1] = '\0';

    // 净化：移除路径遍历字符
    sanitize_path(filename);

    // 污点汇：打开文件（已净化）
    int fd = open(filename, O_RDONLY); // 安全：已净化

    if (fd >= 0) {
      char buffer[100];
      read(fd, buffer, sizeof(buffer));
      close(fd);
    }
  }
  return 0;
}
