// Negative case: unwrap correctly protected by match
// The unwrap IS inside the Some branch, so filtering is correct.

fn process(opt: Option<i32>) -> i32 {
    match opt {
        Some(val) => {
            // SAFE: unwrap is inside the Some branch
            opt.unwrap()
        }
        None => 0,
    }
}

fn main() {
    let result = process(Some(42));
    println!("result: {}", result);
}
