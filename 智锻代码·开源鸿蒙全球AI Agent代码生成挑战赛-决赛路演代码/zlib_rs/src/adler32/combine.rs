//! Adler-32 校验和合并功能
//!
//! 本模块实现了将两个 Adler-32 校验和合并的功能

/// Adler-32 算法使用的模数（最大的小于 65536 的素数）
const BASE: u32 = 65521;

/// 合并两个 Adler-32 校验和（内部实现）
///
/// 将两段数据的 Adler-32 校验和合并为一个，无需重新计算整个数据流的校验和。
///
/// # 参数
/// - `adler1`: 第一段数据的 Adler-32 校验和
/// - `adler2`: 第二段数据的 Adler-32 校验和
/// - `len2`: 第二段数据的长度（字节数）
///
/// # 返回值
/// - 合并后的 Adler-32 校验和
/// - 如果 `len2` 为负数，返回 0xffffffff 作为调试线索
fn adler32_combine_(adler1: u32, adler2: u32, len2: i64) -> u32 {
    // 对于负数长度，返回无效的 adler32 值作为调试线索
    if len2 < 0 {
        return 0xffffffff;
    }

    // 对 len2 执行 MOD63 操作（等价于 len2 %= BASE）
    let rem = (len2 as u64 % BASE as u64) as u32;

    // 提取 adler1 的低 16 位
    let mut sum1 = adler1 & 0xffff;

    // 计算 sum2 = rem * sum1，然后对 BASE 取模
    let mut sum2 = ((rem as u64 * sum1 as u64) % BASE as u64) as u32;

    // sum1 += (adler2 低16位) + BASE - 1
    sum1 += (adler2 & 0xffff) + BASE - 1;

    // sum2 += (adler1 高16位) + (adler2 高16位) + BASE - rem
    sum2 += ((adler1 >> 16) & 0xffff) + ((adler2 >> 16) & 0xffff) + BASE - rem;

    // 规范化 sum1：如果 >= BASE 则减去 BASE（最多两次）
    if sum1 >= BASE {
        sum1 -= BASE;
    }
    if sum1 >= BASE {
        sum1 -= BASE;
    }

    // 规范化 sum2：如果 >= 2*BASE 则减去 2*BASE，然后如果 >= BASE 则减去 BASE
    if sum2 >= BASE << 1 {
        sum2 -= BASE << 1;
    }
    if sum2 >= BASE {
        sum2 -= BASE;
    }

    // 组合结果：低16位是 sum1，高16位是 sum2
    sum1 | (sum2 << 16)
}

