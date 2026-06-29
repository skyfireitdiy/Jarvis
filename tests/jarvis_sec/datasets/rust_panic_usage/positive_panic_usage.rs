// Positive case: panic! usage in production code
fn divide(a: i32, b: i32) -> i32 {
    if b == 0 {
        panic!("division by zero");
    }
    a / b
}

fn main() {
    let result = divide(10, 0);
}
