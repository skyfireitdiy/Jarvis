// Negative case: safe checked math operations
// Using checked_add, checked_sub etc which return Option and handle overflow.

fn add_checked(a: u32, b: u32) -> Option<u32> {
    a.checked_add(b)
}

fn sub_checked(a: u32, b: u32) -> Option<u32> {
    a.checked_sub(b)
}

fn mul_checked(a: u32, b: u32) -> Option<u32> {
    a.checked_mul(b)
}

fn main() {
    if let Some(result) = add_checked(100, 200) {
        println!("result: {}", result);
    } else {
        println!("overflow occurred");
    }
}
