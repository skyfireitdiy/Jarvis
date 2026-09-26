//go:build linux

package capability

import (
	"encoding/base64"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestLinuxFSReadWriteRoundTrip 验证写入后读回内容一致。
func TestLinuxFSReadWriteRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "hello.txt")
	const content = "你好，Jarvis\nsecond line\n"

	res, err := handleLinuxFSWrite(map[string]any{
		"path":    path,
		"content": content,
	})
	if err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	m := res.(map[string]any)
	if m["created"] != true {
		t.Errorf("首次写入应 created=true，实际 %v", m["created"])
	}
	if m["written_bytes"].(int) != len(content) {
		t.Errorf("written_bytes 应为 %d，实际 %v", len(content), m["written_bytes"])
	}

	readRes, err := handleLinuxFSRead(map[string]any{"path": path})
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	rm := readRes.(map[string]any)
	if rm["content"].(string) != content {
		t.Errorf("读回内容不一致:\n期望 %q\n实际 %q", content, rm["content"])
	}
	if rm["is_binary"] != false {
		t.Errorf("文本文件不应判定为二进制，实际 %v", rm["is_binary"])
	}
	if rm["truncated"] != false {
		t.Errorf("小文件不应截断，实际 %v", rm["truncated"])
	}
	if rm["read_bytes"].(int) != len(content) {
		t.Errorf("read_bytes 应为 %d，实际 %v", len(content), rm["read_bytes"])
	}
	if rm["size"].(int64) != int64(len(content)) {
		t.Errorf("size 应为 %d，实际 %v", len(content), rm["size"])
	}
}

// TestLinuxFSWriteAppend 验证追加写入行为。
func TestLinuxFSWriteAppend(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "append.txt")

	if _, err := handleLinuxFSWrite(map[string]any{
		"path":    path,
		"content": "AAA",
	}); err != nil {
		t.Fatalf("首次写入失败: %v", err)
	}

	res, err := handleLinuxFSWrite(map[string]any{
		"path":    path,
		"content": "BBB",
		"append":  true,
	})
	if err != nil {
		t.Fatalf("追加写入失败: %v", err)
	}
	m := res.(map[string]any)
	if m["created"] != false {
		t.Errorf("追加到已存在文件应 created=false，实际 %v", m["created"])
	}
	if m["appended"] != true {
		t.Errorf("appended 应为 true，实际 %v", m["appended"])
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取文件失败: %v", err)
	}
	if string(raw) != "AAABBB" {
		t.Errorf("追加结果应为 AAABBB，实际 %q", string(raw))
	}
}

// TestLinuxFSWriteOverwriteByDefault 验证默认覆盖而非追加。
func TestLinuxFSWriteOverwriteByDefault(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "overwrite.txt")

	if _, err := handleLinuxFSWrite(map[string]any{"path": path, "content": "first"}); err != nil {
		t.Fatalf("首次写入失败: %v", err)
	}
	if _, err := handleLinuxFSWrite(map[string]any{"path": path, "content": "second"}); err != nil {
		t.Fatalf("二次写入失败: %v", err)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取文件失败: %v", err)
	}
	if string(raw) != "second" {
		t.Errorf("默认应覆盖，期望 second，实际 %q", string(raw))
	}
}

// TestLinuxFSWriteCreateDirs 验证 create_dirs 自动创建父目录。
func TestLinuxFSWriteCreateDirs(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "a", "b", "c", "deep.txt")

	// 不开启 create_dirs 时应失败。
	if _, err := handleLinuxFSWrite(map[string]any{"path": path, "content": "x"}); err == nil {
		t.Fatal("父目录不存在且未开启 create_dirs，应返回错误")
	}

	if _, err := handleLinuxFSWrite(map[string]any{
		"path":        path,
		"content":     "deep",
		"create_dirs": true,
	}); err != nil {
		t.Fatalf("开启 create_dirs 后写入失败: %v", err)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取深层文件失败: %v", err)
	}
	if string(raw) != "deep" {
		t.Errorf("内容应为 deep，实际 %q", string(raw))
	}
}

