#!/usr/bin/env python3
"""Windows App CLI Tool

A command-line tool for Windows desktop application automation using pywinauto.
All operations return JSON results. Windows platform only.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import typer

# 输出编码：统一使用 UTF-8，便于 execute_script/ConPTY 正确解码，避免与 PowerShell 管道混用时乱码
_OUTPUT_ENCODING = "utf-8"

# Platform check must be first
if sys.platform != "win32":
    # Lazy message - pywinauto not needed on non-Windows
    _NOT_WINDOWS_MSG = (
        "jarvis-windows (jw) requires Windows. Current platform: " + sys.platform
    )
else:
    _NOT_WINDOWS_MSG = ""

# These imports are after platform check intentionally
# They use typer.app which is defined above
from jarvis.jarvis_utils.config import get_data_dir  # noqa: E402
from jarvis.jarvis_utils.config import get_default_encoding  # noqa: E402
from jarvis.jarvis_utils.utils import init_env  # noqa: E402

app = typer.Typer(
    help="Windows App CLI Tool - Desktop application automation (Windows only)",
    no_args_is_help=True,
)

init_env("")

config_app = typer.Typer(help="Windows 常用系统配置修改")

app.add_typer(config_app, name="config")

DEFAULT_APP_ID = "default"
SESSIONS_FILE = "jw_sessions.json"


def _sessions_path() -> Path:
    return Path(get_data_dir()) / SESSIONS_FILE


def _load_sessions() -> Dict[str, Dict[str, Any]]:
    p = _sessions_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except UnicodeDecodeError:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    except Exception:
        return {}


def _save_sessions(sessions: Dict[str, Dict[str, Any]]) -> None:
    p = _sessions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2), encoding=_OUTPUT_ENCODING
    )


def _save_session(app_id: str, params: Dict[str, Any]) -> None:
    sessions = _load_sessions()
    sessions[app_id] = params
    _save_sessions(sessions)


def _get_session_params(app_id: str) -> Optional[Dict[str, Any]]:
    return _load_sessions().get(app_id)


def _ensure_windows() -> None:
    if sys.platform != "win32":
        result = {"success": False, "stdout": "", "stderr": _NOT_WINDOWS_MSG}
        _print_gbk(json.dumps(result, ensure_ascii=False))
        raise typer.Exit(code=1)


def _print_gbk(s: str) -> None:
    """以 UTF-8 输出到 stdout，便于被 execute_script、ConPTY 等正确解码"""
    try:
        sys.stdout.buffer.write((s + "\n").encode(_OUTPUT_ENCODING, errors="replace"))
        sys.stdout.buffer.flush()
    except (AttributeError, OSError):
        print(s)


def _output(result: Dict[str, Any], exit_on_fail: bool = True) -> None:
    _print_gbk(json.dumps(result, ensure_ascii=False))
    if exit_on_fail and not result.get("success", True):
        raise typer.Exit(code=1)


def _run_action(action_name: str, fn, *args, **kwargs) -> None:
    _ensure_windows()
    try:
        result = fn(*args, **kwargs)
        _output(result)
    except Exception as e:
        _output(
            {"success": False, "stdout": "", "stderr": f"{action_name} failed: {e}"},
            exit_on_fail=True,
        )


def _connect_app(
    app_id: str = DEFAULT_APP_ID,
    process: Optional[str] = None,
    title: Optional[str] = None,
    pid: Optional[int] = None,
    backend: str = "uia",
) -> Dict[str, Any]:
    """Connect to running app and return (app, result). result has success/stdout/stderr."""
    from pywinauto import Application

    params = _get_session_params(app_id)
    if not params:
        if not process and not title and pid is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"No session for app_id [{app_id}]. Run 'jw connect' or 'jw start' first.",
            }
        # Use explicit params
        connect_process = process
        connect_title = title
        connect_pid = pid
    else:
        connect_process = process or params.get("process")
        connect_title = title or params.get("title")
        connect_pid = pid if pid is not None else params.get("pid")

    if not connect_process and not connect_title and connect_pid is None:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Need --process, --title, or --pid to connect.",
        }

    fallback = "win32" if backend == "uia" else "uia"
    backends_to_try = [backend, fallback]
    last_err: Optional[Exception] = None
    for be in backends_to_try:
        try:
            if connect_pid is not None:
                app = Application(backend=be).connect(process=connect_pid)
            elif connect_title:
                app = Application(backend=be).connect(title_re=connect_title)
            else:
                app = Application(backend=be).connect(process=connect_process or "")

            # Store for reuse (save the backend that worked)
            save_params: Dict[str, Any] = {"backend": be}
            if connect_process:
                save_params["process"] = connect_process
            if connect_title:
                save_params["title"] = connect_title
            if connect_pid is not None:
                save_params["pid"] = connect_pid
            _save_session(app_id, save_params)

            return {"success": True, "stdout": "Connected", "stderr": "", "_app": app}
        except Exception as e:
            last_err = e
            continue

    return {
        "success": False,
        "stdout": "",
        "stderr": f"Connect failed: {last_err}",
    }


def _get_app(
    app_id: str,
    process: Optional[str],
    title: Optional[str],
    pid: Optional[int],
    backend: str,
):
    """Get Application instance. Returns (app, error_result). error_result is None on success."""
    r = _connect_app(
        app_id=app_id, process=process, title=title, pid=pid, backend=backend
    )
    if not r.get("success"):
        return None, r
    app = r.get("_app")
    if app is None:
        return None, {
            "success": False,
            "stdout": "",
            "stderr": "Connect returned no app",
        }
    return app, None


def _resolve_control_from_index(
    control: Optional[str], index: Optional[int]
) -> Optional[str]:
    """When only --index given (no --control), use get-tree index #N."""
    if control is not None:
        return control
    if index is not None:
        return "#" + str(index)
    return None


