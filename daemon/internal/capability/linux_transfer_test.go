//go:build linux

package capability

// 本文件在 Linux 真机上对分块传输能力做端到端测试：
// 用 t.TempDir() 建真实文件，走 Registry.Execute 调用能力 Handler，
// 验证 stat / read / write / verify 的正常路径与边界。

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// execLinuxTransfer 通过注册表执行 Linux 传输能力，失败时直接终止测试。
func execLinuxTransfer(t *testing.T, name string, params map[string]any) map[string]any {
	t.Helper()
	reg := NewRegistry()
	res := reg.Execute(name, params)
	if !res.Success {
		t.Fatalf("执行 %s 失败: %s", name, res.Error)
	}
	data, ok := res.Data.(map[string]any)
	if !ok {
		t.Fatalf("执行 %s 返回类型异常: %T", name, res.Data)
	}
	return data
}

// execLinuxTransferErr 通过注册表执行 Linux 传输能力，期望失败并返回错误文本。
func execLinuxTransferErr(t *testing.T, name string, params map[string]any) string {
	t.Helper()
	reg := NewRegistry()
	res := reg.Execute(name, params)
	if res.Success {
		t.Fatalf("执行 %s 期望失败，实际成功: %+v", name, res.Data)
	}
	return res.Error
}

// TestLinuxTransferStat 覆盖 stat 的存在/不存在/目录三种情形。
func TestLinuxTransferStat(t *testing.T) {
	dir := t.TempDir()

	// 1) 不存在的文件：返回 exists=false，不报错。
	missing := filepath.Join(dir, "nope.bin")
	got := execLinuxTransfer(t, "linux.fs.transfer.stat", map[string]any{"path": missing})
	if got["exists"] != false {
		t.Fatalf("不存在文件期望 exists=false，实际 %v", got["exists"])
	}
	if got["size"] != int64(0) {
		t.Fatalf("不存在文件期望 size=0，实际 %v", got["size"])
	}

	// 2) 存在的文件：size 与 sha256 必须正确。
	content := []byte("hello transfer stat")
	file := filepath.Join(dir, "a.txt")
	if err := os.WriteFile(file, content, 0o644); err != nil {
		t.Fatalf("准备文件失败: %v", err)
	}
	sum := sha256.Sum256(content)
	wantSHA := hex.EncodeToString(sum[:])

	got = execLinuxTransfer(t, "linux.fs.transfer.stat", map[string]any{"path": file})
	if got["exists"] != true {
		t.Fatalf("存在文件期望 exists=true，实际 %v", got["exists"])
	}
	if got["size"] != int64(len(content)) {
		t.Fatalf("期望 size=%d，实际 %v", len(content), got["size"])
	}
	if got["sha256"] != wantSHA {
		t.Fatalf("期望 sha256=%s，实际 %v", wantSHA, got["sha256"])
	}
	if got["is_dir"] != false {
		t.Fatalf("期望 is_dir=false，实际 %v", got["is_dir"])
	}
	if got["mtime"] == "" {
		t.Fatalf("期望 mtime 非空")
	}

	// 3) 目录：is_dir=true 且不算 sha256。
	got = execLinuxTransfer(t, "linux.fs.transfer.stat", map[string]any{"path": dir})
	if got["is_dir"] != true {
		t.Fatalf("目录期望 is_dir=true，实际 %v", got["is_dir"])
	}
	if got["sha256"] != "" {
		t.Fatalf("目录期望 sha256 为空，实际 %v", got["sha256"])
	}
}

