// Negative case: safe type conversions
// Using try_into() or explicit bounds checking before conversion.

use std::convert::TryInto;

fn process_large_id(id: u64) -> Option<u32> {
    // SAFE: try_into returns None on overflow
    id.try_into().ok()
}

fn signed_to_unsigned(value: i32) -> Option<u32> {
    // SAFE: explicit check for negative values
    if value < 0 {
        return None;
    }
    Some(value as u32) // safe because we checked value >= 0
}

fn main() {
    if let Some(result) = process_large_id(42) {
        println!("result: {}", result);
    }
}
