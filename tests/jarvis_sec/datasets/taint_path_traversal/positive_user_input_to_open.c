// 路径遍历正例：用户输入 -> open 污点传播
// 应该检测到：用户输入直接用于文件路径

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    char *filename = argv[1];

    // 污点汇：打开文件
    // 污点传播路径：argv -> filename -> open
    int fd = open(filename, O_RDONLY); // 路径遍历风险

    if (fd >= 0) {
      char buffer[100];
      read(fd, buffer, sizeof(buffer));
      close(fd);
    }
  }
  return 0;
}