// TestLinuxTransferWriteReadRoundTrip 分 3 块写入再分块读回，验证逐字节一致。
func TestLinuxTransferWriteReadRoundTrip(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "roundtrip.bin")

	// 构造 2.5 块的数据（块大小 4096），含二进制字节。
	chunkSize := 4096
	original := make([]byte, chunkSize*2+chunkSize/2)
	for i := range original {
		original[i] = byte(i % 251) // 用质数取模，保证覆盖多种字节值
	}

	// 分块写入：首块 truncate=true 清空，后续块按 offset 定位。
	totalWritten := 0
	for offset := 0; offset < len(original); offset += chunkSize {
		end := offset + chunkSize
		if end > len(original) {
			end = len(original)
		}
		part := original[offset:end]
		got := execLinuxTransfer(t, "linux.fs.transfer.write", map[string]any{
			"path":     file,
			"offset":   offset,
			"data":     TransferEncodeBase64(part),
			"truncate": offset == 0,
		})
		if got["written_bytes"] != int64(len(part)) {
			t.Fatalf("offset=%d 期望写入 %d 字节，实际 %v", offset, len(part), got["written_bytes"])
		}
		totalWritten += len(part)
	}

	// 写入后文件大小必须等于原始长度。
	statGot := execLinuxTransfer(t, "linux.fs.transfer.stat", map[string]any{"path": file})
	if statGot["size"] != int64(len(original)) {
		t.Fatalf("写入后期望 size=%d，实际 %v", len(original), statGot["size"])
	}

	// 分块读回：按 4096 循环，直到 eof。
	var rebuilt bytes.Buffer
	offset := int64(0)
	for {
		got := execLinuxTransfer(t, "linux.fs.transfer.read", map[string]any{
			"path":   file,
			"offset": offset,
			"length": chunkSize,
		})
		raw, err := TransferDecodeBase64(got["data"].(string))
		if err != nil {
			t.Fatalf("解码读回数据失败: %v", err)
		}
		// 每块的 chunk_sha256 必须与该块内容一致。
		if got["chunk_sha256"] != TransferBytesSHA256(raw) {
			t.Fatalf("offset=%d 块校验和不符", offset)
		}
		rebuilt.Write(raw)
		offset += int64(len(raw))

		if got["eof"] == true {
			break
		}
		if len(raw) == 0 {
			t.Fatalf("offset=%d 返回空块但 eof=false，会死循环", offset)
		}
	}

	if !bytes.Equal(rebuilt.Bytes(), original) {
		t.Fatalf("读回内容与原文不一致：原文 %d 字节，读回 %d 字节", len(original), rebuilt.Len())
	}

	// verify 应匹配。
	sum := sha256.Sum256(original)
	wantSHA := hex.EncodeToString(sum[:])
	verifyGot := execLinuxTransfer(t, "linux.fs.transfer.verify", map[string]any{
		"path":   file,
		"sha256": wantSHA,
	})
	if verifyGot["match"] != true {
		t.Fatalf("verify 期望 match=true，实际 %v", verifyGot["match"])
	}
}

