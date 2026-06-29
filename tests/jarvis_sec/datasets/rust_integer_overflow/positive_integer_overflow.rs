// Positive case: integer overflow in release mode
// In Rust, integer overflow wraps in release mode without panic.
// This can lead to security vulnerabilities when used in:
// - buffer size calculations
// - financial calculations
// - loop bounds
// The checker should detect wrapping arithmetic that may overflow.

fn calculate_buffer_size(count: u32, element_size: u32) -> usize {
    // VULNERABLE: overflow wraps in release, could allocate small buffer
    let total = count * element_size;
    total as usize
}

fn process_payment(amount: u64, multiplier: u64) -> u64 {
    // VULNERABLE: financial calculation overflow
    let total = amount * multiplier;
    total
}

fn main() {
    // This will wrap to a small number in release mode
    let size = calculate_buffer_size(u32::MAX, 2);
    println!("buffer size: {}", size);
}