// TestLinuxFSWriteMode 验证 mode 参数解析与生效。
func TestLinuxFSWriteMode(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mode.txt")

	if _, err := handleLinuxFSWrite(map[string]any{
		"path":    path,
		"content": "x",
		"mode":    "0600",
	}); err != nil {
		t.Fatalf("写入失败: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat 失败: %v", err)
	}
	if got := info.Mode().Perm(); got != 0o600 {
		t.Errorf("权限应为 0600，实际 %o", got)
	}

	// 非法 mode 必须报错。
	if _, err := handleLinuxFSWrite(map[string]any{
		"path":    filepath.Join(dir, "bad.txt"),
		"content": "x",
		"mode":    "abc",
	}); err == nil {
		t.Error("非法 mode 应返回错误")
	}

	if _, err := handleLinuxFSWrite(map[string]any{
		"path":    filepath.Join(dir, "bad2.txt"),
		"content": "x",
		"mode":    "0999",
	}); err == nil {
		t.Error("含非法八进制位的 mode 应返回错误")
	}
}

// TestLinuxFSReadOffsetLimit 验证 offset/limit 分段读取与截断标志。
func TestLinuxFSReadOffsetLimit(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "seg.txt")
	const content = "0123456789"

	if _, err := handleLinuxFSWrite(map[string]any{"path": path, "content": content}); err != nil {
		t.Fatalf("写入失败: %v", err)
	}

	res, err := handleLinuxFSRead(map[string]any{
		"path":   path,
		"offset": 2,
		"limit":  3,
	})
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	m := res.(map[string]any)
	if m["content"].(string) != "234" {
		t.Errorf("offset=2 limit=3 应得到 234，实际 %q", m["content"])
	}
	if m["truncated"] != true {
		t.Errorf("还有剩余内容，truncated 应为 true，实际 %v", m["truncated"])
	}
	if m["read_bytes"].(int) != 3 {
		t.Errorf("read_bytes 应为 3，实际 %v", m["read_bytes"])
	}

	// 恰好读完时不应标记截断。
	res2, err := handleLinuxFSRead(map[string]any{
		"path":   path,
		"offset": 7,
		"limit":  3,
	})
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	m2 := res2.(map[string]any)
	if m2["content"].(string) != "789" {
		t.Errorf("应得到 789，实际 %q", m2["content"])
	}
	if m2["truncated"] != false {
		t.Errorf("刚好读完不应截断，实际 %v", m2["truncated"])
	}
}

// TestLinuxFSReadBinaryDetection 验证二进制内容自动转 base64。
func TestLinuxFSReadBinaryDetection(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bin.dat")
	payload := []byte{0x00, 0x01, 0x02, 0xFF, 0xFE}

	if err := os.WriteFile(path, payload, 0o644); err != nil {
		t.Fatalf("准备二进制文件失败: %v", err)
	}

	res, err := handleLinuxFSRead(map[string]any{"path": path})
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	m := res.(map[string]any)
	if m["is_binary"] != true {
		t.Errorf("含 NUL 字节应判定为二进制，实际 %v", m["is_binary"])
	}
	if m["encoding"].(string) != "base64" {
		t.Errorf("二进制内容应报告 base64 编码，实际 %v", m["encoding"])
	}
	decoded, err := base64.StdEncoding.DecodeString(m["content"].(string))
	if err != nil {
		t.Fatalf("返回内容不是合法 base64: %v", err)
	}
	if string(decoded) != string(payload) {
		t.Errorf("base64 解码后内容不一致:\n期望 %v\n实际 %v", payload, decoded)
	}
}

// TestLinuxFSReadBase64Encoding 验证显式指定 base64 编码。
func TestLinuxFSReadBase64Encoding(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "text.txt")
	if _, err := handleLinuxFSWrite(map[string]any{"path": path, "content": "hi"}); err != nil {
		t.Fatalf("写入失败: %v", err)
	}

	res, err := handleLinuxFSRead(map[string]any{"path": path, "encoding": "base64"})
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	m := res.(map[string]any)
	if m["content"].(string) != base64.StdEncoding.EncodeToString([]byte("hi")) {
		t.Errorf("base64 内容不符，实际 %q", m["content"])
	}
	if m["is_binary"] != false {
		t.Errorf("文本内容 is_binary 应为 false，实际 %v", m["is_binary"])
	}
}

// TestLinuxFSWriteBase64Content 验证 base64 内容写入。
func TestLinuxFSWriteBase64Content(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "from64.bin")
	payload := []byte{0xDE, 0xAD, 0xBE, 0xEF}

	if _, err := handleLinuxFSWrite(map[string]any{
		"path":     path,
		"content":  base64.StdEncoding.EncodeToString(payload),
		"encoding": "base64",
	}); err != nil {
		t.Fatalf("写入失败: %v", err)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	if string(raw) != string(payload) {
		t.Errorf("base64 写入结果不一致:\n期望 %v\n实际 %v", payload, raw)
	}

	// 非法 base64 必须报错。
	if _, err := handleLinuxFSWrite(map[string]any{
		"path":     filepath.Join(dir, "bad.bin"),
		"content":  "!!!not-base64!!!",
		"encoding": "base64",
	}); err == nil {
		t.Error("非法 base64 内容应返回错误")
	}
}

