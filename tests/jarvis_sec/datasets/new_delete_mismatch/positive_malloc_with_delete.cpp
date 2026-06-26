/*
 * 正例：malloc配delete
 * 预期：应该检测到 new_delete_mismatch
 */
#include <stdlib.h>
void foo() {
  int *p = (int *)malloc(sizeof(int));
  delete p; // 真实风险：new/delete不匹配
}