// TestLinuxTransferReadBoundaries 覆盖 read 的各类边界。
func TestLinuxTransferReadBoundaries(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "bounds.txt")
	content := []byte("0123456789") // 10 字节
	if err := os.WriteFile(file, content, 0o644); err != nil {
		t.Fatalf("准备文件失败: %v", err)
	}

	// 1) offset 超过文件尾：bytes_read=0、eof=true，不报错。
	got := execLinuxTransfer(t, "linux.fs.transfer.read", map[string]any{
		"path": file, "offset": 100, "length": 10,
	})
	if got["bytes_read"] != int64(0) {
		t.Fatalf("越界期望 bytes_read=0，实际 %v", got["bytes_read"])
	}
	if got["eof"] != true {
		t.Fatalf("越界期望 eof=true，实际 %v", got["eof"])
	}
	if got["data"] != "" {
		t.Fatalf("越界期望 data 为空，实际 %v", got["data"])
	}

	// 2) offset 正好等于文件尾：同样返回空块 + eof。
	got = execLinuxTransfer(t, "linux.fs.transfer.read", map[string]any{
		"path": file, "offset": 10, "length": 10,
	})
	if got["bytes_read"] != int64(0) || got["eof"] != true {
		t.Fatalf("offset=文件尾期望 (0,true)，实际 (%v,%v)", got["bytes_read"], got["eof"])
	}

	// 3) length 超过剩余：返回剩余部分并置 eof=true。
	got = execLinuxTransfer(t, "linux.fs.transfer.read", map[string]any{
		"path": file, "offset": 4, "length": 1000,
	})
	if got["bytes_read"] != int64(6) {
		t.Fatalf("期望 bytes_read=6，实际 %v", got["bytes_read"])
	}
	if got["eof"] != true {
		t.Fatalf("期望 eof=true，实际 %v", got["eof"])
	}
	raw, _ := TransferDecodeBase64(got["data"].(string))
	if string(raw) != "456789" {
		t.Fatalf("期望内容 \"456789\"，实际 %q", raw)
	}

	// 4) length<=0 表示读到文件尾。
	got = execLinuxTransfer(t, "linux.fs.transfer.read", map[string]any{
		"path": file, "offset": 0, "length": 0,
	})
	if got["bytes_read"] != int64(10) || got["eof"] != true {
		t.Fatalf("length=0 期望 (10,true)，实际 (%v,%v)", got["bytes_read"], got["eof"])
	}

	// 5) 负 offset 必须报错。
	errText := execLinuxTransferErr(t, "linux.fs.transfer.read", map[string]any{
		"path": file, "offset": -1,
	})
	if errText == "" {
		t.Fatalf("负 offset 期望报错信息非空")
	}

	// 6) length 超单块上限必须报错。
	execLinuxTransferErr(t, "linux.fs.transfer.read", map[string]any{
		"path": file, "length": TransferMaxChunkSize + 1,
	})

	// 7) 目录不能用 read。
	execLinuxTransferErr(t, "linux.fs.transfer.read", map[string]any{"path": dir})

	// 8) 不存在的文件报错。
	execLinuxTransferErr(t, "linux.fs.transfer.read", map[string]any{
		"path": filepath.Join(dir, "missing.txt"),
	})
}

// TestLinuxTransferVerifyMismatch 覆盖 verify 的不匹配与错误输入。
func TestLinuxTransferVerifyMismatch(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "v.txt")
	if err := os.WriteFile(file, []byte("verify me"), 0o644); err != nil {
		t.Fatalf("准备文件失败: %v", err)
	}

	// 1) 错误 sha256 → match=false（不报错，是正常业务结果）。
	got := execLinuxTransfer(t, "linux.fs.transfer.verify", map[string]any{
		"path": file, "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
	})
	if got["match"] != false {
		t.Fatalf("错误 sha256 期望 match=false，实际 %v", got["match"])
	}
	if got["actual_sha256"] == "" {
		t.Fatalf("期望返回 actual_sha256")
	}

	// 2) 大写 sha256 也应匹配（大小写不敏感）。
	sum := sha256.Sum256([]byte("verify me"))
	upper := fmt.Sprintf("%X", sum)
	got = execLinuxTransfer(t, "linux.fs.transfer.verify", map[string]any{
		"path": file, "sha256": upper,
	})
	if got["match"] != true {
		t.Fatalf("大写 sha256 期望 match=true，实际 %v", got["match"])
	}

	// 3) 文件不存在 → 报错。
	execLinuxTransferErr(t, "linux.fs.transfer.verify", map[string]any{
		"path": filepath.Join(dir, "missing"), "sha256": upper,
	})
}