// TestLinuxFSListBasic 验证目录列举。
func TestLinuxFSListBasic(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "a.txt"), []byte("a"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "b.txt"), []byte("bb"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, "sub"), 0o755); err != nil {
		t.Fatal(err)
	}

	res, err := handleLinuxFSList(map[string]any{"path": dir})
	if err != nil {
		t.Fatalf("列举失败: %v", err)
	}
	m := res.(map[string]any)
	if m["count"].(int) != 3 {
		t.Errorf("应有 3 个条目，实际 %d", m["count"])
	}
	if m["truncated"] != false {
		t.Errorf("不应截断，实际 %v", m["truncated"])
	}

	entries := m["entries"].([]map[string]any)
	names := map[string]bool{}
	for _, e := range entries {
		names[e["name"].(string)] = true
		if e["mode"].(string) == "" {
			t.Errorf("条目 %v 缺少 mode", e["name"])
		}
		if e["mod_time"].(string) == "" {
			t.Errorf("条目 %v 缺少 mod_time", e["name"])
		}
	}
	for _, want := range []string{"a.txt", "b.txt", "sub"} {
		if !names[want] {
			t.Errorf("缺少条目 %s", want)
		}
	}

	// 校验 sub 被识别为目录。
	for _, e := range entries {
		if e["name"].(string) == "sub" && e["is_dir"] != true {
			t.Error("sub 应被识别为目录")
		}
	}
}

// TestLinuxFSListHidden 验证 show_hidden 开关。
func TestLinuxFSListHidden(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, ".hidden"), []byte("h"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "visible"), []byte("v"), 0o644); err != nil {
		t.Fatal(err)
	}

	// 默认包含隐藏项。
	res, err := handleLinuxFSList(map[string]any{"path": dir})
	if err != nil {
		t.Fatalf("列举失败: %v", err)
	}
	if res.(map[string]any)["count"].(int) != 2 {
		t.Errorf("默认应包含隐藏项，实际 %d", res.(map[string]any)["count"])
	}

	// 关闭后应只剩 1 个。
	res2, err := handleLinuxFSList(map[string]any{"path": dir, "show_hidden": false})
	if err != nil {
		t.Fatalf("列举失败: %v", err)
	}
	if res2.(map[string]any)["count"].(int) != 1 {
		t.Errorf("show_hidden=false 应只剩 1 个，实际 %d", res2.(map[string]any)["count"])
	}
}

