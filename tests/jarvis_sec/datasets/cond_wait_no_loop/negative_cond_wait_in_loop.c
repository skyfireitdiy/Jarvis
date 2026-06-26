/*
 * 反例：pthread_cond_wait在循环中
 * 预期：不应该检测到 cond_wait_no_loop
 */
#include <pthread.h>
int condition = 0;
void foo(pthread_cond_t *c, pthread_mutex_t *m) {
  pthread_mutex_lock(m);
  while (!condition) {
    pthread_cond_wait(c, m); // 安全：在循环中
  }
  pthread_mutex_unlock(m);
}
