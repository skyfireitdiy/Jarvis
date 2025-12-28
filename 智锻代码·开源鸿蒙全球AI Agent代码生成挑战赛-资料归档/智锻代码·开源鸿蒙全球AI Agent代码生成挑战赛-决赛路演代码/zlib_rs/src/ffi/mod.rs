//! FFI 接口模块
//!
//! 本模块提供与 C 库兼容的 FFI 接口

pub(crate) mod types;

use crate::adler32::combine::adler32_combine as adler32_combine_impl;
use adler::Adler32;

/// 计算 Adler-32 校验和
///
/// 实现与 zlib 的 adler32() 函数语义等价的 Adler-32 校验和计算。
/// 支持增量计算：可以传入之前计算的校验和值，继续计算新数据的校验和。
///
/// # 参数
/// - `adler`: 初始 Adler-32 校验和值（首次计算时传 0 或 1）
/// - `buf`: 数据缓冲区指针（可为空指针）
/// - `len`: 数据长度（字节数）
///
/// # 返回值
/// - 计算后的 Adler-32 校验和
/// - 当 `buf` 为空指针时，返回初始值 1
///
/// # Safety
/// - 调用者必须确保 `buf` 指向的内存区域至少有 `len` 字节可读
/// - 当 `buf` 为空指针时，函数安全返回初始值
/// 计算 Adler-32 校验和（带 z_size_t 长度参数）
///
/// 实现与 zlib 的 adler32_z() 函数语义等价的 Adler-32 校验和计算。
/// 与 `adler32` 的区别在于使用 `usize` 作为长度类型，支持更大的数据块。
///
/// # 参数
/// - `adler`: 初始 Adler-32 校验和值（首次计算时传 0 或 1）
/// - `buf`: 数据缓冲区指针（可为空指针）
/// - `len`: 数据长度（字节数，使用 usize 类型）
///
/// # 返回值
/// - 计算后的 Adler-32 校验和
/// - 当 `buf` 为空指针时，返回初始值 1
///
/// # Safety
/// - 调用者必须确保 `buf` 指向的内存区域至少有 `len` 字节可读
/// - 当 `buf` 为空指针时，函数安全返回初始值
#[no_mangle]
pub unsafe extern "C" fn adler32_z(adler: u32, buf: *const u8, len: usize) -> u32 {
    // 空指针检查：zlib 行为是返回初始值 1
    if buf.is_null() {
        return 1;
    }

    // 零长度检查：直接返回原始校验和
    if len == 0 {
        return adler;
    }

    // 将原始指针转换为切片（unsafe 操作）
    let slice = unsafe { std::slice::from_raw_parts(buf, len) };

    // 使用 adler crate 计算校验和
    // 如果 adler 为 0，使用默认初始值 1
    let initial = if adler == 0 { 1 } else { adler };

    // 创建 Adler32 计算器并更新数据
    let mut hasher = Adler32::from_checksum(initial);
    hasher.write_slice(slice);
    hasher.checksum()
}

#[no_mangle]
pub unsafe extern "C" fn adler32(adler: u32, buf: *const u8, len: u32) -> u32 {
    // 空指针检查：zlib 行为是返回初始值 1
    if buf.is_null() {
        return 1;
    }

    // 零长度检查：直接返回原始校验和
    if len == 0 {
        return adler;
    }

    // 将原始指针转换为切片（unsafe 操作）
    let slice = unsafe { std::slice::from_raw_parts(buf, len as usize) };

    // 使用 adler crate 计算校验和
    // 如果 adler 为 0，使用默认初始值 1
    let initial = if adler == 0 { 1 } else { adler };

    // 创建 Adler32 计算器并更新数据
    let mut hasher = Adler32::from_checksum(initial);
    hasher.write_slice(slice);
    hasher.checksum()
}

/// 合并两个 Adler-32 校验和
///
/// 实现与 zlib 的 adler32_combine() 函数语义等价的校验和合并。
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
#[no_mangle]
pub extern "C" fn adler32_combine(adler1: u32, adler2: u32, len2: i64) -> u32 {
    adler32_combine_impl(adler1, adler2, len2)
}

