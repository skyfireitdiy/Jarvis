// Positive case: unchecked math operations bypass overflow checks
// unchecked_add, unchecked_sub, unchecked_mul, unchecked_shl, unchecked_shr
// These are unsafe functions that can cause undefined behavior on overflow.
// The checker should detect these as unsafe operations beyond just the unsafe block.

fn add_unchecked(a: u32, b: u32) -> u32 {
    unsafe { a.unchecked_add(b) }
}

fn sub_unchecked(a: u32, b: u32) -> u32 {
    unsafe { a.unchecked_sub(b) }
}

fn mul_unchecked(a: u32, b: u32) -> u32 {
    unsafe { a.unchecked_mul(b) }
}

fn shift_unchecked(a: u32, b: u32) -> u32 {
    unsafe { a.unchecked_shl(b) }
}

fn main() {
    let result = add_unchecked(u32::MAX, 1);
    println!("result: {}", result);
}