def _traverse_controls(
    root,
    depth_limit: int = 99,
    start_index: int = 0,
    display_depth_limit: Optional[int] = None,
):
    """Depth-first 遍历，yield (1-based_index, elem, depth)。
    depth_limit: 实际遍历的深度限制（控制序号计算范围）
    display_depth_limit: 显示深度限制（控制yield的节点深度）
    start_index: 使 subtree 序号与全树一致。"""
    counter = [start_index]

    def _walk(elem, d: int):
        if d > depth_limit:
            return
        counter[0] += 1
        n = counter[0]
        # 只yield深度 <= display_depth_limit 的节点
        if display_depth_limit is None or d <= display_depth_limit:
            yield (n, elem, d)
        # 继续遍历子节点，但受到 depth_limit 限制
        if d < depth_limit:
            try:
                for c in elem.children():
                    yield from _walk(c, d + 1)
            except Exception:
                pass

    yield from _walk(root, 0)


def _get_control_by_index(root, idx: int, depth_limit: int = 99):
    """Get the Nth control (1-based) in depth-first tree order. depth_limit 须与 get-tree 一致。"""
    if idx < 1:
        return None, {"success": False, "stdout": "", "stderr": "Index must be >= 1"}
    try:
        for n, ctrl, _ in _traverse_controls(root, depth_limit):
            if n == idx:
                return ctrl, None
        return None, {
            "success": False,
            "stdout": "",
            "stderr": f"Index {idx} not found (tree has < {idx} controls)",
        }
    except Exception as e:
        return None, {
            "success": False,
            "stdout": "",
            "stderr": f"Index lookup failed: {e}",
        }


def _find_control(win, control: str, index: Optional[int] = None):
    """Find control by #index, title, auto_id, or title_regex. Returns (ctrl, None) or (None, error_dict)."""
    if control.startswith("#") and control[1:].isdigit():
        return _get_control_by_index(win, int(control[1:]))
    if control.startswith("title_regex="):
        pattern = control.replace("title_regex=", "")
        ctrl = win.child_window(title_re=pattern)
    else:
        ctrl = win.child_window(auto_id=control)
        if not ctrl.exists():
            ctrl = win.child_window(title=control)
    if index is not None and ctrl.exists():
        parent = ctrl.parent()
        if parent:
            children = parent.children()
            matches = [
                c
                for c in children
                if (
                    c.window_text() == control
                    or (
                        hasattr(c.element_info, "automation_id")
                        and c.element_info.automation_id == control
                    )
                )
            ]
            if 0 <= index < len(matches):
                ctrl = matches[index]
    if not ctrl.exists():
        return None, {
            "success": False,
            "stdout": "",
            "stderr": f"Control not found: {control}",
        }
    return ctrl, None


# --- Commands ---


