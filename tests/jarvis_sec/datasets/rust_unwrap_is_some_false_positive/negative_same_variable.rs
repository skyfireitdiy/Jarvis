// Negative case: is_some correctly protects the unwrap on the same variable
// The is_some check and unwrap are on the same variable, so filtering is correct.

fn process(opt: Option<i32>) -> i32 {
    if opt.is_some() {
        // SAFE: is_some checks the same variable as unwrap
        opt.unwrap()
    } else {
        0
    }
}

fn main() {
    let result = process(Some(42));
    println!("result: {}", result);
}
