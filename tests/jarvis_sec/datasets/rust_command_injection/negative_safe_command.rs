// Negative case: safe command with fixed arguments
use std::process::Command;

fn main() {
    let output = Command::new("ls")
        .arg("-la")
        .output()
        .expect("failed to execute");
}
