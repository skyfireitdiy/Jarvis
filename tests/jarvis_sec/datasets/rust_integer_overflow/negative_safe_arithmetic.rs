// Negative case: safe arithmetic with checked/saturating operations
// Using checked_add, saturating_add, or wrapping_add explicitly
// shows the developer is aware of overflow behavior.

fn calculate_buffer_size(count: u32, element_size: u32) -> Option<usize> {
    // SAFE: checked multiplication, returns None on overflow
    count.checked_mul(element_size).map(|v| v as usize)
}

fn process_payment(amount: u64, multiplier: u64) -> u64 {
    // SAFE: saturating multiplication, caps at max
    amount.saturating_mul(multiplier)
}

fn main() {
    if let Some(size) = calculate_buffer_size(100, 4) {
        println!("buffer size: {}", size);
    }
}
