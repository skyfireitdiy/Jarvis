// Positive case: get_unchecked not specifically detected
// The checker only reports the unsafe block, not get_unchecked as a distinct
// vulnerability pattern. get_unchecked bypasses bounds checking and can
// cause undefined behavior if the index is out of bounds.
// The checker should detect get_unchecked specifically, not just the unsafe block.

fn access_slice(data: &[u8], index: usize) -> u8 {
    unsafe {
        // VULNERABLE: get_unchecked bypasses bounds checking
        // Checker only reports 'unsafe' pattern, not 'get_unchecked'
        *data.get_unchecked(index)
    }
}

fn access_mut(data: &mut [u8], index: usize) -> u8 {
    unsafe {
        // VULNERABLE: get_unchecked_mut bypasses bounds checking
        *data.get_unchecked_mut(index)
    }
}

fn main() {
    let data = [1u8, 2, 3, 4, 5];
    let val = access_slice(&data, 2);
    println!("val: {}", val);
}
