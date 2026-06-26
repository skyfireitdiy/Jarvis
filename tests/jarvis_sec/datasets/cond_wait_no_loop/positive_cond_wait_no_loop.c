/*
 * 正例：pthread_cond_wait不在循环中
 * 预期：应该检测到 cond_wait_no_loop
 */
#include <pthread.h>
void foo(pthread_cond_t *c, pthread_mutex_t *m) {
  pthread_mutex_lock(m);
  pthread_cond_wait(c, m); // 真实风险：不在循环中
  pthread_mutex_unlock(m);
}