// TestLinuxFSListRecursive 验证递归与 max_depth。
func TestLinuxFSListRecursive(t *testing.T) {
	dir := t.TempDir()
	sub := filepath.Join(dir, "sub")
	deep := filepath.Join(sub, "deep")
	if err := os.MkdirAll(deep, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "top.txt"), []byte("t"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(sub, "mid.txt"), []byte("m"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(deep, "bottom.txt"), []byte("b"), 0o644); err != nil {
		t.Fatal(err)
	}

	// 非递归：只有 top.txt 与 sub。
	res, err := handleLinuxFSList(map[string]any{"path": dir})
	if err != nil {
		t.Fatalf("列举失败: %v", err)
	}
	if got := res.(map[string]any)["count"].(int); got != 2 {
		t.Errorf("非递归应有 2 个条目，实际 %d", got)
	}

	// 递归深度 2：dir 层（top.txt、sub）+ sub 层（deep、mid.txt）。
	// 注意 deep 目录本身位于第 2 层，应被列出；deep 内的 bottom.txt 在第 3 层，不列。
	res2, err := handleLinuxFSList(map[string]any{
		"path":      dir,
		"recursive": true,
		"max_depth": 2,
	})
	if err != nil {
		t.Fatalf("递归列举失败: %v", err)
	}
	if got := res2.(map[string]any)["count"].(int); got != 4 {
		t.Errorf("max_depth=2 应有 4 个条目，实际 %d", got)
	}

	// 递归深度 3：再加上 deep 层的 bottom.txt，共 5 个条目。
	res3, err := handleLinuxFSList(map[string]any{
		"path":      dir,
		"recursive": true,
		"max_depth": 3,
	})
	if err != nil {
		t.Fatalf("递归列举失败: %v", err)
	}
	if got := res3.(map[string]any)["count"].(int); got != 5 {
		t.Errorf("max_depth=3 应有 5 个条目，实际 %d", got)
	}
}

// TestLinuxFSListLimit 验证 limit 截断与 truncated 标志。
func TestLinuxFSListLimit(t *testing.T) {
	dir := t.TempDir()
	for _, n := range []string{"1.txt", "2.txt", "3.txt", "4.txt", "5.txt"} {
		if err := os.WriteFile(filepath.Join(dir, n), []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	res, err := handleLinuxFSList(map[string]any{"path": dir, "limit": 2})
	if err != nil {
		t.Fatalf("列举失败: %v", err)
	}
	m := res.(map[string]any)
	if m["count"].(int) != 2 {
		t.Errorf("limit=2 应返回 2 个条目，实际 %d", m["count"])
	}
	if m["truncated"] != true {
		t.Errorf("被截断时 truncated 应为 true，实际 %v", m["truncated"])
	}
}

// TestLinuxFSListSymlink 验证符号链接信息。
func TestLinuxFSListSymlink(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "target.txt")
	link := filepath.Join(dir, "link.txt")
	if err := os.WriteFile(target, []byte("t"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, link); err != nil {
		t.Skipf("当前环境不支持创建符号链接: %v", err)
	}

	res, err := handleLinuxFSList(map[string]any{"path": dir})
	if err != nil {
		t.Fatalf("列举失败: %v", err)
	}
	entries := res.(map[string]any)["entries"].([]map[string]any)
	found := false
	for _, e := range entries {
		if e["name"].(string) == "link.txt" {
			found = true
			if e["symlink_target"] != target {
				t.Errorf("symlink_target 应为 %s，实际 %v", target, e["symlink_target"])
			}
		}
	}
	if !found {
		t.Error("未找到符号链接条目")
	}
}

// TestLinuxFSParameterValidation 覆盖参数校验与错误路径。
func TestLinuxFSParameterValidation(t *testing.T) {
	dir := t.TempDir()
	existing := filepath.Join(dir, "exists.txt")
	if err := os.WriteFile(existing, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		name   string
		fn     func(map[string]any) (any, error)
		params map[string]any
	}{
		{"read 缺 path", handleLinuxFSRead, map[string]any{}},
		{"read path 类型错", handleLinuxFSRead, map[string]any{"path": 123}},
		{"read path 为空", handleLinuxFSRead, map[string]any{"path": "   "}},
		{"read offset 为负", handleLinuxFSRead, map[string]any{"path": existing, "offset": -1}},
		{"read limit 为 0", handleLinuxFSRead, map[string]any{"path": existing, "limit": 0}},
		{"read limit 超上限", handleLinuxFSRead, map[string]any{"path": existing, "limit": 9 << 20}},
		{"read encoding 非法", handleLinuxFSRead, map[string]any{"path": existing, "encoding": "gbk"}},
		{"read 路径不存在", handleLinuxFSRead, map[string]any{"path": filepath.Join(dir, "nope.txt")}},
		{"read 目标是目录", handleLinuxFSRead, map[string]any{"path": dir}},
		{"write 缺 path", handleLinuxFSWrite, map[string]any{"content": "x"}},
		{"write 缺 content", handleLinuxFSWrite, map[string]any{"path": filepath.Join(dir, "w.txt")}},
		{"write content 类型错", handleLinuxFSWrite, map[string]any{"path": filepath.Join(dir, "w.txt"), "content": 1}},
		{"write append 类型错", handleLinuxFSWrite, map[string]any{"path": filepath.Join(dir, "w.txt"), "content": "x", "append": "yes"}},
		{"write create_dirs 类型错", handleLinuxFSWrite, map[string]any{"path": filepath.Join(dir, "w.txt"), "content": "x", "create_dirs": 1}},
		{"write mode 非法", handleLinuxFSWrite, map[string]any{"path": filepath.Join(dir, "w.txt"), "content": "x", "mode": "xyz"}},
		{"write 父目录不存在", handleLinuxFSWrite, map[string]any{"path": filepath.Join(dir, "no", "dir", "f.txt"), "content": "x"}},
		{"list 缺 path", handleLinuxFSList, map[string]any{}},
		{"list path 不存在", handleLinuxFSList, map[string]any{"path": filepath.Join(dir, "nope")}},
		{"list 目标是文件", handleLinuxFSList, map[string]any{"path": existing}},
		{"list max_depth 为 0", handleLinuxFSList, map[string]any{"path": dir, "max_depth": 0}},
		{"list limit 为 0", handleLinuxFSList, map[string]any{"path": dir, "limit": 0}},
		{"list limit 超上限", handleLinuxFSList, map[string]any{"path": dir, "limit": 20000}},
		{"list recursive 类型错", handleLinuxFSList, map[string]any{"path": dir, "recursive": "true"}},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := tc.fn(tc.params)
			if err == nil {
				t.Fatalf("期望返回错误，实际成功")
			}
			if !strings.Contains(err.Error(), "参数") && !strings.Contains(err.Error(), "失败") &&
				!strings.Contains(err.Error(), "路径") && !strings.Contains(err.Error(), "缺少") {
				t.Errorf("错误信息不够明确: %v", err)
			}
		})
	}
}

// TestLinuxFSCapabilitiesRegistered 验证三个能力都已注册且元信息完整。
func TestLinuxFSCapabilitiesRegistered(t *testing.T) {
	reg := NewRegistry()
	for _, name := range []string{"linux.fs.read", "linux.fs.write", "linux.fs.list"} {
		cap, ok := reg.Get(name)
		if !ok {
			t.Fatalf("能力 %s 未注册", name)
		}
		if cap.Platform != PlatformLinux {
			t.Errorf("能力 %s 平台应为 linux，实际 %s", name, cap.Platform)
		}
		if strings.TrimSpace(cap.Description) == "" {
			t.Errorf("能力 %s 缺少 Description", name)
		}
		if cap.Parameters == nil {
			t.Errorf("能力 %s 缺少 Parameters", name)
		}
		if cap.Handler == nil {
			t.Errorf("能力 %s 缺少 Handler", name)
		}
	}
}

// TestParseFileMode 验证八进制权限解析的纯逻辑。
func TestParseFileMode(t *testing.T) {
	ok := map[string]os.FileMode{
		"0644":  0o644,
		"644":   0o644,
		"0755":  0o755,
		"0600":  0o600,
		"0o600": 0o600,
		"0777":  0o777,
	}
	for in, want := range ok {
		got, err := parseFileMode(in)
		if err != nil {
			t.Errorf("parseFileMode(%q) 意外报错: %v", in, err)
			continue
		}
		if got != want {
			t.Errorf("parseFileMode(%q) = %o，期望 %o", in, got, want)
		}
	}

	for _, bad := range []string{"", "abc", "0999", "0x1ff", "99999"} {
		if _, err := parseFileMode(bad); err == nil {
			t.Errorf("parseFileMode(%q) 应报错", bad)
		}
	}
}

// TestIsBinaryContent 验证二进制判定纯逻辑。
func TestIsBinaryContent(t *testing.T) {
	if isBinaryContent([]byte("")) {
		t.Error("空内容不应判定为二进制")
	}
	if isBinaryContent([]byte("hello 世界")) {
		t.Error("合法 UTF-8 文本不应判定为二进制")
	}
	if !isBinaryContent([]byte{0x00}) {
		t.Error("含 NUL 字节应判定为二进制")
	}
	if !isBinaryContent([]byte{0xFF, 0xFE}) {
		t.Error("非法 UTF-8 应判定为二进制")
	}
}

// TestResolveFSEncoding 验证编码参数解析。
func TestResolveFSEncoding(t *testing.T) {
	cases := map[string]string{
		"":       "utf-8",
		"utf-8":  "utf-8",
		"UTF-8":  "utf-8",
		"utf8":   "utf-8",
		"base64": "base64",
		"BASE64": "base64",
	}
	for in, want := range cases {
		params := map[string]any{}
		if in != "" {
			params["encoding"] = in
		}
		got, err := resolveFSEncoding(params, "utf-8")
		if err != nil {
			t.Errorf("resolveFSEncoding(%q) 意外报错: %v", in, err)
			continue
		}
		if got != want {
			t.Errorf("resolveFSEncoding(%q) = %q，期望 %q", in, got, want)
		}
	}

	if _, err := resolveFSEncoding(map[string]any{"encoding": "gbk"}, "utf-8"); err == nil {
		t.Error("不支持的编码应报错")
	}
	if _, err := resolveFSEncoding(map[string]any{"encoding": 1}, "utf-8"); err == nil {
		t.Error("编码类型错误应报错")
	}
}
