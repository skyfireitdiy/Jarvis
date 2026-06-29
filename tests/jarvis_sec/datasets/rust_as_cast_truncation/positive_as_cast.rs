// Positive case: as-cast causing data truncation
// Using `as` to cast between numeric types can silently truncate data.
// This is especially dangerous when casting from larger to smaller types,
// or from signed to unsigned (and vice versa).

fn process_large_id(id: u64) -> u32 {
    // VULNERABLE: truncation - upper 32 bits lost
    let truncated = id as u32;
    truncated
}

fn signed_to_unsigned(value: i32) -> u32 {
    // VULNERABLE: negative values become large positive numbers
    let converted = value as u32;
    converted
}

fn pointer_as_int(ptr: *const u8) -> usize {
    // VULNERABLE: pointer may not fit in usize on 32-bit
    let addr = ptr as usize;
    addr
}

fn main() {
    let big_id: u64 = 0x1_0000_0000 + 42;
    let result = process_large_id(big_id);
    println!("result: {}", result); // prints 42, not the full id
}
