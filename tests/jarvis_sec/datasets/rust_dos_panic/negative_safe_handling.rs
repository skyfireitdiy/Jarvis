// Negative case: Safe resource handling avoiding DoS
// Use bounded operations, proper error handling, and safe patterns.

use std::fs;
use std::io::{self, Read};

// SAFE: Bounded file reading with limit
fn read_user_file_safe(path: &str, max_bytes: u64) -> io::Result<String> {
    let file = fs::File::open(path)?;
    let metadata = file.metadata()?;

    if metadata.len() > max_bytes {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "file too large"));
    }

    let mut content = String::new();
    let mut limited = file.take(max_bytes);
    limited.read_to_string(&mut content)?;
    Ok(content)
}

// SAFE: Checked division returning Result
fn divide_safe(a: i32, b: i32) -> Result<i32, &'static str> {
    if b == 0 {
        Err("division by zero")
    } else {
        Ok(a / b)
    }
}

// SAFE: Bounded collection with limit
fn collect_bounded<T: Clone>(items: &[T], max_items: usize) -> Option<Vec<T>> {
    if items.len() > max_items {
        return None; // Reject oversized input
    }
    Some(items.iter().cloned().collect())
}

// SAFE: Iterative approach avoiding stack overflow
fn factorial_iterative(n: u64) -> u64 {
    (1..=n).product() // No stack overflow
}

// SAFE: Checked array access returning Option
fn get_item_safe(arr: &[i32], index: usize) -> Option<i32> {
    arr.get(index).copied() // Returns None instead of panic
}

// SAFE: Parse with proper error handling
fn parse_config_safe(data: &str) -> Result<i32, std::num::ParseIntError> {
    data.trim().parse::<i32>() // Returns Result, no panic
}

// SAFE: Environment variable with default
fn load_env_var_safe(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

// SAFE: Bounded iteration with counter
fn process_with_limit(items: &mut Vec<i32>, max_iterations: usize) {
    let mut count = 0;
    while !items.is_empty() && count < max_iterations {
        items.pop(); // Actually remove items
        count += 1;
    }
}

// SAFE: Pre-allocated string with capacity
fn build_string_bounded(parts: &[String], max_total: usize) -> Option<String> {
    let total_len: usize = parts.iter().map(|s| s.len()).sum();
    if total_len > max_total {
        return None;
    }

    let mut result = String::with_capacity(total_len);
    for part in parts {
        result.push_str(part);
    }
    Some(result)
}

fn main() {
    match divide_safe(10, 0) {
        Ok(result) => println!("Result: {}", result),
        Err(e) => eprintln!("Error: {}", e),
    }
}
