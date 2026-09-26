package capability

import "runtime"

// Current 返回当前运行平台；未知平台返回 PlatformAny。
func Current() Platform {
	switch runtime.GOOS {
	case "windows":
		return PlatformWindows
	case "linux":
		return PlatformLinux
	case "darwin":
		return PlatformDarwin
	default:
		return PlatformAny
	}
}

// Matches 判断能力声明的平台是否适用于当前平台。
//
// 声明为 PlatformAny 的能力对所有平台适用。
func Matches(capPlatform, current Platform) bool {
	return capPlatform == PlatformAny || capPlatform == current
}
