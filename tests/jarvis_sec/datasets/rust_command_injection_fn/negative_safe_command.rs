// Negative case: hardcoded command with no user input
// No taint flow from user input to command execution.

use std::process::Command;

fn run_safe_command() {
    // SAFE: no user input flows to the command
    let _ = Command::new("ls").arg("-la").status();
}

fn main() {
    run_safe_command();
}
