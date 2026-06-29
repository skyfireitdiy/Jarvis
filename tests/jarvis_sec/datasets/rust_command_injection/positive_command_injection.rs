// Positive case: command injection vulnerability
use std::io::{self, BufRead};
use std::process::Command;

fn main() {
    let stdin = io::stdin();
    let user_input = stdin.lock().lines().next().unwrap().unwrap();

    // Vulnerable: user input directly in command
    let output = Command::new("sh")
        .arg("-c")
        .arg(&user_input)
        .output()
        .expect("failed to execute");
}
