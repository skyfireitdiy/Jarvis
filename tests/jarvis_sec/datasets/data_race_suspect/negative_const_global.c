/*
 * 反例：const全局变量
 * 预期：不应该检测到 data_race_suspect
 */
#include <pthread.h>
const int shared_data = 0; // const，只读
void *thread_func(void *arg) {
  int val = shared_data;
  return NULL;
}
int main() {
  pthread_t t;
  pthread_create(&t, NULL, thread_func, NULL);
  pthread_join(t, NULL);
  return 0;
}
