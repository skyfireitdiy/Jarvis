int main() {
    char input[100];
    char cmd[200];
    get_user_input(input, sizeof(input));
    process_data(input, cmd);
    execute_command(cmd);
    return 0;
}
