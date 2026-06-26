/*
 * 正例：递归锁
 * 预期：应该检测到 deadlock_patterns
 */
#include <pthread.h>
void foo(pthread_mutex_t *m) {
  pthread_mutex_lock(m);
  pthread_mutex_lock(m); // 真实风险：递归锁
}
