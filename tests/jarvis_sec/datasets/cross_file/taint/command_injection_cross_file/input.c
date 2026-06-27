#include <stdio.h>

void get_user_input(char* buffer, int size) {
    fgets(buffer, size, stdin);
}
