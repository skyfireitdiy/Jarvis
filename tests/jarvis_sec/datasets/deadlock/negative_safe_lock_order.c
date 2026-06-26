#include <pthread.h>
#include <stdio.h>

pthread_mutex_t lockA = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lockB = PTHREAD_MUTEX_INITIALIZER;

void *thread1_func(void *arg) {
  // 线程1: 先锁A，再锁B (AB顺序)
  int ret = pthread_mutex_lock(&lockA);
  if (ret != 0)
    return NULL;
  printf("Thread1: lockA acquired\n");

  ret = pthread_mutex_lock(&lockB);
  if (ret != 0) {
    pthread_mutex_unlock(&lockA);
    return NULL;
  }
  printf("Thread1: lockB acquired\n");

  ret = pthread_mutex_unlock(&lockB);
  ret = pthread_mutex_unlock(&lockA);
  return NULL;
}

void *thread2_func(void *arg) {
  // 线程2: 也是先锁A，再锁B (AB顺序) - 与线程1相同，不会死锁
  int ret = pthread_mutex_lock(&lockA);
  if (ret != 0)
    return NULL;
  printf("Thread2: lockA acquired\n");

  ret = pthread_mutex_lock(&lockB);
  if (ret != 0) {
    pthread_mutex_unlock(&lockA);
    return NULL;
  }
  printf("Thread2: lockB acquired\n");

  ret = pthread_mutex_unlock(&lockB);
  ret = pthread_mutex_unlock(&lockA);
  return NULL;
}

int main() {
  pthread_t t1, t2;
  int ret1 = pthread_create(&t1, NULL, thread1_func, NULL);
  if (ret1 != 0)
    return 1;

  int ret2 = pthread_create(&t2, NULL, thread2_func, NULL);
  if (ret2 != 0)
    return 1;

  int join1 = pthread_join(t1, NULL);
  int join2 = pthread_join(t2, NULL);
  return (join1 != 0 || join2 != 0) ? 1 : 0;
}