// TestLinuxTransferWriteBoundaries 覆盖 write 的边界。
func TestLinuxTransferWriteBoundaries(t *testing.T) {
	dir := t.TempDir()

	// 1) 负 offset 报错。
	execLinuxTransferErr(t, "linux.fs.transfer.write", map[string]any{
		"path": filepath.Join(dir, "x.bin"), "offset": -1, "data": "",
	})

	// 2) 非法 base64 报错。
	execLinuxTransferErr(t, "linux.fs.transfer.write", map[string]any{
		"path": filepath.Join(dir, "x.bin"), "data": "!!!bad!!!",
	})

	// 3) 缺少 data 报错。
	execLinuxTransferErr(t, "linux.fs.transfer.write", map[string]any{
		"path": filepath.Join(dir, "x.bin"),
	})

	// 4) 单块超上限报错。
	big := make([]byte, TransferMaxChunkSize+1)
	execLinuxTransferErr(t, "linux.fs.transfer.write", map[string]any{
		"path": filepath.Join(dir, "x.bin"), "data": TransferEncodeBase64(big),
	})

	// 5) 断点续传：先写前 5 字节，再从 offset=5 写后 5 字节（truncate=false），
	//    最终内容应为两者拼接，验证「不覆盖已有前缀」。
	file := filepath.Join(dir, "resume.bin")
	execLinuxTransfer(t, "linux.fs.transfer.write", map[string]any{
		"path": file, "offset": 0, "data": TransferEncodeBase64([]byte("01234")), "truncate": true,
	})
	got := execLinuxTransfer(t, "linux.fs.transfer.write", map[string]any{
		"path": file, "offset": 5, "data": TransferEncodeBase64([]byte("56789")), "truncate": false,
	})
	if got["size"] != int64(10) {
		t.Fatalf("续传后期望 size=10，实际 %v", got["size"])
	}
	onDisk, err := os.ReadFile(file)
	if err != nil {
		t.Fatalf("读取文件失败: %v", err)
	}
	if string(onDisk) != "0123456789" {
		t.Fatalf("续传后期望 \"0123456789\"，实际 %q", onDisk)
	}

	// 6) truncate=true 应清空已有内容。
	execLinuxTransfer(t, "linux.fs.transfer.write", map[string]any{
		"path": file, "offset": 0, "data": TransferEncodeBase64([]byte("XY")), "truncate": true,
	})
	onDisk, _ = os.ReadFile(file)
	if string(onDisk) != "XY" {
		t.Fatalf("truncate 后期望 \"XY\"，实际 %q", onDisk)
	}
}

// TestLinuxTransferFileSizeLimit 验证超过 512 MiB 上限时被拒绝。
//
// 为避免真写 512 MiB 数据，这里用「创建稀疏文件 + 断言 stat/read 报错」的方式：
// 稀疏文件在 Linux 上瞬时创建，不占用实际磁盘块。
func TestLinuxTransferFileSizeLimit(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "huge.bin")

	f, err := os.Create(file)
	if err != nil {
		t.Fatalf("创建文件失败: %v", err)
	}
	// 截断到 512 MiB + 1 字节，形成稀疏文件。
	if err := f.Truncate(TransferMaxFileSize + 1); err != nil {
		f.Close()
		t.Skipf("当前文件系统不支持稀疏文件截断，跳过: %v", err)
	}
	if err := f.Close(); err != nil {
		t.Fatalf("关闭文件失败: %v", err)
	}

	info, err := os.Stat(file)
	if err != nil {
		t.Fatalf("stat 失败: %v", err)
	}
	if info.Size() != TransferMaxFileSize+1 {
		t.Fatalf("稀疏文件大小期望 %d，实际 %d", TransferMaxFileSize+1, info.Size())
	}

	// stat 应因超上限报错。
	if errText := execLinuxTransferErr(t, "linux.fs.transfer.stat", map[string]any{"path": file}); errText == "" {
		t.Fatalf("超上限 stat 期望报错信息非空")
	}
	// read 也应因超上限报错。
	if errText := execLinuxTransferErr(t, "linux.fs.transfer.read", map[string]any{"path": file}); errText == "" {
		t.Fatalf("超上限 read 期望报错信息非空")
	}
	// write 写到超上限位置也应报错（offset 已超上限，即使 data 为空）。
	if errText := execLinuxTransferErr(t, "linux.fs.transfer.write", map[string]any{
		"path": file, "offset": TransferMaxFileSize, "data": TransferEncodeBase64([]byte("xx")),
	}); errText == "" {
		t.Fatalf("超上限 write 期望报错信息非空")
	}
}
