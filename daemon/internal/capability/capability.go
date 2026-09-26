// Package capability 提供守护进程的能力注册表。
//
// 设计参考 Python 侧 src/jarvis/jarvis_tools/registry.py 的 Tool / ToolRegistry 模型：
// 每个能力有名称、描述、参数 schema 与处理函数；注册表负责注册、查询、按平台列出与执行。
// 平台专有能力通过构建标签（见 registry_linux.go / registry_windows.go / registry_other.go）
// 在 NewRegistry 时装配，避免在无构建标签的文件中引用平台专有类型。
//
// 本轮只实现框架，不注册任何实际能力。
package capability

import (
	"fmt"
	"sort"
	"sync"
)

// Platform 表示能力适用的平台。
type Platform string

// 平台常量。PlatformAny 表示跨平台通用能力。
const (
	PlatformWindows Platform = "windows"
	PlatformLinux   Platform = "linux"
	PlatformDarwin  Platform = "darwin"
	PlatformAny     Platform = "any"
)

// Capability 描述一个可被网关调用的能力。
type Capability struct {
	// Name 是能力唯一名称，建议使用 "域.动作" 形式（如 "fs.read"）。
	Name string `json:"name"`
	// Description 是能力说明，供模型理解用途。
	Description string `json:"description"`
	// Parameters 是参数 JSON schema 描述，可为空。
	Parameters map[string]any `json:"parameters,omitempty"`
	// Platform 是该能力适用的平台，为空时视为 PlatformAny。
	Platform Platform `json:"platform"`
	// Handler 是能力实现；params 为调用参数，返回结果与错误。
	Handler func(params map[string]any) (any, error) `json:"-"`
}

// Result 是一次能力调用的结果。
type Result struct {
	// Success 表示调用是否成功。
	Success bool `json:"success"`
	// Data 是成功时的返回数据。
	Data any `json:"data,omitempty"`
	// Error 是失败原因。
	Error string `json:"error,omitempty"`
}

// Registry 是能力注册表，并发安全。
type Registry struct {
	mu   sync.RWMutex
	caps map[string]*Capability
}

// NewRegistry 创建注册表并装配当前平台的能力。
func NewRegistry() *Registry {
	r := &Registry{caps: make(map[string]*Capability)}
	registerPlatformCapabilities(r)
	return r
}

// Register 注册一个能力。
//
// 名称为空或重复注册都会返回错误（不静默覆盖）。
func (r *Registry) Register(cap Capability) error {
	if cap.Name == "" {
		return fmt.Errorf("capability name is empty")
	}
	if cap.Platform == "" {
		cap.Platform = PlatformAny
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.caps[cap.Name]; exists {
		return fmt.Errorf("capability already registered: %s", cap.Name)
	}
	c := cap
	r.caps[cap.Name] = &c
	return nil
}

// Get 按名称查询能力。
func (r *Registry) Get(name string) (*Capability, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	c, ok := r.caps[name]
	return c, ok
}

// List 返回全部能力的副本，按名称升序排序。
func (r *Registry) List() []Capability {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]Capability, 0, len(r.caps))
	for _, c := range r.caps {
		out = append(out, *c)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// ListForPlatform 返回适用于指定平台的能力（含 PlatformAny 的能力），按名称升序排序。
func (r *Registry) ListForPlatform(p Platform) []Capability {
	all := r.List()
	out := make([]Capability, 0, len(all))
	for _, c := range all {
		if Matches(c.Platform, p) {
			out = append(out, c)
		}
	}
	return out
}

// Execute 按名称执行能力。
//
// 未注册的能力返回 Success=false 且 Error 含 "unknown capability: <name>"；
// Handler 为 nil 时返回明确错误；Handler panic 会被捕获并转为错误。
func (r *Registry) Execute(name string, params map[string]any) (res Result) {
	cap, ok := r.Get(name)
	if !ok {
		return Result{Success: false, Error: fmt.Sprintf("unknown capability: %s", name)}
	}
	if cap.Handler == nil {
		return Result{Success: false, Error: fmt.Sprintf("capability not implemented: %s", name)}
	}
	defer func() {
		if rec := recover(); rec != nil {
			res = Result{Success: false, Error: fmt.Sprintf("capability %s panicked: %v", name, rec)}
		}
	}()
	data, err := cap.Handler(params)
	if err != nil {
		return Result{Success: false, Error: err.Error()}
	}
	return Result{Success: true, Data: data}
}
