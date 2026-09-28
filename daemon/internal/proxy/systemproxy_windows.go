//go:build windows

package proxy

import (
	"net/http"
	"net/url"
	"strings"
	"sync"
	"syscall"
	"unsafe"
)

// 注册表路径与值名（Windows「Internet 选项 → 连接 → 局域网设置」）。
const (
	regPath           = `Software\Microsoft\Windows\CurrentVersion\Internet Settings`
	regValueProxyEnab = "ProxyEnable"
	regValueProxySrv  = "ProxyServer"
	regValueProxySkip = "ProxyOverride"
)

// advapi32 中的注册表 API。用 LazyDLL 动态加载，避免依赖 golang.org/x/sys。
var (
	advapi32          = syscall.NewLazyDLL("advapi32.dll")
	procRegOpenKeyEx  = advapi32.NewProc("RegOpenKeyExW")
	procRegQueryValue = advapi32.NewProc("RegQueryValueExW")
	procRegCloseKey   = advapi32.NewProc("RegCloseKey")
)

// 缓存系统代理配置：注册表读取有系统调用开销，而代理设置变更极少，
// 故进程内缓存一份。缓存的是「原始字符串」，与请求无关。
var (
	sysProxyOnce sync.Once
	sysProxySrv  string
	sysProxySkip string
)

// systemProxyForRequest 依据 Windows 系统代理配置决定请求是否走代理。
// 未启用系统代理时返回 nil（不使用代理）。
func systemProxyForRequest(req *http.Request) (*url.URL, error) {
	sysProxyOnce.Do(loadSystemProxy)

	if sysProxySrv == "" {
		return nil, nil
	}
	// ProxyOverride 等价于 NO_PROXY：命中的主机直连。
	if matchProxyOverride(req.URL.Hostname(), sysProxySkip) {
		return nil, nil
	}
	raw := pickProxyForScheme(sysProxySrv, req.URL.Scheme)
	if raw == "" {
		return nil, nil
	}
	return parseProxyURL(raw)
}

// loadSystemProxy 从注册表读取系统代理配置并写入缓存。
// 任何读取失败都视为「未配置代理」，不返回错误（避免影响正常直连）。
func loadSystemProxy() {
	enable, ok := readRegDWORD(regValueProxyEnab)
	if !ok || enable == 0 {
		return
	}
	srv, ok := readRegString(regValueProxySrv)
	if !ok {
		return
	}
	sysProxySrv = strings.TrimSpace(srv)
	if skip, ok := readRegString(regValueProxySkip); ok {
		sysProxySkip = skip
	}
}

// pickProxyForScheme / parseProxyURL / matchProxyOverride 见 parse.go（跨平台）。

// readRegDWORD 读取指定 DWORD 值。读取失败返回 (0, false)。
func readRegDWORD(name string) (uint32, bool) {
	data, typ, ok := readRegValue(name)
	if !ok || typ != syscall.REG_DWORD || len(data) < 4 {
		return 0, false
	}
	return *(*uint32)(unsafe.Pointer(&data[0])), true
}

// readRegString 读取指定 REG_SZ 值。读取失败返回 ("", false)。
func readRegString(name string) (string, bool) {
	data, typ, ok := readRegValue(name)
	if !ok || (typ != syscall.REG_SZ && typ != syscall.REG_EXPAND_SZ) {
		return "", false
	}
	return syscall.UTF16ToString(bytesToUTF16(data)), true
}

// readRegValue 打开 HKCU 下固定路径并读取一个值，返回原始字节与类型。
func readRegValue(name string) ([]byte, uint32, bool) {
	pathPtr, err := syscall.UTF16PtrFromString(regPath)
	if err != nil {
		return nil, 0, false
	}
	var hKey syscall.Handle
	r, _, _ := procRegOpenKeyEx.Call(
		uintptr(syscall.HKEY_CURRENT_USER),
		uintptr(unsafe.Pointer(pathPtr)),
		0,
		uintptr(syscall.KEY_READ),
		uintptr(unsafe.Pointer(&hKey)),
	)
	if r != 0 { // ERROR_SUCCESS == 0
		return nil, 0, false
	}
	defer procRegCloseKey.Call(uintptr(hKey))

	namePtr, err := syscall.UTF16PtrFromString(name)
	if err != nil {
		return nil, 0, false
	}
	var (
		typ    uint32
		size   uint32
		data   []byte
		regErr uintptr
	)
	// 先查询大小，再据此分配缓冲区。多留 1 个 wchar 余量防止竞态截断。
	for i := 0; i < 2; i++ {
		size = uint32(len(data))
		regErr, _, _ = procRegQueryValue.Call(
			uintptr(hKey),
			uintptr(unsafe.Pointer(namePtr)),
			0,
			uintptr(unsafe.Pointer(&typ)),
			uintptr(unsafe.Pointer(bufPtr(data))),
			uintptr(unsafe.Pointer(&size)),
		)
		if regErr == 0 { // ERROR_SUCCESS
			break
		}
		if regErr != uintptr(syscall.ERROR_MORE_DATA) {
			return nil, 0, false
		}
		data = make([]byte, size+2)
	}
	if len(data) == 0 {
		return nil, 0, false
	}
	return data[:size], typ, true
}

// bufPtr 返回切片首元素指针；空切片返回 nil（对应 API 的 NULL）。
func bufPtr(b []byte) unsafe.Pointer {
	if len(b) == 0 {
		return nil
	}
	return unsafe.Pointer(&b[0])
}

// bytesToUTF16 把 UTF-16LE 字节序列转成 []uint16（供 UTF16ToString 使用）。
func bytesToUTF16(b []byte) []uint16 {
	n := len(b) / 2
	out := make([]uint16, 0, n)
	for i := 0; i < n; i++ {
		out = append(out, *(*uint16)(unsafe.Pointer(&b[i*2])))
	}
	return out
}
