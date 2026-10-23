package capability

// 本文件实现跨平台通用的文件「编辑」能力逻辑，语义对齐 Python 侧
// src/jarvis/jarvis_tools/edit_file.py 与 edit_file_by_line.py：
//   - fsEditFile：查找替换（search/replace/replace_all），含引号/换行归一化匹配、
//     唯一性校验（多匹配需 replace_all=true）、写入前备份、失败回滚。
//   - fsEditByLine：按行号闭区间替换（[start_line, end_line]），含行号越界校验、
//     写入前备份、失败回滚。
//
// 与 Linux/Windows 平台能力的关系：Linux（linux.fs.edit / linux.fs.edit_by_line）
// 与 Windows（windows.fs.edit / windows.fs.edit_by_line）均复用本文件的函数，
// 仅注册时 Platform 与能力名不同。
//
// 说明：daemon 面向底层文本编辑，不做 diff 预览（那属于上层终端渲染职责）。

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// fsEditFile 在文件中查找 search 文本并替换为 replace。
//
// 行为对齐 tool_registry 的 edit_file：
//   - search 为空或与 replace 相同视为无效操作，返回错误；
//   - 先精确匹配；失败则做换行/引号归一化后匹配，并从原文截取实际匹配片段；
//   - 匹配到多处且 replace_all=false 时返回错误（需显式 replace_all=true）；
//   - 写入前备份原文件，写入失败时回滚。
//
// 返回 map 含 path/replaced/match_count/encoding 等修改结果。
func fsEditFile(path, search, replace string, replaceAll bool) (map[string]any, error) {
	if search == "" {
		return nil, fmt.Errorf("search 不能为空字符串")
	}
	if search == replace {
		return nil, fmt.Errorf("search 和 replace 内容完全相同，这是一个无效操作（没有实际修改）")
	}

	content, backupPath, err := readFileWithBackup(path)
	if err != nil {
		return nil, err
	}

	cleanup := func() {
		if backupPath != "" {
			_ = os.Remove(backupPath)
		}
	}

	actualSearch := findActualSearchText(content, search)
	if actualSearch == "" {
		cleanup()
		return nil, fmt.Errorf("未找到可匹配的文本：%s", search)
	}

	styledReplace := preserveQuoteStyle(search, actualSearch, replace)
	matchCount := strings.Count(content, actualSearch)

	var newContent string
	switch {
	case matchCount == 1:
		newContent = strings.Replace(content, actualSearch, styledReplace, 1)
	case replaceAll:
		newContent = strings.ReplaceAll(content, actualSearch, styledReplace)
	default:
		cleanup()
		return nil, fmt.Errorf(
			"search 文本匹配到 %d 处，但 replace_all=false，不会自动替换全部匹配", matchCount)
	}

	if err := writeFileWithRollback(path, newContent, backupPath); err != nil {
		cleanup()
		return nil, err
	}
	cleanup()

	return map[string]any{
		"path":        path,
		"replaced":    true,
		"match_count": matchCount,
		"encoding":    "utf-8",
	}, nil
}

// fsEditByLine 用 content 替换文件中闭区间 [startLine, endLine] 的内容。
//
// 行为对齐 tool_registry 的 edit_file_by_line：
//   - startLine/endLine 从 1 开始，endLine 必须 >= startLine；
//   - startLine 超出文件总行数时报错；
//   - 写入前备份原文件，写入失败时回滚。
//
// 返回 map 含 path/replaced/start_line/end_line 等修改结果。
func fsEditByLine(path string, startLine, endLine int, content string) (map[string]any, error) {
	if startLine < 1 {
		return nil, fmt.Errorf("start_line 必须大于等于 1，实际 %d", startLine)
	}
	if endLine < startLine {
		return nil, fmt.Errorf("end_line 必须大于等于 start_line，实际 %d < %d", endLine, startLine)
	}

	orig, backupPath, err := readFileWithBackup(path)
	if err != nil {
		return nil, err
	}

	cleanup := func() {
		if backupPath != "" {
			_ = os.Remove(backupPath)
		}
	}

	lines := strings.SplitAfter(orig, "\n")
	totalLines := len(lines)
	// 文件以换行结尾时，SplitAfter 会产生一个空尾串，不计为独立行。
	if totalLines > 0 && lines[totalLines-1] == "" {
		totalLines--
	}
	if startLine > totalLines {
		cleanup()
		return nil, fmt.Errorf("start_line (%d) 超出文件总行数 (%d)", startLine, totalLines)
	}

	before := strings.Join(lines[:startLine-1], "")
	after := ""
	if endLine < totalLines {
		after = strings.Join(lines[endLine:], "")
	} else if endLine == totalLines {
		// 替换到末行：保留末行之后的空尾串（若有）
		if len(lines) > totalLines {
			after = lines[totalLines]
		}
	}

	replaceContent := content
	if after != "" && !strings.HasSuffix(replaceContent, "\n") {
		replaceContent += "\n"
	}

	newContent := before + replaceContent + after

	if err := writeFileWithRollback(path, newContent, backupPath); err != nil {
		cleanup()
		return nil, err
	}
	cleanup()

	return map[string]any{
		"path":       path,
		"replaced":   true,
		"start_line": startLine,
		"end_line":   endLine,
		"encoding":   "utf-8",
	}, nil
}

