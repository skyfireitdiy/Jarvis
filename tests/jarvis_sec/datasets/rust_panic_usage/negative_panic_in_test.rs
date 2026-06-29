// Negative case: panic! in test context
#[test]
fn test_divide_by_zero() {
    let result = divide(10, 0);
    assert!(result.is_err());
}
