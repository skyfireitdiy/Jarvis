/*
 * 正例：路径拼接未验证
 * 预期：应该检测到 taint_path_traversal
 */
#include <stdio.h>
#include <string.h>
void open_user_file(char *filename) {
  char path[256] = "/home/user/data/";
  strcat(path, filename); // 危险：未验证filename是否包含../等路径遍历字符
  FILE *fp = fopen(path, "r");
  // ...
}