// readFileWithBackup 读取文件内容并在原文件旁创建 .bak 备份。
//
// 文件不存在时返回空内容且 backupPath 为空（与 tool_registry 一致：编辑目标通常是已存在文件）。
// 备份失败不影响主流程（backupPath 为空，后续不执行回滚）。
func readFileWithBackup(path string) (content string, backupPath string, err error) {
	data, readErr := os.ReadFile(path)
	if readErr != nil {
		if os.IsNotExist(readErr) {
			return "", "", nil
		}
		return "", "", fmt.Errorf("读取文件 %s 失败: %w", path, readErr)
	}
	content = string(data)

	abs, absErr := filepath.Abs(path)
	if absErr != nil {
		abs = path
	}
	backupPath = abs + ".bak"
	if copyErr := copyFile(path, backupPath); copyErr != nil {
		// 备份失败不影响主流程（无回滚能力）
		backupPath = ""
	}
	return content, backupPath, nil
}

// writeFileWithRollback 写入文件，失败时尝试用备份回滚。
func writeFileWithRollback(path, content, backupPath string) error {
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		if backupPath != "" {
			_ = copyFile(backupPath, path)
			_ = os.Remove(backupPath)
		}
		return fmt.Errorf("写入文件 %s 失败: %w", path, err)
	}
	return nil
}

// copyFile 复制文件（用于备份与回滚）。
func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0o644)
}

// normalizeLineEndings 统一换行符为 \n，便于进行保守的等价匹配。
func normalizeLineEndings(text string) string {
	text = strings.ReplaceAll(text, "\r\n", "\n")
	return strings.ReplaceAll(text, "\r", "\n")
}

// normalizeQuotes 归一化常见引号风格，便于在文件中定位实际匹配文本。
func normalizeQuotes(text string) string {
	replacer := strings.NewReplacer(
		"“", "\"",
		"”", "\"",
		"‘", "'",
		"’", "'",
	)
	return replacer.Replace(text)
}

// findActualSearchText 查找文件中的实际匹配文本。
//
// 先尝试精确匹配；若失败，再尝试基于换行和引号归一化后的定位，
// 并从原始文件内容中截取实际匹配片段。找不到返回空字符串。
//
// 注意：归一化（弯引号→直引号）会改变文本字节长度，因此必须按
// rune（Unicode 码点）定位与截取，避免字节错位。
func findActualSearchText(content, searchText string) string {
	if searchText == "" {
		return searchText
	}
	if strings.Contains(content, searchText) {
		return searchText
	}

	contentRunes := []rune(content)
	searchRunes := []rune(searchText)

	normalizedContent := normalizeQuotes(normalizeLineEndings(content))
	normalizedSearch := normalizeQuotes(normalizeLineEndings(searchText))

	idx := runeIndex([]rune(normalizedContent), []rune(normalizedSearch))
	if idx == -1 {
		return ""
	}
	end := idx + len(searchRunes)
	if end > len(contentRunes) {
		end = len(contentRunes)
	}
	return string(contentRunes[idx:end])
}

// runeIndex 在 base 中查找 sub 首次出现的起始下标（按 rune 计），找不到返回 -1。
func runeIndex(base, sub []rune) int {
	if len(sub) == 0 {
		return 0
	}
	if len(sub) > len(base) {
		return -1
	}
	for i := 0; i+len(sub) <= len(base); i++ {
		match := true
		for j := range sub {
			if base[i+j] != sub[j] {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}

// preserveQuoteStyle 当 search 因引号归一化匹配到实际文本时，
// 尽量保持实际文本中的弯引号风格（对齐 tool_registry 的 preserve_quote_style）。
func preserveQuoteStyle(searchText, actualSearchText, replaceText string) string {
	if searchText == actualSearchText {
		return replaceText
	}

	hasCurlyDouble := strings.ContainsAny(actualSearchText, "“”")
	hasCurlySingle := strings.ContainsAny(actualSearchText, "‘’")

	styled := replaceText
	if hasCurlyDouble {
		styled = applyCurlyDoubleQuotes(styled)
	}
	if hasCurlySingle {
		styled = applyCurlySingleQuotes(styled)
	}
	return styled
}

// applyCurlyDoubleQuotes 将直双引号转换为弯双引号（对齐 tool_registry）。
func applyCurlyDoubleQuotes(text string) string {
	runes := []rune(text)
	out := make([]rune, 0, len(runes))
	for i, ch := range runes {
		if ch == '"' {
			if isOpeningQuoteContext(runes, i) {
				out = append(out, '“')
			} else {
				out = append(out, '”')
			}
		} else {
			out = append(out, ch)
		}
	}
	return string(out)
}

// applyCurlySingleQuotes 将直单引号转换为弯单引号，同时保留常见缩写中的撇号。
func applyCurlySingleQuotes(text string) string {
	runes := []rune(text)
	out := make([]rune, 0, len(runes))
	for i, ch := range runes {
		if ch != '\'' {
			out = append(out, ch)
			continue
		}
		var prev, next rune
		if i > 0 {
			prev = runes[i-1]
		}
		if i < len(runes)-1 {
			next = runes[i+1]
		}
		if isAlpha(prev) && isAlpha(next) {
			out = append(out, '’')
			continue
		}
		if isOpeningQuoteContext(runes, i) {
			out = append(out, '‘')
		} else {
			out = append(out, '’')
		}
	}
	return string(out)
}

// isOpeningQuoteContext 判断当前位置的引号是否处于开引号上下文。
func isOpeningQuoteContext(runes []rune, index int) bool {
	if index == 0 {
		return true
	}
	prev := runes[index-1]
	switch prev {
	case ' ', '\t', '\n', '\r', '(', '[', '{', '—', '–':
		return true
	}
	return false
}

// isAlpha 判断 rune 是否为字母（ASCII 字母即可，与 tool_registry 的 isalpha 语义一致）。
func isAlpha(r rune) bool {
	return (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z')
}