/// 合并两个 Adler-32 校验和（64位长度版本）
///
/// 实现与 zlib 的 adler32_combine64() 函数语义等价的校验和合并。
/// 与 `adler32_combine` 功能相同，使用 64 位长度参数。
///
/// # 参数
/// - `adler1`: 第一段数据的 Adler-32 校验和
/// - `adler2`: 第二段数据的 Adler-32 校验和
/// - `len2`: 第二段数据的长度（64位有符号整数）
///
/// # 返回值
/// - 合并后的 Adler-32 校验和
/// - 如果 `len2` 为负数，返回 0xffffffff 作为调试线索
#[no_mangle]
pub extern "C" fn adler32_combine64(adler1: u32, adler2: u32, len2: i64) -> u32 {
    adler32_combine_impl(adler1, adler2, len2)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 测试空指针返回初始值 1
    #[test]
    fn test_null_pointer_returns_initial() {
        let result = unsafe { adler32(0, std::ptr::null(), 0) };
        assert_eq!(result, 1);

        let result = unsafe { adler32(100, std::ptr::null(), 100) };
        assert_eq!(result, 1);
    }

    /// 测试零长度返回原始校验和
    #[test]
    fn test_zero_length_returns_original() {
        let buf = [1u8, 2, 3];
        let result = unsafe { adler32(12345, buf.as_ptr(), 0) };
        assert_eq!(result, 12345);
    }

    /// 测试基本计算：空数据返回初始值
    #[test]
    fn test_empty_data() {
        let buf: [u8; 0] = [];
        let result = unsafe { adler32(1, buf.as_ptr(), 0) };
        assert_eq!(result, 1);
    }

    /// 测试单字节计算
    #[test]
    fn test_single_byte() {
        // 对于单字节 'a' (0x61 = 97)
        // s1 = 1 + 97 = 98
        // s2 = 0 + 98 = 98
        // result = (s2 << 16) | s1 = (98 << 16) | 98 = 0x00620062
        let buf = [b'a'];
        let result = unsafe { adler32(1, buf.as_ptr(), 1) };
        assert_eq!(result, 0x00620062);
    }

    /// 测试多字节计算
    #[test]
    fn test_multiple_bytes() {
        // "abc" 的 Adler-32
        // 初始: s1 = 1, s2 = 0
        // 'a' (97): s1 = 1 + 97 = 98, s2 = 0 + 98 = 98
        // 'b' (98): s1 = 98 + 98 = 196, s2 = 98 + 196 = 294
        // 'c' (99): s1 = 196 + 99 = 295, s2 = 294 + 295 = 589
        // result = (589 << 16) | 295 = 0x024d0127
        let buf = b"abc";
        let result = unsafe { adler32(1, buf.as_ptr(), 3) };
        assert_eq!(result, 0x024d0127);
    }

    /// 测试增量计算（连续调用）
    #[test]
    fn test_incremental_calculation() {
        // 分两次计算 "abc"
        let buf1 = b"a";
        let adler1 = unsafe { adler32(1, buf1.as_ptr(), 1) };

        let buf2 = b"bc";
        let result = unsafe { adler32(adler1, buf2.as_ptr(), 2) };

        // 应该与一次性计算 "abc" 结果相同
        let buf_full = b"abc";
        let expected = unsafe { adler32(1, buf_full.as_ptr(), 3) };
        assert_eq!(result, expected);
    }

    /// 测试较长数据
    #[test]
    fn test_longer_data() {
        let buf = b"Hello, World!";
        let result = unsafe { adler32(1, buf.as_ptr(), buf.len() as u32) };
        // 验证结果非零且格式有效
        assert_ne!(result, 0);
        assert_ne!(result, 1);
    }

    /// 测试全零数据
    #[test]
    fn test_zero_data() {
        let buf = [0u8; 10];
        let result = unsafe { adler32(1, buf.as_ptr(), 10) };
        // s1 = 1 + 0*10 = 1
        // s2 = 0 + 1*10 = 10
        // result = (10 << 16) | 1 = 0x000a0001
        assert_eq!(result, 0x000a0001);
    }

    /// 测试全 0xFF 数据
    #[test]
    fn test_max_byte_data() {
        let buf = [0xFFu8; 5];
        let result = unsafe { adler32(1, buf.as_ptr(), 5) };
        // 验证结果有效
        assert_ne!(result, 0);
    }

    /// 测试初始值为 0 时的行为（应等同于 1）
    #[test]
    fn test_initial_zero_equals_one() {
        let buf = b"test";
        let result_with_zero = unsafe { adler32(0, buf.as_ptr(), 4) };
        let result_with_one = unsafe { adler32(1, buf.as_ptr(), 4) };
        // zlib 中 adler32(0, buf, len) 等同于 adler32(1, buf, len)
        assert_eq!(result_with_zero, result_with_one);
    }

    /// 测试大缓冲区
    #[test]
    fn test_large_buffer() {
        let buf = vec![0x55u8; 65536];
        let result = unsafe { adler32(1, buf.as_ptr(), buf.len() as u32) };
        // 验证结果有效
        assert_ne!(result, 0);
    }
}
