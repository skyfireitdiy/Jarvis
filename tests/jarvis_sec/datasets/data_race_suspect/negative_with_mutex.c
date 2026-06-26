/*
 * 反例：有互斥锁保护
 * 预期：不应该检测到 data_race_suspect
 */
#include <pthread.h>
int shared_data = 0;
pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
void *thread_func(void *arg) {
  pthread_mutex_lock(&mutex);
  shared_data = 100; // 安全：有锁保护
  pthread_mutex_unlock(&mutex);
  return NULL;
}
int main() {
  pthread_t t;
  pthread_create(&t, NULL, thread_func, NULL);
  pthread_join(t, NULL);
  return 0;
}
