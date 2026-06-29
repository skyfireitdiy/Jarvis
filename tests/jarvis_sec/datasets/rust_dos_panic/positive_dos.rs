// Positive case: CWE-400 DoS via Panic
// Uncontrolled resource consumption leading to panic or crash.
// These patterns can cause denial of service in production.

use std::fs;
use std::io::{self, Read};

// VULNERABLE: Unbounded string allocation
fn read_user_file(path: &str) -> io::Result<String> {
    let mut file = fs::File::open(path)?;
    let mut content = String::new();
    file.read_to_string(&mut content)?; // May OOM on huge file
    Ok(content)
}

// VULNERABLE: Panic on invalid input
fn divide_checked(a: i32, b: i32) -> i32 {
    a / b // Panics if b == 0
}

// VULNERABLE: Unbounded vector growth
fn collect_all_items<T: Clone>(items: &[T]) -> Vec<T> {
    items.iter().cloned().collect() // May OOM on huge input
}

// VULNERABLE: Stack overflow via deep recursion
fn factorial_recursive(n: u64) -> u64 {
    if n <= 1 {
        1
    } else {
        n * factorial_recursive(n - 1)
    } // Stack overflow on large n
}

// VULNERABLE: Panic on array index
fn get_item(arr: &[i32], index: usize) -> i32 {
    arr[index] // Panics if index >= arr.len()
}

// VULNERABLE: Unwrap causing panic
fn parse_config(data: &str) -> i32 {
    data.trim().parse::<i32>().unwrap() // Panics on invalid input
}

// VULNERABLE: Expect causing panic
fn load_env_var(key: &str) -> String {
    std::env::var(key).expect("missing env var") // Panics if not set
}

// VULNERABLE: Infinite loop potential
fn process_until_empty(items: &mut Vec<i32>) {
    while !items.is_empty() {
        // If items is never emptied, infinite loop
        println!("Processing: {:?}", items.last());
    }
}

// VULNERABLE: Unbounded memory in string concatenation
fn build_large_string(parts: &[String]) -> String {
    let mut result = String::new();
    for part in parts {
        result.push_str(part); // May OOM with many/large parts
    }
    result
}

fn main() {
    let result = divide_checked(10, 0); // Will panic!
    println!("Result: {}", result);
}