@app.command()
def start(
    path: str = typer.Option(..., "--path", "-p", help="Executable path"),
    args: str = typer.Option("", "--args", "-a", help="Startup arguments"),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id", help="App session ID"),
    backend: str = typer.Option(
        "uia",
        "--backend",
        help="Backend: uia (default) or win32. Tries fallback automatically if primary fails.",
    ),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Start timeout (seconds)"),
) -> None:
    """Start an application and register the session."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    import warnings

    with warnings.catch_warnings(action="ignore", category=UserWarning):
        try:
            from pywinauto import findwindows

            fallback = "win32" if backend == "uia" else "uia"
            backends_to_try = [backend, fallback]
            handles_before: set = set()
            for be in backends_to_try:
                handles_before.update(
                    findwindows.find_windows(
                        title_re=".*",
                        backend=be,
                        visible_only=True,
                    )
                )
            cmd_list = [path] + (args.split() if args else [])
            proc_handle = subprocess.Popen(
                cmd_list,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc = proc_handle.pid
            app = None
            tit = ""
            used_backend = backend
            for attempt in range(int(timeout * 2)):
                time.sleep(0.5)
                try:
                    all_handles = []
                    for be in backends_to_try:
                        all_handles.extend(
                            findwindows.find_windows(
                                title_re=".*",
                                backend=be,
                                visible_only=True,
                            )
                        )
                    new_handles = [h for h in all_handles if h not in handles_before]
                    if new_handles:
                        for h in new_handles:
                            for be in backends_to_try:
                                try:
                                    a = Application(backend=be).connect(handle=h)
                                    w = a.top_window()
                                    wpid = w.process_id()
                                    if wpid == proc or wpid == proc_handle.pid:
                                        app = a
                                        proc = wpid
                                        tit = w.window_text()
                                        used_backend = be
                                        break
                                except Exception:
                                    continue
                            if app is not None:
                                break
                        if app is None and new_handles:
                            try:
                                app = Application(backend=backends_to_try[0]).connect(
                                    handle=new_handles[0]
                                )
                                win = app.top_window()
                                proc = win.process_id()
                                tit = win.window_text()
                                used_backend = backends_to_try[0]
                            except Exception:
                                pass
                        if app is not None:
                            break
                except Exception:
                    continue
            if app is None:
                proc_handle.kill()
                raise RuntimeError(
                    "Window not ready after start (uia and win32 both failed)."
                )
            params: Dict[str, Any] = {
                "process": path,
                "backend": used_backend,
                "pid": proc,
            }
            if tit:
                params["title"] = tit
            _save_session(app_id, params)
            _output(
                {
                    "success": True,
                    "stdout": f"Started. pid={proc}, title={tit}",
                    "stderr": "",
                }
            )
        except Exception as e:
            _output(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Start failed: {e}",
                }
            )


@app.command()
def connect(
    process: Optional[str] = typer.Option(
        None, "--process", help="Process name or path"
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Window title (regex ok)"
    ),
    pid: Optional[int] = typer.Option(None, "--pid", help="Process ID"),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id", help="App session ID"),
    backend: str = typer.Option(
        "uia", "--backend", help="Backend: uia (default) or win32"
    ),
) -> None:
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    r = _connect_app(
        app_id=app_id, process=process, title=title, pid=pid, backend=backend
    )
    # Don't pass _app to JSON output
    out = {k: v for k, v in r.items() if k != "_app"}
    _output(out)


@app.command(name="list")
def list_cmd(
    app_id: Optional[str] = typer.Option(None, "--app-id", help="Filter by app ID"),
) -> None:
    """List registered app sessions."""
    _ensure_windows()
    sessions = _load_sessions()
    if app_id:
        sessions = {k: v for k, v in sessions.items() if k == app_id}
    items = [
        {
            "app_id": aid,
            "process": p.get("process"),
            "title": p.get("title"),
            "pid": p.get("pid"),
        }
        for aid, p in sessions.items()
    ]
    _output(
        {
            "success": True,
            "stdout": json.dumps(items, ensure_ascii=False, indent=2),
            "stderr": "",
        }
    )


@app.command(name="list-windows")
def list_windows_cmd(
    backend: str = typer.Option(
        "uia", "--backend", help="Backend: uia (default) or win32"
    ),
    title_filter: Optional[str] = typer.Option(
        None, "--title", "-t", help="Filter by window title (substring match)"
    ),
    limit: int = typer.Option(
        50, "--limit", "-n", help="Max windows to list (default 50)"
    ),
) -> None:
    """List visible windows (title, pid, handle). Use --title to filter."""
    _ensure_windows()
    try:
        from pywinauto import Desktop
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    seen: set = set()
    items: list = []
    be = "win32" if backend == "uia" else "uia"
    for be_try in [backend, be]:
        try:
            desktop = Desktop(backend=be_try)
            for win in desktop.windows():
                if len(items) >= limit:
                    break
                try:
                    raw_title = win.window_text() or ""
                    if not raw_title.strip():
                        continue
                    title = "".join(
                        c for c in raw_title if ord(c) >= 32 and c != "\u200b"
                    ).strip()
                    if not title:
                        title = raw_title
                    pid = win.process_id()
                    key = (pid, title)
                    if key in seen:
                        continue
                    seen.add(key)
                    if title_filter and title_filter.lower() not in title.lower():
                        continue
                    h = getattr(win.element_info, "handle", None) or getattr(
                        win, "handle", None
                    )
                    items.append({"title": title, "pid": pid, "handle": h})
                except Exception:
                    continue
            if items:
                break
        except Exception:
            continue

    _output(
        {
            "success": True,
            "stdout": json.dumps(items, ensure_ascii=True, indent=2),
            "stderr": "",
        }
    )


@app.command()
def close(
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id", help="App session ID"),
    kill: bool = typer.Option(
        True,
        "--kill/--no-kill",
        "-k",
        help="Kill process (default). Use --no-kill to only disconnect",
    ),
) -> None:
    """Close session and kill process (use --no-kill to disconnect only)."""
    _ensure_windows()
    sessions = _load_sessions()
    if app_id not in sessions:
        _output(
            {
                "success": True,
                "stdout": "Session not found (already closed)",
                "stderr": "",
            }
        )
        return

    if kill:
        try:
            from pywinauto import Application
            import time

            params = sessions[app_id]
            backend = params.get("backend", "uia")
            pid = params.get("pid")
            proc = params.get("process")
            fallback = "win32" if backend == "uia" else "uia"
            for be in [backend, fallback]:
                try:
                    if pid is not None:
                        app = Application(backend=be).connect(process=pid)
                    elif proc:
                        app = Application(backend=be).connect(process=proc)
                    else:
                        app = Application(backend=be).connect(
                            title_re=params.get("title", ".*")
                        )
                    win = app.window()
                    win.set_focus()
                    win.type_keys("%{F4}")
                    time.sleep(1.0)
                    try:
                        if win.exists():
                            app.kill()
                    except Exception:
                        pass
                    break
                except Exception:
                    continue
            else:
                raise RuntimeError("Connect failed for close")
        except Exception as e:
            _output(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Close failed: {e}",
                }
            )
            return

    del sessions[app_id]
    _save_sessions(sessions)
    _output({"success": True, "stdout": "Closed", "stderr": ""})


@app.command()
def click(
    control: Optional[str] = typer.Option(
        None,
        "--control",
        "-c",
        help="Control title, AutomationId, title_regex=..., or #N from get-tree",
    ),
    menu: Optional[str] = typer.Option(
        None, "--menu", "-m", help="Menu path, e.g. File->Open"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-i", help="Control index from get-tree (e.g. -i 5 for #5)"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id", help="App session ID"),
    process: Optional[str] = typer.Option(
        None, "--process", help="Process to connect (override session)"
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Window title (override session)"
    ),
    pid: Optional[int] = typer.Option(
        None, "--pid", help="Process ID (override session)"
    ),
    backend: str = typer.Option("uia", "--backend", help="Backend"),
) -> None:
    """Click a control or menu item."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        control = _resolve_control_from_index(control, index)
        if menu:
            win.menu_select(menu)
        elif control:
            ctrl, err = _find_control(
                win, control, None if control.startswith("#") else index
            )
            if err:
                _output(err)
                return
            win.set_focus()
            _do_click(ctrl, win=win)
        else:
            return _output(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": "Need --control, --index, or --menu",
                }
            )
        _output({"success": True, "stdout": "Clicked", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Click failed: {e}"})


def _do_click(ctrl, win=None, double: bool = False, right: bool = False):
    """Click control. Prefer invoke/click (no coords), else click_input. For rect=(0,0,0,0) use window coords."""
    if win:
        try:
            win.set_focus()
        except Exception:
            pass
    if right:
        if hasattr(ctrl, "right_click"):
            ctrl.right_click()
        else:
            _click_at_coords(ctrl, win, button="right")
    elif double:
        if hasattr(ctrl, "double_click"):
            ctrl.double_click()
        else:
            _click_at_coords(ctrl, win, double=True)
    else:
        if hasattr(ctrl, "invoke"):
            try:
                ctrl.invoke()
                return
            except Exception:
                pass
        if hasattr(ctrl, "click"):
            try:
                ctrl.click()
                return
            except Exception:
                pass
        _click_at_coords(ctrl, win)


def _click_at_coords(ctrl, win=None, button: str = "left", double: bool = False):
    """Click at control center, or estimate from window when rect is (0,0,0,0)."""
    rect = ctrl.rectangle()
    if rect.left != 0 or rect.top != 0 or rect.right != 0 or rect.bottom != 0:
        # 优先用相对坐标点击（左内 1/4、垂直居中），减少被重叠元素拦截的概率
        try:
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 4 and h > 4:
                rel_x, rel_y = max(2, w // 4), h // 2
                ctrl.click_input(coords=(rel_x, rel_y), button=button, double=double)
                return
        except Exception:
            pass
        ctrl.click_input(button=button, double=double)
        return
    # rect 无效时，估算位置。标题栏按钮优先按名称（兄弟索引在 UIA 下常匹配失败）
    try:
        p = ctrl
        wrect = None
        while p:
            r = p.rectangle()
            if r.right > 0 and r.bottom > 0:
                wrect = r
                break
            try:
                p = p.parent() if hasattr(p, "parent") else None
            except Exception:
                break
        if not wrect:
            ctrl.click_input(button=button, double=double)
            return
        par = ctrl.parent()
        siblings = par.children() if par else []
        idx = 0
        name = (ctrl.window_text() or "").strip()
        # 1) 标题栏按钮按名称定位，避免兄弟索引匹配失败时点到左侧
        name_offsets = [
            ("关闭", 23),
            ("Close", 23),
            ("✕", 23),
            ("最大", 69),
            ("Maximize", 69),
            ("Restore", 69),
            ("最小", 115),
            ("Minimize", 115),
        ]
        for k, off in name_offsets:
            if k in name:
                if win:
                    try:
                        wr = win.rectangle()
                        if wr.right > 0:
                            wrect = wr
                    except Exception:
                        pass
                right_edge = wrect.right
                bar_h = min(40, (wrect.bottom - wrect.top) // 10)
                cx = right_edge - off
                cy = wrect.top + bar_h // 2
                idx = -1
                break
        # 2) 通用兄弟索引
        if idx >= 0:
            try:
                for i, c in enumerate(siblings):
                    if getattr(c, "handle", None) == getattr(ctrl, "handle", None):
                        idx = i
                        break
                    try:
                        if c.element_info == ctrl.element_info:
                            idx = i
                            break
                    except Exception:
                        pass
            except Exception:
                pass
            n = max(1, len(siblings))
            if par:
                pr = par.rectangle()
                if pr.right > 0 and pr.bottom > 0:
                    wrect = pr
            left, top, right, bottom = wrect.left, wrect.top, wrect.right, wrect.bottom
            w, h = right - left, bottom - top
            cx = int(left + w * (idx + 0.5) / n)
            cy = int(top + h // 2)
        import time

        if win:
            try:
                win.set_focus()
                time.sleep(0.25)
            except Exception:
                pass
        from pywinauto import mouse

        if double:
            mouse.double_click(coords=(cx, cy), button=button)
        else:
            mouse.click(coords=(cx, cy), button=button)
    except Exception:
        ctrl.click_input(button=button, double=double)


def _get_control_center(ctrl) -> tuple:
    """Get screen coordinates of control center (x, y)."""
    rect = ctrl.rectangle()
    return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)


@app.command(name="double-click")
def double_click_cmd(
    control: Optional[str] = typer.Option(
        None, "--control", "-c", help="Control or #N from get-tree"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-i", help="Control index from get-tree"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Double-click a control."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        control = _resolve_control_from_index(control, index)
        if not control:
            return _output(
                {"success": False, "stdout": "", "stderr": "Need --control or --index"}
            )
        ctrl, err = _find_control(
            win, control, None if control.startswith("#") else index
        )
        if err:
            _output(err)
            return
        _do_click(ctrl, win=win, double=True)
        _output({"success": True, "stdout": "Double-clicked", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Double-click failed: {e}"})


@app.command(name="right-click")
def right_click_cmd(
    control: Optional[str] = typer.Option(
        None, "--control", "-c", help="Control or #N from get-tree"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-i", help="Control index from get-tree"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Right-click a control or the window."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        control = _resolve_control_from_index(control, index)
        if control:
            ctrl, err = _find_control(
                win, control, None if control.startswith("#") else index
            )
            if err:
                _output(err)
                return
        else:
            ctrl = win
        _do_click(ctrl, win=win, right=True)
        _output({"success": True, "stdout": "Right-clicked", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Right-click failed: {e}"})


@app.command()
def hover(
    control: Optional[str] = typer.Option(
        None, "--control", "-c", help="Control or #N from get-tree"
    ),
    x: Optional[int] = typer.Option(
        None, "--x", help="Screen X coordinate (used if --control omitted)"
    ),
    y: Optional[int] = typer.Option(
        None, "--y", help="Screen Y coordinate (used if --control omitted)"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-i", help="Control index from get-tree"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Move mouse to control center or to (x, y) coordinates."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    control = _resolve_control_from_index(control, index)
    if control is None and (x is None or y is None):
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "Need --control, --index, or both --x and --y",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        if control:
            win = app.window()
            ctrl, err = _find_control(
                win, control, None if control.startswith("#") else index
            )
            if err:
                _output(err)
                return
            px, py = _get_control_center(ctrl)
        else:
            px, py = x, y  # type: ignore
        win = app.window()
        win.move_mouse(coords=(px, py), absolute=True)
        _output({"success": True, "stdout": f"Moved to ({px}, {py})", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Hover failed: {e}"})


@app.command()
def drag(
    to_control: Optional[str] = typer.Option(
        None, "--to-control", help="Drag to this control's center"
    ),
    to_x: Optional[int] = typer.Option(None, "--to-x", help="Drag to X (screen coord)"),
    to_y: Optional[int] = typer.Option(None, "--to-y", help="Drag to Y (screen coord)"),
    from_control: Optional[str] = typer.Option(
        None, "--from-control", help="Start drag from this control"
    ),
    from_x: Optional[int] = typer.Option(
        None, "--from-x", help="Start X (used if --from-control omitted)"
    ),
    from_y: Optional[int] = typer.Option(
        None, "--from-y", help="Start Y (used if --from-control omitted)"
    ),
    button: str = typer.Option(
        "left", "--button", "-b", help="Mouse button: left, right, middle"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Drag mouse from one point to another."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    if to_control is None and (to_x is None or to_y is None):
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "Need --to-control or both --to-x and --to-y",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        if from_control:
            ctrl, err = _find_control(win, from_control, None)
            if err:
                _output(err)
                return
            press_coords = _get_control_center(ctrl)
        elif from_x is not None and from_y is not None:
            press_coords = (from_x, from_y)
        else:
            rect = win.rectangle()
            press_coords = (
                (rect.left + rect.right) // 2,
                (rect.top + rect.bottom) // 2,
            )

        if to_control:
            ctrl, err = _find_control(win, to_control, None)
            if err:
                _output(err)
                return
            release_coords = _get_control_center(ctrl)
        else:
            release_coords = (to_x, to_y)  # type: ignore

        win.drag_mouse(
            button=button,
            press_coords=press_coords,
            release_coords=release_coords,
        )
        _output({"success": True, "stdout": "Drag completed", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Drag failed: {e}"})


@app.command(name="type")
def type_text(
    text: str = typer.Option(..., "--text", "-t", help="Text to type"),
    control: Optional[str] = typer.Option(
        None, "--control", "-c", help="Target control or #N from get-tree"
    ),
    index: Optional[int] = typer.Option(
        None, "--index", "-i", help="Control index from get-tree"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id", help="App session ID"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Type text into a control."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        control = _resolve_control_from_index(control, index)
        if control:
            ctrl, err = _find_control(
                win, control, None if control.startswith("#") else index
            )
            if err:
                _output(err)
                return
        else:
            ctrl = win
        ctrl.set_focus()
        try:
            if hasattr(ctrl, "set_edit_text"):
                ctrl.set_edit_text(text)
            else:
                ctrl.type_keys(text, with_spaces=True)
        except Exception:
            # 主窗口/容器无 set_edit_text，或控件不支持；回退到 type_keys
            ctrl.type_keys(text, with_spaces=True)
        _output({"success": True, "stdout": "Typed", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Type failed: {e}"})


@app.command(name="type-keys")
def type_keys_cmd(
    keys: str = typer.Option(
        ..., "--keys", "-k", help="Key sequence, e.g. ^a, {ENTER}"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Send keyboard key sequence."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        win.set_focus()
        win.type_keys(keys)
        _output({"success": True, "stdout": "Keys sent", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Type-keys failed: {e}"})


@app.command()
def screenshot(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Save path"),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Capture window screenshot."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
        from datetime import datetime
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        if not path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            data_dir = Path(get_data_dir())
            data_dir.mkdir(parents=True, exist_ok=True)
            path = str(data_dir / f"jw_screenshot_{ts}.png")
        win.capture_as_image().save(path)
        _output({"success": True, "stdout": f"Saved to {path}", "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Screenshot failed: {e}"})


@app.command(name="get-tree")
def get_tree_cmd(
    depth: int = typer.Option(
        99, "--depth", "-d", help="Tree depth（与 click -i 序号对应，默认全树）"
    ),
    control: Optional[str] = typer.Option(
        None, "--control", "-c", help="Start from control or #N"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Get control tree with #N indexes (use with click/type -i N or -c #N)."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        start = win
        start_idx = 0
        if control:
            if control.startswith("#") and control[1:].isdigit():
                idx_val = int(control[1:])
                start, err = _get_control_by_index(win, idx_val)
                if err:
                    _output(err)
                    return
                start_idx = idx_val - 1
            else:
                ctrl = win.child_window(auto_id=control)
                if not ctrl.exists():
                    ctrl = win.child_window(title=control)
                if ctrl.exists():
                    start = ctrl
        lines = []
        # 始终使用 depth_limit=99 遍历全树，但只显示深度 <= depth 的节点
        for n, elem, d in _traverse_controls(start, 99, start_idx, depth):
            try:
                ct = elem.element_info.control_type
                name = elem.window_text() or ""
                aid = getattr(elem.element_info, "automation_id", "") or ""
                rect = elem.rectangle()
                lines.append(
                    "  " * d + f"#{n} [{ct}] name={name!r} auto_id={aid!r} rect={rect}"
                )
            except Exception:
                pass
        _output({"success": True, "stdout": "\n".join(lines), "stderr": ""})
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Get-tree failed: {e}"})


@app.command()
def menu(
    menu_path: str = typer.Option(
        ..., "--path", "-p", help="Menu path, e.g. File->Open"
    ),
    app_id: str = typer.Option(DEFAULT_APP_ID, "--app-id"),
    process: Optional[str] = typer.Option(None, "--process"),
    title: Optional[str] = typer.Option(None, "--title"),
    pid: Optional[int] = typer.Option(None, "--pid"),
    backend: str = typer.Option("uia", "--backend"),
) -> None:
    """Execute menu selection."""
    _ensure_windows()
    try:
        from pywinauto import Application  # noqa: F401 - Check availability only
    except ImportError:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": "pywinauto not installed. Run: pip install pywinauto",
            }
        )
        return

    app, err = _get_app(app_id, process, title, pid, backend)
    if err:
        _output(err)
        return

    try:
        win = app.window()
        win.menu_select(menu_path)
        _output(
            {"success": True, "stdout": f"Menu selected: {menu_path}", "stderr": ""}
        )
    except Exception as e:
        _output({"success": False, "stdout": "", "stderr": f"Menu failed: {e}"})


# --- System Config Commands (PowerShell/Registry based) ---


def _run_ps(script: str, timeout: int = 30) -> Dict[str, Any]:
    """Run PowerShell script and return {success, stdout, stderr}."""
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            timeout=timeout,
            encoding=get_default_encoding(),
            errors="replace",
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return {"success": r.returncode == 0, "stdout": out, "stderr": err}
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "PowerShell execution timed out",
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


@config_app.command("theme")
def config_theme(
    mode: str = typer.Argument(..., help="dark | light | toggle"),
) -> None:
    """切换系统/应用主题（深色/浅色模式）"""
    _ensure_windows()
    path = r"HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    if mode == "toggle":
        script = f"""
$p = Get-ItemProperty -Path '{path}' -Name AppsUseLightTheme -ErrorAction SilentlyContinue
$v = if ($p.AppsUseLightTheme -eq 0) {{ 1 }} else {{ 0 }}
Set-ItemProperty -Path '{path}' -Name AppsUseLightTheme -Value $v -Type Dword -Force
Set-ItemProperty -Path '{path}' -Name SystemUsesLightTheme -Value $v -Type Dword -Force
Write-Output "Theme: $(if ($v -eq 0) {{ 'dark' }} else {{ 'light' }})"
"""
    elif mode == "dark":
        script = f"""
Set-ItemProperty -Path '{path}' -Name AppsUseLightTheme -Value 0 -Type Dword -Force
Set-ItemProperty -Path '{path}' -Name SystemUsesLightTheme -Value 0 -Type Dword -Force
Write-Output "Theme: dark"
"""
    elif mode == "light":
        script = f"""
Set-ItemProperty -Path '{path}' -Name AppsUseLightTheme -Value 1 -Type Dword -Force
Set-ItemProperty -Path '{path}' -Name SystemUsesLightTheme -Value 1 -Type Dword -Force
Write-Output "Theme: light"
"""
    else:
        _output(
            {
                "success": False,
                "stdout": "",
                "stderr": f"Invalid mode: {mode}. Use dark, light, or toggle",
            }
        )
        return
    _output(_run_ps(script))


@config_app.command("power-plan")
def config_power_plan(
    action: str = typer.Argument(..., help="list | set"),
    plan_id: Optional[str] = typer.Option(
        None, "--id", help="电源方案 GUID（set 时必需）"
    ),
) -> None:
    """列出或切换电源计划"""
    _ensure_windows()
    if action == "list":
        script = "powercfg /list | Out-String"
        _output(_run_ps(script))
        return
    if action == "set":
        if not plan_id:
            _output(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": "Need --id (plan GUID) for 'set'",
                }
            )
            return
        script = f"powercfg /setactive {plan_id}"
        _output(_run_ps(script))
        return
    _output(
        {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid action: {action}. Use list or set",
        }
    )


@config_app.command("proxy")
def config_proxy(
    action: str = typer.Argument(..., help="get | enable | disable | set"),
    server: Optional[str] = typer.Option(
        None, "--server", help="代理地址，如 127.0.0.1:7890"
    ),
    bypass: Optional[str] = typer.Option(
        None, "--bypass", help="绕过列表，如 localhost;127.*"
    ),
) -> None:
    """获取或设置系统代理"""
    _ensure_windows()
    path = r"HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings"
    if action == "get":
        script = f"""
$p = Get-ItemProperty -Path '{path}' -Name ProxyEnable -ErrorAction SilentlyContinue
$s = (Get-ItemProperty -Path '{path}' -Name ProxyServer -ErrorAction SilentlyContinue).ProxyServer
Write-Output "enabled=$($p.ProxyEnable); server=$s"
"""
        _output(_run_ps(script))
        return
    if action == "disable":
        script = f"""
Set-ItemProperty -Path '{path}' -Name ProxyEnable -Value 0 -Type Dword -Force
Write-Output "Proxy disabled"
"""
        _output(_run_ps(script))
        return
    if action == "enable":
        server_val = server or "127.0.0.1:7890"
        bypass_val = bypass or "localhost;127.*;10.*;172.16.*;192.168.*"
        script = f"""
Set-ItemProperty -Path '{path}' -Name ProxyEnable -Value 1 -Type Dword -Force
Set-ItemProperty -Path '{path}' -Name ProxyServer -Value '{server_val}' -Force
Set-ItemProperty -Path '{path}' -Name ProxyOverride -Value '{bypass_val}' -Force -ErrorAction SilentlyContinue
Write-Output "Proxy enabled: {server_val}"
"""
        _output(_run_ps(script))
        return
    if action == "set":
        if not server:
            _output(
                {"success": False, "stdout": "", "stderr": "Need --server for 'set'"}
            )
            return
        bypass_val = bypass or "localhost;127.*;10.*;172.16.*;192.168.*"
        script = f"""
Set-ItemProperty -Path '{path}' -Name ProxyEnable -Value 1 -Type Dword -Force
Set-ItemProperty -Path '{path}' -Name ProxyServer -Value '{server}' -Force
Set-ItemProperty -Path '{path}' -Name ProxyOverride -Value '{bypass_val}' -Force -ErrorAction SilentlyContinue
Write-Output "Proxy set: {server}"
"""
        _output(_run_ps(script))
        return
    _output(
        {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid action: {action}. Use get, enable, disable, or set",
        }
    )


@config_app.command("screen-timeout")
def config_screen_timeout(
    action: str = typer.Argument(..., help="get | set"),
    minutes: Optional[int] = typer.Option(
        None, "--minutes", "-m", help="熄屏分钟数，0 表示从不"
    ),
) -> None:
    """获取或设置屏幕关闭超时（当前电源计划）"""
    _ensure_windows()
    if action == "get":
        script = "powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE"
        _output(_run_ps(script))
        return
    if action == "set":
        if minutes is None:
            _output(
                {"success": False, "stdout": "", "stderr": "Need --minutes for 'set'"}
            )
            return
        ac_min = max(0, minutes)  # AC power
        dc_min = max(0, minutes)  # DC/battery
        script = f"powercfg /change monitor-timeout-ac {ac_min}; powercfg /change monitor-timeout-dc {dc_min}"
        _output(_run_ps(script))
        return
    _output(
        {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid action: {action}. Use get or set",
        }
    )


@config_app.command("remote-desktop")
def config_remote_desktop(
    action: str = typer.Argument(..., help="enable | disable | get"),
) -> None:
    """启用/禁用远程桌面（需管理员权限）"""
    _ensure_windows()
    path = r"HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server"
    if action == "get":
        script = f"(Get-ItemProperty -Path '{path}' -Name fDenyTSConnections -ErrorAction SilentlyContinue).fDenyTSConnections"
        _output(_run_ps(script))
        return
    if action == "enable":
        script = f"""
Set-ItemProperty -Path '{path}' -Name fDenyTSConnections -Value 0 -Force
Write-Output "Remote Desktop enabled (may need admin)"
"""
        _output(_run_ps(script))
        return
    if action == "disable":
        script = f"""
Set-ItemProperty -Path '{path}' -Name fDenyTSConnections -Value 1 -Force
Write-Output "Remote Desktop disabled (may need admin)"
"""
        _output(_run_ps(script))
        return
    _output(
        {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid action: {action}. Use enable, disable, or get",
        }
    )


@config_app.command("startup")
def config_startup(
    action: str = typer.Argument(..., help="list | enable | disable"),
    name: Optional[str] = typer.Option(
        None, "--name", help="启动项名称（enable/disable 时）"
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="启动项路径/命令行（enable 时）"
    ),
) -> None:
    """列出启动项或启用/禁用（当前用户 Startup 文件夹）"""
    _ensure_windows()
    startup_dir = r"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    if action == "list":
        script = f"""
Get-ChildItem -Path '{startup_dir}' -ErrorAction SilentlyContinue | ForEach-Object {{
  $n = $_.Name; $t = $_.Target -replace '^.*\\', ''; Write-Output "$n | $t"
}}
"""
        _output(_run_ps(script))
        return
    if action == "disable":
        if not name:
            _output(
                {"success": False, "stdout": "", "stderr": "Need --name for 'disable'"}
            )
            return
        safe_name = name.replace("'", "''")
        script = f"""
$p = Join-Path '{startup_dir}' '{safe_name}'
if (Test-Path $p) {{ Rename-Item $p ($p + '.disabled') -Force; Write-Output "Disabled: {safe_name}" }}
else {{ Write-Error "Not found: {safe_name}" }}
"""
        _output(_run_ps(script))
        return
    if action == "enable":
        if not name:
            _output(
                {"success": False, "stdout": "", "stderr": "Need --name for 'enable'"}
            )
            return
        safe_name = name.replace("'", "''")
        script = f"""
$p = Join-Path '{startup_dir}' '{safe_name}'
$disabled = $p + '.disabled'
if (Test-Path $disabled) {{ Rename-Item $disabled $p -Force; Write-Output "Enabled: {safe_name}" }}
elseif (Test-Path $p) {{ Write-Output "Already enabled: {safe_name}" }}
else {{ Write-Error "Not found: {safe_name}" }}
"""
        _output(_run_ps(script))
        return
    _output(
        {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid action: {action}. Use list, enable, or disable",
        }
    )


if __name__ == "__main__":
    app()