/// 合并两个 Adler-32 校验和（公共接口）
///
/// 这是 `adler32_combine_` 的公共包装函数，提供与 C 库兼容的接口。
///
/// # 参数
/// - `adler1`: 第一段数据的 Adler-32 校验和
/// - `adler2`: 第二段数据的 Adler-32 校验和
/// - `len2`: 第二段数据的长度（字节数）
///
/// # 返回值
/// - 合并后的 Adler-32 校验和
/// - 如果 `len2` 为负数，返回 0xffffffff 作为调试线索
pub fn adler32_combine(adler1: u32, adler2: u32, len2: i64) -> u32 {
    adler32_combine_(adler1, adler2, len2)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 测试负数长度返回 0xffffffff
    #[test]
    fn test_negative_len_returns_invalid() {
        assert_eq!(adler32_combine_(0, 0, -1), 0xffffffff);
        assert_eq!(adler32_combine_(1, 1, -100), 0xffffffff);
        assert_eq!(
            adler32_combine_(0x12345678, 0x87654321, i64::MIN),
            0xffffffff
        );
    }

    /// 测试零长度
    #[test]
    fn test_zero_len() {
        // len2 = 0 时，rem = 0
        // sum1 = adler1 & 0xffff
        // sum2 = 0 (因为 rem * sum1 = 0)
        // sum1 += (adler2 & 0xffff) + BASE - 1
        // sum2 += (adler1 >> 16) + (adler2 >> 16) + BASE - 0
        let result = adler32_combine_(1, 1, 0);
        // 验证结果有效（非 0xffffffff）
        assert_ne!(result, 0xffffffff);
    }

    /// 测试初始 Adler-32 值（1）的合并
    #[test]
    fn test_initial_adler_values() {
        // Adler-32 的初始值是 1（sum1=1, sum2=0）
        // 合并两个初始值
        let result = adler32_combine_(1, 1, 0);
        assert_ne!(result, 0xffffffff);
    }

    /// 测试典型值
    #[test]
    fn test_typical_values() {
        // 使用一些典型的校验和值进行测试
        let adler1: u32 = 0x00010001; // sum2=1, sum1=1
        let adler2: u32 = 0x00020002; // sum2=2, sum1=2
        let len2: i64 = 10;

        let result = adler32_combine_(adler1, adler2, len2);
        // 验证结果有效
        assert_ne!(result, 0xffffffff);
        // 验证结果的格式正确（高低16位都在有效范围内）
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试边界值：len2 等于 BASE
    #[test]
    fn test_len_equals_base() {
        let result = adler32_combine_(0x00010001, 0x00010001, BASE as i64);
        assert_ne!(result, 0xffffffff);
        // rem = BASE % BASE = 0
        // 验证结果格式正确
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试边界值：len2 大于 BASE
    #[test]
    fn test_len_greater_than_base() {
        let result = adler32_combine_(0x00010001, 0x00010001, BASE as i64 + 100);
        assert_ne!(result, 0xffffffff);
        // 验证结果格式正确
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试大数值
    #[test]
    fn test_large_values() {
        // 测试接近最大有效 Adler-32 值的情况
        let max_adler = (BASE - 1) | ((BASE - 1) << 16);
        let result = adler32_combine_(max_adler, max_adler, 1000);
        assert_ne!(result, 0xffffffff);
        // 验证结果格式正确
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试 len2 为 i64::MAX
    #[test]
    fn test_max_len() {
        let result = adler32_combine_(1, 1, i64::MAX);
        assert_ne!(result, 0xffffffff);
        // 验证结果格式正确
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试零值 adler
    #[test]
    fn test_zero_adler_values() {
        let result = adler32_combine_(0, 0, 100);
        assert_ne!(result, 0xffffffff);
    }

    /// 测试 sum1 需要减两次 BASE 的边界情况
    #[test]
    fn test_sum1_double_reduction() {
        // 构造一个使 sum1 需要减两次 BASE 的情况
        // sum1 = (adler1 & 0xffff) + (adler2 & 0xffff) + BASE - 1
        // 需要 sum1 >= 2 * BASE
        // 即 (adler1 & 0xffff) + (adler2 & 0xffff) >= BASE + 1
        let adler1 = BASE - 1; // sum1 部分接近 BASE
        let adler2 = BASE - 1; // sum1 部分接近 BASE
        let result = adler32_combine_(adler1, adler2, 0);
        assert_ne!(result, 0xffffffff);
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    // ========== adler32_combine 公共接口测试 ==========

    /// 测试 adler32_combine 与 adler32_combine_ 行为一致
    #[test]
    fn test_adler32_combine_wrapper_consistency() {
        // 验证公共接口与内部实现行为一致
        assert_eq!(adler32_combine(1, 1, 0), adler32_combine_(1, 1, 0));
        assert_eq!(adler32_combine(0, 0, -1), adler32_combine_(0, 0, -1));
        assert_eq!(
            adler32_combine(0x12345678, 0x87654321, 1000),
            adler32_combine_(0x12345678, 0x87654321, 1000)
        );
    }

    /// 测试 adler32_combine 负数长度返回 0xffffffff
    #[test]
    fn test_adler32_combine_negative_len() {
        assert_eq!(adler32_combine(0, 0, -1), 0xffffffff);
        assert_eq!(adler32_combine(1, 1, -100), 0xffffffff);
        assert_eq!(
            adler32_combine(0x12345678, 0x87654321, i64::MIN),
            0xffffffff
        );
    }

    /// 测试 adler32_combine 零长度
    #[test]
    fn test_adler32_combine_zero_len() {
        let result = adler32_combine(1, 1, 0);
        assert_ne!(result, 0xffffffff);
    }

    /// 测试 adler32_combine 典型值
    #[test]
    fn test_adler32_combine_typical_values() {
        let adler1: u32 = 0x00010001;
        let adler2: u32 = 0x00020002;
        let len2: i64 = 10;
        let result = adler32_combine(adler1, adler2, len2);
        assert_ne!(result, 0xffffffff);
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试 adler32_combine 边界值：len2 等于 BASE
    #[test]
    fn test_adler32_combine_len_equals_base() {
        let result = adler32_combine(0x00010001, 0x00010001, BASE as i64);
        assert_ne!(result, 0xffffffff);
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试 adler32_combine 大数值
    #[test]
    fn test_adler32_combine_large_values() {
        let max_adler = (BASE - 1) | ((BASE - 1) << 16);
        let result = adler32_combine(max_adler, max_adler, 1000);
        assert_ne!(result, 0xffffffff);
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }

    /// 测试 adler32_combine len2 为 i64::MAX
    #[test]
    fn test_adler32_combine_max_len() {
        let result = adler32_combine(1, 1, i64::MAX);
        assert_ne!(result, 0xffffffff);
        assert!((result & 0xffff) < BASE);
        assert!((result >> 16) < BASE);
    }
}
