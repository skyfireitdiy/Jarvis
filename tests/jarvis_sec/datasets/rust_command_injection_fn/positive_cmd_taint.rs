// Positive case: user input flows to shell command execution
// This is a critical security vulnerability: arbitrary command execution.
// The taint analyzer should trace user input -> Command::arg -> shell execution.
// Currently the checker fails to detect this taint flow.

use std::io::{self, BufRead};
use std::process::Command;

fn run_user_command() {
    let stdin = io::stdin();
    // Source: user input from stdin
    let user_input = stdin.lock().lines().next().unwrap().unwrap();

    // Sink: user input passed directly to shell command
    // VULNERABLE: command injection - user controls the command
    let output = Command::new("sh")
        .arg("-c")
        .arg(&user_input)
        .output()
        .expect("failed to execute");
}

fn main() {
    run_user_command();
}
