#!/usr/bin/env python3
"""Playwright Browser CLI Tool

A simple command-line tool for browser automation.
All operations return JSON results.
"""

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime

import typer
from playwright.async_api import async_playwright

from jarvis.jarvis_utils.config import get_data_dir


# Global playwright context and browser sessions
_playwright_context = None
_browser_sessions: Dict[str, Dict[str, Any]] = {}

# Global console logs storage (per browser session)
_console_logs: Dict[str, List[Dict[str, str]]] = {}


# Typer app
app = typer.Typer(
    help="Playwright Browser CLI Tool - Browser automation command-line interface",
    no_args_is_help=True,
)


def get_socket_path() -> Path:
    """Get the default socket path for daemon mode."""
    return Path(get_data_dir()) / "playwright_daemon.sock"


class BrowserDaemon:
    """Playwright Browser Daemon

    Manages browser sessions and provides IPC interface via Unix domain socket.
    """

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.server: asyncio.Server | None = None
        self._server_task: asyncio.Task[None] | None = None
        self.running = False

    async def start(self) -> None:
        """Start daemon"""
        self.running = True

        # Ensure socket file does not exist
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        # Create Unix domain socket
        self.server = await asyncio.start_unix_server(
            self.handle_client,
            path=self.socket_path,
        )

        print(f"Playwright Browser Daemon started, socket: {self.socket_path}")

        # Start server task
        self._server_task = asyncio.create_task(self.server.serve_forever())

        # Graceful shutdown handling
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    async def _delayed_stop(self) -> None:
        """Delayed stop daemon"""
        # Wait a bit to ensure clients receive response
        await asyncio.sleep(0.1)
        await self.stop()

    async def stop(self) -> None:
        """Stop daemon"""
        if not self.running:
            return

        self.running = False

        # Cancel server task
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        # Close socket
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # Delete socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        print("Playwright Browser Daemon stopped")

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle client connection"""
        try:
            while self.running:
                # Read request
                line = await reader.readline()
                if not line:
                    break

                try:
                    # Parse Content-Length header
                    header = line.decode().strip()
                    if header.startswith("Content-Length:"):
                        content_length = int(header.split(":")[1].strip())
                    else:
                        content_length = int(header)

                    # Read empty line
                    await reader.readline()

                    # Read content
                    content = await reader.readexactly(content_length)
                    request = json.loads(content.decode())

                    # Handle request
                    response = await self.handle_request(request)

                    # Send response
                    response_json = json.dumps(response, ensure_ascii=False)
                    response_data = f"Content-Length: {len(response_json)}\r\n\r\n{response_json}".encode()
                    writer.write(response_data)
                    await writer.drain()

                except Exception as e:
                    # Send error response
                    error_response = {
                        "success": False,
                        "stderr": str(e),
                        "stdout": "",
                    }
                    error_json = json.dumps(error_response, ensure_ascii=False)
                    error_data = f"Content-Length: {len(error_json)}\r\n\r\n{error_json}".encode()
                    writer.write(error_data)
                    await writer.drain()
                    break

        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request"""
        action = request.get("action")
        params = request.get("params", {})

        # Route to browser functions
        if action == "launch":
            return await launch_browser(
                browser_id=params.get("browser_id", "default"),
                headless=params.get("headless", True),
            )
        elif action == "close":
            return await close_browser(browser_id=params.get("browser_id", "default"))
        elif action == "navigate":
            return await navigate(
                url=params.get("url"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "click":
            return await click(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "type":
            return await type_text(
                selector=params.get("selector"),
                text=params.get("text"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "screenshot":
            return await screenshot(
                browser_id=params.get("browser_id", "default"),
                path=params.get("path", "/tmp/screenshot.png"),
            )
        elif action == "gettext":
            return await get_text(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "list":
            return await list_browsers()
        elif action == "console":
            return await get_console_logs(
                browser_id=params.get("browser_id", "default"),
                clear_logs=params.get("clear_logs", False),
            )
        elif action == "eval":
            return await evaluate_javascript(
                code=params.get("code"),
                browser_id=params.get("browser_id", "default"),
                save_result=params.get("save_result", False),
            )
        elif action == "get_attribute":
            return await get_attribute(
                selector=params.get("selector"),
                attribute=params.get("attribute"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "get_element_info":
            return await get_element_info(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "wait_for_selector":
            return await wait_for_selector(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
                wait_state=params.get("wait_state", "visible"),
                timeout=params.get("timeout", 30.0),
            )
        elif action == "wait_for_text":
            return await wait_for_text(
                text=params.get("text"),
                browser_id=params.get("browser_id", "default"),
                selector=params.get("selector", "*"),
                timeout=params.get("timeout", 30.0),
            )
        elif action == "hover":
            return await hover(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "drag":
            return await drag(
                selector=params.get("selector"),
                target_selector=params.get("target_selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "double_click":
            return await double_click(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "press_key":
            return await press_key(
                key=params.get("key"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "fill_form":
            return await fill_form(
                fields=params.get("fields", {}),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "submit_form":
            return await submit_form(
                browser_id=params.get("browser_id", "default"),
                form_selector=params.get("form_selector", "form"),
            )
        elif action == "clear_form":
            return await clear_form(
                browser_id=params.get("browser_id", "default"),
                form_selector=params.get("form_selector", "form"),
            )
        elif action == "upload_file":
            return await upload_file(
                selector=params.get("selector"),
                file_path=params.get("file_path"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "download_file":
            return await download_file(
                browser_id=params.get("browser_id", "default"),
                selector=params.get("selector", ""),
            )
        elif action == "new_tab":
            return await new_tab(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "switch_tab":
            return await switch_tab(
                page_id=params.get("page_id"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "close_tab":
            return await close_tab(
                page_id=params.get("page_id"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "go_back":
            return await go_back(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "go_forward":
            return await go_forward(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "scroll_to":
            return await scroll_to(
                scroll_x=params.get("scroll_x", 0),
                scroll_y=params.get("scroll_y", 0),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "scroll_down":
            return await scroll_down(
                scroll_amount=params.get("scroll_amount", 300),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "scroll_up":
            return await scroll_up(
                scroll_amount=params.get("scroll_amount", 300),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "get_cookies":
            return await get_cookies(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "set_cookies":
            return await set_cookies(
                cookies_data=params.get("cookies", "[]"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "clear_cookies":
            return await clear_cookies(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "get_local_storage":
            return await get_local_storage(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "set_local_storage":
            return await set_local_storage(
                data=params.get("data", "{}"),
                clear=params.get("clear", False),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "start_network_monitor":
            return await start_network_monitor(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "get_network_requests":
            return await get_network_requests(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "element_screenshot":
            return await element_screenshot(
                selector=params.get("selector"),
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "export_pdf":
            return await export_pdf(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "get_performance_metrics":
            return await get_performance_metrics(
                browser_id=params.get("browser_id", "default"),
            )
        elif action == "shutdown":
            # Delayed stop daemon, return response first
            asyncio.create_task(self._delayed_stop())
            return {"success": True, "stdout": "Daemon shutting down", "stderr": ""}
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Unknown action: {action}",
            }


@app.command()
def daemon(
    socket_path: Path = typer.Option(
        None,
        "--socket-path",
        "-s",
        help="Socket path for IPC communication",
    ),
):
    """Run as daemon process for persistent browser sessions.

    The daemon runs in the background and maintains browser sessions across
    multiple CLI invocations. Clients communicate with the daemon via Unix socket.
    """
    socket_path = socket_path or get_socket_path()

    async def run_daemon(socket_path_str: str) -> None:
        """Run daemon"""
        daemon_instance = BrowserDaemon(socket_path_str)
        await daemon_instance.start()

        try:
            # Wait for stop signal
            while daemon_instance.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await daemon_instance.stop()

    # Run async daemon
    asyncio.run(run_daemon(str(socket_path)))


@app.command()
def launch(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    headless: bool = typer.Option(
        True, "--headless", "--no-headless", help="Headless mode"
    ),
) -> None:
    """Launch browser

    Launch a new browser instance with the specified ID.
    If headless is True, the browser runs without a UI.
    """
    result = send_to_daemon("launch", {"browser_id": browser_id, "headless": headless})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def close(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Close browser

    Close the browser instance with the specified ID.
    """
    result = send_to_daemon("close", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command(name="navigate")
def navigate_cmd(
    url: str = typer.Option(..., "--url", "-u", help="URL to navigate"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Navigate to URL

    Navigate the browser to the specified URL.
    """
    result = send_to_daemon("navigate", {"url": url, "browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command(name="click")
def click_cmd(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Click element

    Click on the element matching the CSS selector.
    """
    result = send_to_daemon("click", {"selector": selector, "browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def type(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    text: str = typer.Option(..., "--text", "-t", help="Text to type"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Type text into element

    Type text into the element matching the CSS selector.
    """
    result = send_to_daemon(
        "type", {"selector": selector, "text": text, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command(name="screenshot")
def screenshot_cmd(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    path: str = typer.Option(
        "/tmp/screenshot.png", "--path", "-p", help="Screenshot path"
    ),
) -> None:
    """Take screenshot

    Take a screenshot of the current page.
    """
    result = send_to_daemon("screenshot", {"browser_id": browser_id, "path": path})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def gettext(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get text from element

    Get text content from the element matching the CSS selector.
    """
    result = send_to_daemon("gettext", {"selector": selector, "browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command(name="list")
def list_cmd() -> None:
    """List all browsers

    List all active browser sessions.
    """
    result = send_to_daemon("list", {})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def console(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    clear_logs: bool = typer.Option(
        False, "--clear-logs", help="Clear logs after reading"
    ),
) -> None:
    """Get console logs

    Get console logs from browser session.
    """
    result = send_to_daemon(
        "console", {"browser_id": browser_id, "clear_logs": clear_logs}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def eval(
    code: str = typer.Option(..., "--code", "-c", help="JavaScript code to execute"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    save_result: bool = typer.Option(
        False, "--save-result", help="Save result to file"
    ),
) -> None:
    """Execute JavaScript

    Execute JavaScript code in the browser context.
    """
    result = send_to_daemon(
        "eval", {"code": code, "browser_id": browser_id, "save_result": save_result}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def getattribute(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    attribute: str = typer.Option(..., "--attribute", "-a", help="Attribute name"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get element attribute

    Get the value of an attribute from the selected element.
    """
    result = send_to_daemon(
        "get_attribute",
        {"selector": selector, "attribute": attribute, "browser_id": browser_id},
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def getelementinfo(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get element information

    Get detailed information about the selected element.
    """
    result = send_to_daemon(
        "get_element_info", {"selector": selector, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def waitforselector(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    wait_state: str = typer.Option(
        "visible",
        "--wait-state",
        help="Wait state (visible, hidden, attached, detached)",
    ),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout in seconds"),
) -> None:
    """Wait for selector

    Wait for element to reach specified state.
    """
    result = send_to_daemon(
        "wait_for_selector",
        {
            "selector": selector,
            "browser_id": browser_id,
            "wait_state": wait_state,
            "timeout": timeout,
        },
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def waitfortext(
    text: str = typer.Option(..., "--text", "-t", help="Text to wait for"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    selector: str = typer.Option("*", "--selector", "-s", help="CSS selector"),
    timeout: float = typer.Option(30.0, "--timeout", help="Timeout in seconds"),
) -> None:
    """Wait for text

    Wait for text to appear on the page.
    """
    result = send_to_daemon(
        "wait_for_text",
        {
            "text": text,
            "browser_id": browser_id,
            "selector": selector,
            "timeout": timeout,
        },
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command(name="hover")
def hover_cmd(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Hover over element

    Move mouse over the element matching the CSS selector.
    """
    result = send_to_daemon("hover", {"selector": selector, "browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command(name="drag")
def drag_cmd(
    selector: str = typer.Option(
        ..., "--selector", "-s", help="CSS selector for source element"
    ),
    target_selector: str = typer.Option(
        ..., "--target-selector", "-t", help="CSS selector for target element"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Drag element to target

    Drag the source element to the target element.
    """
    result = send_to_daemon(
        "drag",
        {
            "selector": selector,
            "target_selector": target_selector,
            "browser_id": browser_id,
        },
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def doubleclick(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Double click on element

    Double click on the element matching the CSS selector.
    """
    result = send_to_daemon(
        "double_click", {"selector": selector, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def presskey(
    key: str = typer.Option(..., "--key", "-k", help="Key to press"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Press keyboard key

    Press the specified keyboard key.
    """
    result = send_to_daemon("press_key", {"key": key, "browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def fillform(
    fields: str = typer.Option(
        ..., "--fields", "-f", help="Form fields as JSON string"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Fill form fields

    Fill multiple form fields with values.
    """
    try:
        fields_dict = json.loads(fields)
    except json.JSONDecodeError as e:
        result = {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid JSON format for fields: {str(e)}",
        }
        print(json.dumps(result, ensure_ascii=False))
        raise typer.Exit(code=1)
    result = send_to_daemon(
        "fill_form", {"fields": fields_dict, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def submitform(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    form_selector: str = typer.Option("form", "--form-selector", help="Form selector"),
) -> None:
    """Submit form

    Submit the specified form.
    """
    result = send_to_daemon(
        "submit_form", {"browser_id": browser_id, "form_selector": form_selector}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def clearform(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    form_selector: str = typer.Option("form", "--form-selector", help="Form selector"),
) -> None:
    """Clear form fields

    Clear all fields in the specified form.
    """
    result = send_to_daemon(
        "clear_form", {"browser_id": browser_id, "form_selector": form_selector}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def uploadfile(
    selector: str = typer.Option(..., "--selector", "-s", help="CSS selector"),
    file_path: str = typer.Option(..., "--file-path", "-f", help="File path to upload"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Upload file

    Upload a file to the specified input element.
    """
    result = send_to_daemon(
        "upload_file",
        {"selector": selector, "file_path": file_path, "browser_id": browser_id},
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def downloadfile(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
    selector: str = typer.Option(
        "", "--selector", "-s", help="CSS selector for download button/link"
    ),
) -> None:
    """Download file

    Download a file from the current page.
    """
    result = send_to_daemon(
        "download_file", {"browser_id": browser_id, "selector": selector}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def newtab(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Create new tab

    Create a new tab in the browser.
    """
    result = send_to_daemon("new_tab", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def switchtab(
    page_id: str = typer.Option(..., "--page-id", "-p", help="Page ID to switch to"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Switch to tab

    Switch to the specified tab.
    """
    result = send_to_daemon(
        "switch_tab", {"page_id": page_id, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def closetab(
    page_id: str = typer.Option(..., "--page-id", "-p", help="Page ID to close"),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Close tab

    Close the specified tab.
    """
    result = send_to_daemon("close_tab", {"page_id": page_id, "browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def goback(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Go back

    Navigate to the previous page.
    """
    result = send_to_daemon("go_back", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def goforward(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Go forward

    Navigate to the next page.
    """
    result = send_to_daemon("go_forward", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def scrollto(
    scroll_x: int = typer.Option(
        0, "--scroll-x", "-x", help="X coordinate to scroll to"
    ),
    scroll_y: int = typer.Option(
        0, "--scroll-y", "-y", help="Y coordinate to scroll to"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Scroll to position

    Scroll to the specified position on the page.
    """
    result = send_to_daemon(
        "scroll_to",
        {"scroll_x": scroll_x, "scroll_y": scroll_y, "browser_id": browser_id},
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def scrolldown(
    scroll_amount: int = typer.Option(
        300, "--scroll-amount", "-a", help="Amount to scroll down in pixels"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Scroll down

    Scroll down the page by the specified amount.
    """
    result = send_to_daemon(
        "scroll_down", {"scroll_amount": scroll_amount, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def scrollup(
    scroll_amount: int = typer.Option(
        300, "--scroll-amount", "-a", help="Amount to scroll up in pixels"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Scroll up

    Scroll up the page by the specified amount.
    """
    result = send_to_daemon(
        "scroll_up", {"scroll_amount": scroll_amount, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def getcookies(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get cookies

    Get all cookies for the browser.
    """
    result = send_to_daemon("get_cookies", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def setcookies(
    cookies: str = typer.Option(
        ..., "--cookies", "-c", help="Cookies as JSON string (list format)"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Set cookies

    Set cookies from JSON string.
    """
    result = send_to_daemon(
        "set_cookies", {"cookies": cookies, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def clearcookies(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Clear cookies

    Clear all cookies for the browser.
    """
    result = send_to_daemon("clear_cookies", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def getlocalstorage(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get localStorage

    Get all localStorage data for the page.
    """
    result = send_to_daemon("get_local_storage", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def setlocalstorage(
    data: str = typer.Option(
        ..., "--data", "-d", help="Storage data as JSON string (dict format)"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Clear all localStorage before setting"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Set localStorage

    Set localStorage from JSON string.
    """
    result = send_to_daemon(
        "set_local_storage", {"data": data, "clear": clear, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def startnetworkmonitor(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Start network monitor

    Start monitoring network requests.
    """
    result = send_to_daemon("start_network_monitor", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def getnetworkrequests(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get network requests

    Get all recorded network requests.
    """
    result = send_to_daemon("get_network_requests", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def elementscreenshot(
    selector: str = typer.Option(
        ..., "--selector", "-s", help="CSS selector for element"
    ),
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Element screenshot

    Take a screenshot of a specific element.
    """
    result = send_to_daemon(
        "element_screenshot", {"selector": selector, "browser_id": browser_id}
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def exportpdf(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Export PDF

    Export the current page to PDF.
    """
    result = send_to_daemon("export_pdf", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


@app.command()
def getperformancemetrics(
    browser_id: str = typer.Option("default", "--browser-id", help="Browser ID"),
) -> None:
    """Get performance metrics

    Get performance metrics for the current page.
    """
    result = send_to_daemon("get_performance_metrics", {"browser_id": browser_id})
    print(json.dumps(result, ensure_ascii=False))
    if not result["success"]:
        raise typer.Exit(code=1)


def get_browser_session(browser_id: str = "default") -> Dict[str, Any]:
    """Get or create browser session"""
    if browser_id not in _browser_sessions:
        _browser_sessions[browser_id] = {
            "context": None,
            "page": None,
            "pages": {},
            "current_page_id": None,
        }
    if browser_id not in _console_logs:
        _console_logs[browser_id] = []
    return _browser_sessions[browser_id]


async def launch_browser(
    browser_id: str = "default", headless: bool = True
) -> Dict[str, Any]:
    """Launch browser"""
    global _playwright_context

    try:
        if _playwright_context is None:
            _playwright_context = await async_playwright().start()

        session = get_browser_session(browser_id)
        if session["context"] is not None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] already launched",
            }

        browser = await _playwright_context.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        # Add console event listener
        def handle_console_message(msg):
            # Limit logs to 1000 entries
            if len(_console_logs[browser_id]) >= 1000:
                _console_logs[browser_id].pop(0)
            _console_logs[browser_id].append(
                {
                    "type": msg.type,
                    "text": msg.text,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        page.on("console", handle_console_message)

        session["context"] = context
        session["page"] = page

        return {
            "success": True,
            "stdout": f"Browser [{browser_id}] launched successfully",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to launch browser: {str(e)}",
        }


async def close_browser(browser_id: str = "default") -> Dict[str, Any]:
    """Close browser"""
    try:
        session = get_browser_session(browser_id)
        if session["context"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        await session["context"].close()
        session["context"] = None
        session["page"] = None
        del _browser_sessions[browser_id]

        # Clear console logs
        if browser_id in _console_logs:
            del _console_logs[browser_id]

        return {
            "success": True,
            "stdout": f"Browser [{browser_id}] closed successfully",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to close browser: {str(e)}",
        }


async def navigate(url: str, browser_id: str = "default") -> Dict[str, Any]:
    """Navigate to URL"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        await page.goto(url, wait_until="networkidle")

        return {
            "success": True,
            "stdout": f"Navigated to {url}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to navigate: {str(e)}",
        }


async def click(selector: str, browser_id: str = "default") -> Dict[str, Any]:
    """Click element"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        await page.click(selector)

        return {
            "success": True,
            "stdout": f"Clicked element: {selector}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to click: {str(e)}",
        }


async def type_text(
    selector: str, text: str, browser_id: str = "default"
) -> Dict[str, Any]:
    """Type text into element"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        await page.fill(selector, text)

        return {
            "success": True,
            "stdout": f"Typed text into: {selector}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to type text: {str(e)}",
        }


async def screenshot(
    browser_id: str = "default", path: str = "/tmp/screenshot.png"
) -> Dict[str, Any]:
    """Take screenshot"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        screenshot_path = Path(path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path))

        return {
            "success": True,
            "stdout": f"Screenshot saved to: {path}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to take screenshot: {str(e)}",
        }


async def get_text(selector: str, browser_id: str = "default") -> Dict[str, Any]:
    """Get text from element"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        element = await page.query_selector(selector)
        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        text = await element.text_content()
        return {
            "success": True,
            "stdout": text if text else "",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get text: {str(e)}",
        }


async def list_browsers() -> Dict[str, Any]:
    """List all browser sessions"""
    try:
        browser_list = []

        for browser_id, session in _browser_sessions.items():
            try:
                page = session["page"]
                if page is not None:
                    browser_list.append(
                        {
                            "id": browser_id,
                            "status": "active",
                            "title": await page.title(),
                            "url": page.url,
                        }
                    )
                else:
                    browser_list.append(
                        {
                            "id": browser_id,
                            "status": "inactive",
                            "title": "",
                            "url": "",
                        }
                    )
            except Exception:
                browser_list.append(
                    {
                        "id": browser_id,
                        "status": "error",
                        "title": "",
                        "url": "",
                    }
                )

        # Format output
        output = "Browser list:\n"
        for browser in browser_list:
            output += f"ID: {browser['id']}, Status: {browser['status']}, Title: {browser['title']}, URL: {browser['url']}\n"

        return {
            "success": True,
            "stdout": output,
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to list browsers: {str(e)}",
        }


async def get_console_logs(
    browser_id: str = "default", clear_logs: bool = False
) -> Dict[str, Any]:
    """Get console logs"""
    try:
        if browser_id not in _browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        console_logs = _console_logs.get(browser_id, [])

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_console_{timestamp}.txt"

        # Format log content
        content = f"Browser ID: {browser_id}\n"
        content += f"Time: {timestamp}\n"
        content += f"Log count: {len(console_logs)}\n"
        content += "=" * 50 + "\n\n"

        for log in console_logs:
            content += f"[{log['timestamp']}] [{log['type'].upper()}] {log['text']}\n"

        # Save to file
        filename.write_text(content, encoding="utf-8")
        file_path = str(filename)

        # Clear logs if requested
        if clear_logs:
            _console_logs[browser_id] = []

        return {
            "success": True,
            "stdout": f"Got {len(console_logs)} console logs. File path: {file_path}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get console logs: {str(e)}",
        }


async def evaluate_javascript(
    code: str, browser_id: str = "default", save_result: bool = False
) -> Dict[str, Any]:
    """Execute JavaScript code"""
    try:
        if browser_id not in _browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = _browser_sessions[browser_id]["page"]

        # Execute JavaScript
        result = await page.evaluate(code)

        # Format result as string
        result_str = str(result)
        if len(result_str) > 10000:
            result_str = result_str[:10000] + "... (truncated)"

        stdout_msg = f"JavaScript executed successfully: {result_str}"
        file_path_msg = ""

        # Optionally save result to file
        if save_result:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path("/tmp/playwright_browser")
            temp_dir.mkdir(parents=True, exist_ok=True)
            filename = temp_dir / f"{browser_id}_eval_{timestamp}.txt"

            content = f"Browser ID: {browser_id}\n"
            content += f"Time: {timestamp}\n"
            content += f"Code:\n{code}\n\n"
            content += f"Result:\n{result_str}\n"

            file_path = str(filename)
            filename.write_text(content, encoding="utf-8")
            file_path_msg = f" File path: {file_path}"

        return {
            "success": True,
            "stdout": f"{stdout_msg}{file_path_msg}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to execute JavaScript: {str(e)}",
        }


async def get_attribute(
    selector: str, attribute: str, browser_id: str = "default"
) -> Dict[str, Any]:
    """Get element attribute value"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        element = await page.query_selector(selector)

        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        attr_value = await element.get_attribute(attribute)

        if attr_value is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element [{selector}] has no attribute [{attribute}]",
            }

        return {
            "success": True,
            "stdout": attr_value,
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get attribute: {str(e)}",
        }


async def get_element_info(
    selector: str, browser_id: str = "default"
) -> Dict[str, Any]:
    """Get element information"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        element = await page.query_selector(selector)

        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        # Get element information
        info = {
            "selector": selector,
            "tag_name": await element.evaluate("el => el.tagName"),
            "text": await element.evaluate("el => el.textContent"),
            "visible": await element.is_visible(),
            "enabled": await element.is_enabled(),
            "id": await element.evaluate("el => el.id"),
            "class": await element.evaluate("el => el.className"),
        }

        # Convert info to JSON string
        info_str = json.dumps(info, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "stdout": f"Element information:\n{info_str}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get element info: {str(e)}",
        }


async def wait_for_selector(
    selector: str,
    browser_id: str = "default",
    wait_state: str = "visible",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Wait for element to reach specified state"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Validate state parameter
        valid_states = ["visible", "hidden", "attached", "detached"]
        if wait_state not in valid_states:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Invalid wait state: {wait_state}, valid states: {', '.join(valid_states)}",
            }

        # Wait for element to reach specified state
        await page.wait_for_selector(selector, state=wait_state, timeout=timeout * 1000)

        return {
            "success": True,
            "stdout": f"Element [{selector}] reached state [{wait_state}]",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to wait for selector: {str(e)}",
        }


async def wait_for_text(
    text: str, browser_id: str = "default", selector: str = "*", timeout: float = 30.0
) -> Dict[str, Any]:
    """Wait for text to appear"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Wait for text to appear
        await page.wait_for_function(
            """
            (text, selector) => {
                const elements = document.querySelectorAll(selector);
                for (const el of elements) {
                    if (el.textContent && el.textContent.includes(text)) {
                        return true;
                    }
                }
                return false;
            }
            """,
            text=text,
            selector=selector,
            timeout=timeout * 1000,
        )

        return {
            "success": True,
            "stdout": f"Text [{text}] appeared",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to wait for text: {str(e)}",
        }


async def hover(selector: str, browser_id: str = "default") -> Dict[str, Any]:
    """Hover over element"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        element = await page.query_selector(selector)

        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        await element.hover()

        return {
            "success": True,
            "stdout": f"Hovered over element: {selector}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to hover: {str(e)}",
        }


async def drag(
    selector: str, target_selector: str, browser_id: str = "default"
) -> Dict[str, Any]:
    """Drag element to target"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        source_element = await page.query_selector(selector)
        target_element = await page.query_selector(target_selector)

        if not source_element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Source element not found: {selector}",
            }

        if not target_element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Target element not found: {target_selector}",
            }

        await source_element.drag_to(target_element)

        return {
            "success": True,
            "stdout": f"Dragged element [{selector}] to [{target_selector}]",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to drag: {str(e)}",
        }


async def double_click(selector: str, browser_id: str = "default") -> Dict[str, Any]:
    """Double click on element"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        element = await page.query_selector(selector)

        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        await element.dblclick()

        return {
            "success": True,
            "stdout": f"Double clicked element: {selector}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to double click: {str(e)}",
        }


async def press_key(key: str, browser_id: str = "default") -> Dict[str, Any]:
    """Press keyboard key"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        await page.keyboard.press(key)

        return {
            "success": True,
            "stdout": f"Pressed key: {key}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to press key: {str(e)}",
        }


async def fill_form(
    fields: Dict[str, str], browser_id: str = "default"
) -> Dict[str, Any]:
    """Fill form fields"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        filled_fields = []
        errors = []

        # Iterate over all fields
        for field_name, field_value in fields.items():
            try:
                # Try multiple selectors
                selectors = [
                    f"input[name='{field_name}']",
                    f"input[id='{field_name}']",
                    f"textarea[name='{field_name}']",
                    f"textarea[id='{field_name}']",
                    f"select[name='{field_name}']",
                    f"select[id='{field_name}']",
                ]

                element = None
                for selector in selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            break
                    except Exception:
                        continue

                if element:
                    await element.fill(str(field_value))
                    filled_fields.append(field_name)
                else:
                    errors.append(f"Field not found: {field_name}")

            except Exception as e:
                errors.append(f"Failed to fill field {field_name}: {str(e)}")

        # Save operation result
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_fill_form_{timestamp}.txt"

        content = f"Browser ID: {browser_id}\n"
        content += f"Time: {timestamp}\n"
        content += f"Successfully filled: {len(filled_fields)} fields\n"
        content += f"Failed: {len(errors)} fields\n\n"

        if filled_fields:
            content += "=== Successfully filled fields ===\n"
            for field in filled_fields:
                content += f"  - {field}: {fields[field]}\n"
            content += "\n"

        if errors:
            content += "=== Errors ===\n"
            for error in errors:
                content += f"  - {error}\n"

        filename.write_text(content, encoding="utf-8")

        return {
            "success": len(errors) == 0,
            "stdout": f"Filled {len(filled_fields)} fields. Result saved to: {filename}",
            "stderr": "; ".join(errors) if errors else "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to fill form: {str(e)}",
        }


async def submit_form(
    browser_id: str = "default", form_selector: str = "form"
) -> Dict[str, Any]:
    """Submit form"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Try to submit form
        try:
            await page.click(f"{form_selector} button[type='submit']")
        except Exception:
            try:
                await page.click(f"{form_selector} input[type='submit']")
            except Exception:
                # Try to submit form directly
                form = await page.query_selector(form_selector)
                if form:
                    await form.evaluate("el => el.submit()")
                else:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"Form not found: {form_selector}",
                    }

        return {
            "success": True,
            "stdout": "Form submitted",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to submit form: {str(e)}",
        }


async def clear_form(
    browser_id: str = "default", form_selector: str = "form"
) -> Dict[str, Any]:
    """Clear form fields"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Get all input elements in form
        inputs = await page.query_selector_all(f"{form_selector} input")
        textareas = await page.query_selector_all(f"{form_selector} textarea")
        selects = await page.query_selector_all(f"{form_selector} select")

        cleared_count = 0

        # Clear input elements
        for input_elem in inputs:
            try:
                await input_elem.fill("")
                cleared_count += 1
            except Exception:
                pass

        # Clear textarea elements
        for textarea in textareas:
            try:
                await textarea.fill("")
                cleared_count += 1
            except Exception:
                pass

        # Reset select elements to first option
        for select in selects:
            try:
                await select.select_option(index=0)
                cleared_count += 1
            except Exception:
                pass

        return {
            "success": True,
            "stdout": f"Cleared {cleared_count} form fields",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to clear form: {str(e)}",
        }


async def upload_file(
    selector: str, file_path: str, browser_id: str = "default"
) -> Dict[str, Any]:
    """Upload file"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]
        element = await page.query_selector(selector)

        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        await element.set_input_files(file_path)

        return {
            "success": True,
            "stdout": f"Uploaded file: {file_path}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to upload file: {str(e)}",
        }


async def download_file(
    browser_id: str = "default", selector: str = ""
) -> Dict[str, Any]:
    """Download file"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Set download directory
        import os

        download_dir = "/tmp/playwright_downloads"
        os.makedirs(download_dir, exist_ok=True)

        # Start download, wait for download to complete
        async with page.expect_download() as download_info:
            # Click download link or button
            if selector:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
            else:
                # If no selector, assume page has started download
                pass

        download = download_info.value
        file_name = (
            download.suggested_filename
            or f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        save_path = os.path.join(download_dir, file_name)

        # Save file
        await download.save_as(save_path)

        return {
            "success": True,
            "stdout": f"File downloaded to: {save_path}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to download file: {str(e)}",
        }


async def new_tab(browser_id: str = "default") -> Dict[str, Any]:
    """Create new tab"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        context = session["context"]
        pages = session.get("pages", {})

        # Create new page
        new_page = await context.new_page()
        page_id = f"page_{len(pages) + 1}"
        pages[page_id] = new_page

        # Update session
        session["pages"] = pages
        session["current_page_id"] = page_id
        session["page"] = new_page

        return {
            "success": True,
            "stdout": f"Created new tab [{page_id}], total tabs: {len(pages)}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to create new tab: {str(e)}",
        }


async def switch_tab(page_id: str, browser_id: str = "default") -> Dict[str, Any]:
    """Switch to specified tab"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        if not page_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Missing page_id parameter",
            }

        pages = session.get("pages", {})

        if page_id not in pages:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Tab [{page_id}] not found, available tabs: {', '.join(pages.keys())}",
            }

        # Switch to specified tab
        session["current_page_id"] = page_id
        session["page"] = pages[page_id]

        return {
            "success": True,
            "stdout": f"Switched to tab [{page_id}]",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to switch tab: {str(e)}",
        }


async def close_tab(page_id: str, browser_id: str = "default") -> Dict[str, Any]:
    """Close specified tab"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        if not page_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Missing page_id parameter",
            }

        pages = session.get("pages", {})

        if page_id not in pages:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Tab [{page_id}] not found, available tabs: {', '.join(pages.keys())}",
            }

        # Close tab
        await pages[page_id].close()
        del pages[page_id]

        # If closing current tab, switch to another
        if session["current_page_id"] == page_id:
            if pages:
                # Switch to first available tab
                new_current_id = list(pages.keys())[0]
                session["current_page_id"] = new_current_id
                session["page"] = pages[new_current_id]
            else:
                # No more tabs, clear
                session["current_page_id"] = None
                session["page"] = None

        session["pages"] = pages

        return {
            "success": True,
            "stdout": f"Closed tab [{page_id}], remaining tabs: {len(pages)}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to close tab: {str(e)}",
        }


async def go_back(browser_id: str = "default") -> Dict[str, Any]:
    """Go back to previous page"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Check if can go back
        can_go_back = await page.evaluate("() => window.history.length > 1")

        if not can_go_back:
            return {
                "success": False,
                "stdout": "",
                "stderr": "No page to go back to",
            }

        # Go back
        await page.go_back()

        return {
            "success": True,
            "stdout": "Went back to previous page",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to go back: {str(e)}",
        }


async def go_forward(browser_id: str = "default") -> Dict[str, Any]:
    """Go forward to next page"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Go forward
        await page.go_forward()

        return {
            "success": True,
            "stdout": "Went forward to next page",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to go forward: {str(e)}",
        }


async def scroll_to(
    scroll_x: int = 0, scroll_y: int = 0, browser_id: str = "default"
) -> Dict[str, Any]:
    """Scroll to specified position"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Scroll to specified position
        await page.evaluate(f"window.scrollTo({scroll_x}, {scroll_y})")

        return {
            "success": True,
            "stdout": f"Scrolled to position ({scroll_x}, {scroll_y})",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to scroll: {str(e)}",
        }


async def scroll_down(
    scroll_amount: int = 300, browser_id: str = "default"
) -> Dict[str, Any]:
    """Scroll down the page"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Get current scroll position
        current_scroll = await page.evaluate("window.scrollY")
        new_scroll = current_scroll + scroll_amount

        # Scroll down
        await page.evaluate(f"window.scrollTo(0, {new_scroll})")

        return {
            "success": True,
            "stdout": f"Scrolled down {scroll_amount} pixels",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to scroll down: {str(e)}",
        }


async def scroll_up(
    scroll_amount: int = 300, browser_id: str = "default"
) -> Dict[str, Any]:
    """Scroll up the page"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Get current scroll position
        current_scroll = await page.evaluate("window.scrollY")
        new_scroll = current_scroll - scroll_amount

        # Ensure new_scroll is not less than 0
        if new_scroll < 0:
            new_scroll = 0

        # Scroll up
        await page.evaluate(f"window.scrollTo(0, {new_scroll})")

        return {
            "success": True,
            "stdout": f"Scrolled up {scroll_amount} pixels",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to scroll up: {str(e)}",
        }


async def get_cookies(browser_id: str = "default") -> Dict[str, Any]:
    """Get all cookies"""
    try:
        session = get_browser_session(browser_id)
        if session["context"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        context = session["context"]

        # Get all cookies
        cookies = await context.cookies()

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_cookies_{timestamp}.json"

        # Save cookies as JSON
        filename.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "success": True,
            "stdout": f"Got {len(cookies)} cookies. Saved to: {filename}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get cookies: {str(e)}",
        }


async def set_cookies(cookies_data: str, browser_id: str = "default") -> Dict[str, Any]:
    """Set cookies from JSON string"""
    try:
        session = get_browser_session(browser_id)
        if session["context"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        context = session["context"]

        # Parse cookies from JSON string
        cookies = json.loads(cookies_data)

        if not isinstance(cookies, list):
            return {
                "success": False,
                "stdout": "",
                "stderr": "Cookies must be a list",
            }

        # Set cookies
        await context.add_cookies(cookies)

        return {
            "success": True,
            "stdout": f"Set {len(cookies)} cookies",
            "stderr": "",
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid JSON format for cookies: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to set cookies: {str(e)}",
        }


async def clear_cookies(browser_id: str = "default") -> Dict[str, Any]:
    """Clear all cookies"""
    try:
        session = get_browser_session(browser_id)
        if session["context"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        context = session["context"]

        # Clear cookies
        await context.clear_cookies()

        return {
            "success": True,
            "stdout": "Cleared all cookies",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to clear cookies: {str(e)}",
        }


async def get_local_storage(browser_id: str = "default") -> Dict[str, Any]:
    """Get all localStorage data"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Get all localStorage data
        local_storage = await page.evaluate(
            """() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }"""
        )

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_local_storage_{timestamp}.json"

        filename.write_text(
            json.dumps(local_storage, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "success": True,
            "stdout": f"Got {len(local_storage)} localStorage items. Saved to: {filename}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get localStorage: {str(e)}",
        }


async def set_local_storage(
    data: str, clear: bool = False, browser_id: str = "default"
) -> Dict[str, Any]:
    """Set localStorage from JSON string"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Parse data from JSON string
        storage_data = json.loads(data)

        if not isinstance(storage_data, dict):
            return {
                "success": False,
                "stdout": "",
                "stderr": "Data must be a dictionary",
            }

        if clear:
            # Clear all localStorage
            await page.evaluate("() => localStorage.clear()")

        # Set localStorage data
        if storage_data:
            await page.evaluate(
                """(data) => {
                    for (const [key, value] of Object.entries(data)) {
                        localStorage.setItem(key, value);
                    }
                }""",
                storage_data,
            )

        action_desc = "Cleared and set" if clear else "Set"
        return {
            "success": True,
            "stdout": f"{action_desc} {len(storage_data)} localStorage items",
            "stderr": "",
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Invalid JSON format for data: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to set localStorage: {str(e)}",
        }


async def start_network_monitor(browser_id: str = "default") -> Dict[str, Any]:
    """Start network monitor"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Initialize network requests list
        if "network_requests" not in session:
            session["network_requests"] = []

        # Setup request and response listeners
        def handle_request(request):
            request_info = {
                "type": "request",
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            session["network_requests"].append(request_info)

        def handle_response(response):
            response_info = {
                "type": "response",
                "url": response.url,
                "status": response.status,
                "headers": dict(response.headers),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            session["network_requests"].append(response_info)

        # Add listeners
        page.on("request", handle_request)
        page.on("response", handle_response)

        return {"success": True, "stdout": "Network monitor started", "stderr": ""}
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to start network monitor: {str(e)}",
        }


async def get_network_requests(browser_id: str = "default") -> Dict[str, Any]:
    """Get network requests"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        network_requests = session.get("network_requests", [])

        if not network_requests:
            return {
                "success": True,
                "stdout": "No network requests recorded",
                "stderr": "",
            }

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_network_requests_{timestamp}.json"

        filename.write_text(
            json.dumps(network_requests, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "success": True,
            "stdout": f"Got {len(network_requests)} network requests. Saved to: {filename}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get network requests: {str(e)}",
        }


async def element_screenshot(
    selector: str, browser_id: str = "default"
) -> Dict[str, Any]:
    """Take screenshot of element"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Missing selector parameter",
            }

        page = session["page"]

        # Find element
        element = await page.wait_for_selector(selector, timeout=30000)

        if not element:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Element not found: {selector}",
            }

        # Take screenshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_element_screenshot_{timestamp}.png"

        await element.screenshot(path=str(filename))

        return {
            "success": True,
            "stdout": f"Element screenshot taken for [{selector}]. Saved to: {filename}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to take element screenshot: {str(e)}",
        }


async def export_pdf(browser_id: str = "default") -> Dict[str, Any]:
    """Export page to PDF"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Export PDF
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_page_{timestamp}.pdf"

        await page.pdf(path=str(filename))

        return {
            "success": True,
            "stdout": f"PDF exported. Saved to: {filename}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to export PDF: {str(e)}",
        }


async def get_performance_metrics(browser_id: str = "default") -> Dict[str, Any]:
    """Get page performance metrics"""
    try:
        session = get_browser_session(browser_id)
        if session["page"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Browser [{browser_id}] not launched",
            }

        page = session["page"]

        # Get performance metrics
        metrics = await page.evaluate("""() => {
            const perfData = performance.timing;
            const metrics = {
                "页面加载时间": perfData.loadEventEnd - perfData.navigationStart,
                "DOM 解析时间": perfData.domComplete - perfData.domInteractive,
                "资源加载时间": perfData.loadEventEnd - perfData.domContentLoadedEventEnd,
                "DNS 查询时间": perfData.domainLookupEnd - perfData.domainLookupStart,
                "TCP 连接时间": perfData.connectEnd - perfData.connectStart,
                "请求响应时间": perfData.responseStart - perfData.requestStart,
                "文档下载时间": perfData.responseEnd - perfData.responseStart,
                "DOM 内容加载时间": perfData.domContentLoadedEventEnd - perfData.navigationStart,
            };
            return metrics;
        }""")

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = temp_dir / f"{browser_id}_performance_metrics_{timestamp}.json"

        filename.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "success": True,
            "stdout": f"Performance metrics obtained. Saved to: {filename}",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to get performance metrics: {str(e)}",
        }


def send_to_daemon(
    action: str, params: Dict[str, Any], socket_path: Path | None = None
) -> Dict[str, Any]:
    """Send request to daemon and get response

    Args:
        action: Action to perform (e.g., 'launch', 'navigate', 'click')
        params: Parameters for the action
        socket_path: Socket path (default: get_socket_path())

    Returns:
        Response dict with 'success', 'stdout', 'stderr' keys
    """
    socket_path = socket_path or get_socket_path()

    async def _send() -> Dict[str, Any]:
        try:
            # Connect to daemon socket
            reader, writer = await asyncio.open_unix_connection(str(socket_path))

            # Prepare request
            request = {"action": action, "params": params}
            request_json = json.dumps(request, ensure_ascii=False)
            request_data = (
                f"Content-Length: {len(request_json)}\r\n\r\n{request_json}".encode()
            )

            # Send request
            writer.write(request_data)
            await writer.drain()

            # Read response header
            header_line = await reader.readline()
            if not header_line:
                raise Exception("No response from daemon")

            header = header_line.decode().strip()
            if header.startswith("Content-Length:"):
                content_length = int(header.split(":")[1].strip())
            else:
                raise Exception(f"Invalid response header: {header}")

            # Read empty line
            await reader.readline()

            # Read response content
            content = await reader.readexactly(content_length)
            response: Dict[str, Any] = json.loads(content.decode())

            # Close connection
            writer.close()
            await writer.wait_closed()

            return response

        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Daemon not running at {socket_path}. Please start daemon first.",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to communicate with daemon: {str(e)}",
            }

    # Run async function
    return asyncio.run(_send())


if __name__ == "__main__":
    app()
