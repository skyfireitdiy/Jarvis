/*
 * 反例：释放后置NULL
 * 预期：不应该检测到 double_free
 */
#include <stdlib.h>
void safe_free_example(char *ptr) {
  free(ptr);
  ptr = NULL; // 安全：释放后立即置NULL
  // 即使再次free(ptr)也是安全的（free(NULL)是合法的）
}
