"""
Capture worker for Taobao visual collection contracts.

The worker executes a bounded session contract through the Midscene computer MCP
over stdio: system screenshots in, system mouse/keyboard/scroll actions out. It
does not read browser DOM, HTML, network, storage, cookies, CDP, or page source.
"""
import base64
import json
import os
import queue
import random
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules.page_sampling import write_task_event, write_tile_summary
from modules.utils import ensure_dir
from modules.visual_control import write_worker_runtime


MCP_REQUIRED_TOOLS = {
    "computer_connect",
    "take_screenshot",
    "act",
}
MCP_OPTIONAL_TOOLS = {"assert"}
REAL_NOT_AVAILABLE_STATUS = "real_not_available"


def run_capture_worker(contract_path: str) -> Dict[str, Any]:
    """Run the capture worker against a contract JSON file.

    The worker tries to execute the contract through the local Midscene computer
    MCP stdio launcher. If that environment is not available, it writes explicit
    real_not_available results instead of pretending a capture occurred.
    """
    started = time.monotonic()
    contract = _read_json(contract_path)
    run_id = str(contract.get("run_id") or "")
    session_index = int(contract.get("session_index") or 0)
    task_dir = str(contract.get("task_dir") or os.path.dirname(os.path.dirname(contract_path)))
    session_dir = str(contract.get("session_dir") or os.path.dirname(contract_path))
    session_result_path = str(
        contract.get("session_result_path")
        or os.path.join(session_dir, "session_worker_result.json")
    )
    keyword_tasks = contract.get("keyword_tasks") or []
    now = _now()

    write_worker_runtime(
        run_id,
        session_index,
        "capture",
        "running",
        contract_path=contract_path,
        worker_role="visual_capture_worker",
        schema="taobao_visual_capture_worker_v1",
        started_at=now,
    )
    write_task_event(
        task_dir,
        event="visual_capture_worker_started",
        run_id=run_id,
        session_index=session_index,
        contract_path=contract_path,
        keyword_count=len(keyword_tasks),
    )

    real_result = _run_real_capture_contract(
        contract=contract,
        contract_path=contract_path,
        run_id=run_id,
        session_index=session_index,
        task_dir=task_dir,
        keyword_tasks=keyword_tasks,
    )
    keyword_results = real_result["keyword_results"]
    session_status = real_result["status"]
    stop_reason = real_result["stop_reason"]
    notes = real_result["notes"]

    elapsed_seconds = round(time.monotonic() - started, 3)
    session_result = {
        "schema": "taobao_visual_capture_worker_result_v1",
        "run_id": run_id,
        "session_index": session_index,
        "worker_role": "visual_capture_worker",
        "status": session_status,
        "processed_keywords": len(keyword_results),
        "stop_reason": stop_reason,
        "keyword_results": keyword_results,
        "elapsed_seconds": elapsed_seconds,
        "notes": notes,
        "created_at": now,
        "updated_at": _now(),
    }
    _write_json(session_result_path, session_result)
    write_task_event(
        task_dir,
        event="visual_capture_worker_finished",
        level="info" if session_status == "captured" else "warning",
        run_id=run_id,
        session_index=session_index,
        status=session_status,
        stop_reason=stop_reason,
        processed_keywords=len(keyword_results),
        session_result_path=session_result_path,
    )
    write_worker_runtime(
        run_id,
        session_index,
        "capture",
        session_status,
        contract_path=contract_path,
        session_result_path=session_result_path,
        processed_keywords=len(keyword_results),
        stop_reason=stop_reason,
        elapsed_seconds=elapsed_seconds,
        finished_at=_now(),
    )
    return {
        "ok": True,
        "run_id": run_id,
        "session_index": session_index,
        "status": session_status,
        "session_result": session_result_path,
        "processed_keywords": len(keyword_results),
    }


def _run_real_capture_contract(
    contract: Dict[str, Any],
    contract_path: str,
    run_id: str,
    session_index: int,
    task_dir: str,
    keyword_tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    launcher = _mcp_launcher_path()
    if not launcher:
        return _real_unavailable_results(
            keyword_tasks,
            run_id,
            session_index,
            task_dir,
            stop_reason="midscene_mcp_launcher_missing",
            notes="Real capture requires local/start_midscene_computer_mcp.sh.",
        )

    try:
        with MidsceneStdioClient(_mcp_command(launcher), cwd=_project_root()) as client:
            tools = client.list_tools()
            missing = sorted(MCP_REQUIRED_TOOLS - set(tools))
            if missing:
                return _real_unavailable_results(
                    keyword_tasks,
                    run_id,
                    session_index,
                    task_dir,
                    stop_reason="midscene_mcp_tools_missing",
                    notes=f"Midscene MCP missing required tools: {', '.join(missing)}.",
                )

            write_task_event(
                task_dir,
                event="visual_capture_real_mcp_connected",
                run_id=run_id,
                session_index=session_index,
                contract_path=contract_path,
                tools=sorted(set(tools) & (MCP_REQUIRED_TOOLS | MCP_OPTIONAL_TOOLS)),
            )
            client.call_tool("computer_connect", {})

            keyword_results = []
            for fallback_index, task in enumerate(keyword_tasks, start=1):
                if fallback_index > 1:
                    _sleep_between_keywords(contract, run_id, session_index, task_dir, task)
                keyword_result = _capture_keyword_with_mcp(
                    client=client,
                    task=task,
                    contract=contract,
                    run_id=run_id,
                    session_index=session_index,
                    task_dir=task_dir,
                    fallback_index=fallback_index,
                    tools=tools,
                )
                keyword_results.append(keyword_result)
                if keyword_result.get("status") == "needs_review":
                    return {
                        "status": "needs_review",
                        "stop_reason": keyword_result.get("stop_reason") or "keyword_needs_review",
                        "keyword_results": keyword_results,
                        "notes": "Real Midscene computer MCP capture stopped for human review.",
                    }

            session_status = (
                "captured"
                if keyword_results and all(item.get("status") == "captured" for item in keyword_results)
                else "failed"
            )
            return {
                "status": session_status,
                "stop_reason": "completed" if session_status == "captured" else "no_keywords_captured",
                "keyword_results": keyword_results,
                "notes": (
                    "Real Midscene computer MCP capture completed. Product rows are still "
                    "owned by extract/ingest from retained visible screenshots."
                ),
            }
    except Exception as exc:
        return _real_unavailable_results(
            keyword_tasks,
            run_id,
            session_index,
            task_dir,
            stop_reason="midscene_mcp_stdio_unavailable",
            notes=f"Midscene computer MCP was not usable from this Python worker: {exc}",
        )


def _capture_keyword_with_mcp(
    client: "MidsceneStdioClient",
    task: Dict[str, Any],
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    fallback_index: int,
    tools: List[str],
) -> Dict[str, Any]:
    keyword = str(task.get("keyword") or "")
    keyword_index = int(task.get("keyword_index") or task.get("index") or fallback_index)
    capture_plan = task.get("capture_plan") or {}
    evidence_dir = str(task.get("evidence_dir") or "")
    if not evidence_dir:
        evidence_dir = os.path.join(task_dir, "evidence", f"keyword_{keyword_index:03d}")
    ensure_dir(evidence_dir)
    started = time.monotonic()
    screenshots: List[Dict[str, Any]] = []
    max_tiles = int(capture_plan.get("max_tiles_per_keyword") or 1)
    max_tiles = max(1, max_tiles)
    scroll_distance = int(capture_plan.get("tile_scroll_distance_px") or 0)
    scroll_distance = max(1, scroll_distance)
    page_load_wait = float((contract.get("config") or {}).get("page_load_wait") or 8.0)
    allow_act = bool((contract.get("model_boundary") or {}).get("allow_midscene_act", True))

    try:
        if not allow_act:
            raise RuntimeError("midscene_act_disabled_for_real_capture")
        _call_act(
            client,
            _keyword_search_prompt(keyword=keyword, scroll_distance=scroll_distance),
        )
        _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, "after_keyword_search_act")
        time.sleep(page_load_wait)

        for tile_index in range(max_tiles):
            tile_id = f"tile_{tile_index:02d}"
            tile_path = _tile_path(capture_plan, evidence_dir, tile_index)
            screenshot = client.capture_screenshot(tile_path)
            screenshots.append(
                {
                    "tile_id": tile_id,
                    "path": tile_path,
                    "mime_type": screenshot.get("mime_type") or "image/png",
                    "captured_at": _now(),
                }
            )
            write_tile_summary(
                task_dir=task_dir,
                run_id=run_id,
                keyword=keyword,
                tile_id=tile_id,
                scroll_distance_px=0 if tile_index == 0 else scroll_distance,
                rough_state="visible_results_unverified",
                image_path=tile_path,
                image_retained=True,
                notes="captured_by_midscene_computer_mcp",
            )
            if tile_index < max_tiles - 1:
                _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, f"before_scroll_{tile_index + 1}")
                _call_act(
                    client,
                    _next_tile_prompt(
                        keyword=keyword,
                        tile_index=tile_index + 1,
                        scroll_distance=scroll_distance,
                    ),
                )
                _sleep_micro_pause(contract, run_id, session_index, task_dir, keyword, f"after_scroll_act_{tile_index + 1}")

        elapsed = round(time.monotonic() - started, 3)
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="captured",
            rough_state="visible_results_unverified",
            stop_reason="captured",
            notes="Captured viewport tiles through Midscene computer MCP; product extraction is deferred.",
            screenshots=screenshots,
            elapsed_seconds=elapsed,
        )
    except Exception as exc:
        abnormal_path = (
            task.get("abnormal_screenshot_path")
            or capture_plan.get("abnormal_screenshot_path")
            or os.path.join(evidence_dir, "abnormal_state.png")
        )
        try:
            client.capture_screenshot(str(abnormal_path))
            abnormal_screenshot = str(abnormal_path)
        except Exception:
            abnormal_screenshot = ""
        elapsed = round(time.monotonic() - started, 3)
        return _write_keyword_result(
            task=task,
            run_id=run_id,
            session_index=session_index,
            task_dir=task_dir,
            fallback_index=fallback_index,
            mode="real",
            status="needs_review",
            rough_state="mcp_action_failed",
            stop_reason="midscene_mcp_action_failed",
            notes=f"Real MCP action failed before completing keyword capture: {exc}",
            screenshots=screenshots,
            abnormal_screenshot=abnormal_screenshot,
            elapsed_seconds=elapsed,
        )


def _sleep_between_keywords(
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    task: Dict[str, Any],
) -> None:
    behavior = contract.get("visual_behavior") or {}
    bounds = behavior.get("inter_keyword_pause_seconds") or [30, 60]
    try:
        low, high = float(bounds[0]), float(bounds[1])
    except Exception:
        low, high = 30.0, 60.0
    seconds = random.uniform(max(0.0, low), max(low, high))
    keyword = str(task.get("keyword") or "")
    write_task_event(
        task_dir,
        event="visual_capture_inter_keyword_pause",
        run_id=run_id,
        session_index=session_index,
        keyword=keyword,
        seconds=round(seconds, 3),
    )
    time.sleep(seconds)


def _sleep_micro_pause(
    contract: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    keyword: str,
    reason: str,
) -> None:
    seconds = _sample_micro_pause_seconds(contract.get("visual_behavior") or {})
    write_task_event(
        task_dir,
        event="visual_capture_micro_pause",
        run_id=run_id,
        session_index=session_index,
        keyword=keyword,
        reason=reason,
        seconds=round(seconds, 3),
    )
    time.sleep(seconds)


def _sample_micro_pause_seconds(behavior: Dict[str, Any]) -> float:
    distribution = behavior.get("micro_pause_distribution") or {
        "short": "0.8,3,0.82",
        "medium": "3,6,0.14",
        "long": "6,10,0.04",
    }
    segments = []
    for value in distribution.values():
        try:
            low, high, weight = [float(part) for part in str(value).split(",", 2)]
            if weight > 0:
                segments.append((max(0.0, low), max(low, high), weight))
        except Exception:
            continue
    if not segments:
        segments = [(0.8, 3.0, 1.0)]
    total = sum(item[2] for item in segments)
    pick = random.uniform(0, total)
    acc = 0.0
    for low, high, weight in segments:
        acc += weight
        if pick <= acc:
            return random.uniform(low, high)
    low, high, _ = segments[-1]
    return random.uniform(low, high)


def _real_unavailable_results(
    keyword_tasks: List[Dict[str, Any]],
    run_id: str,
    session_index: int,
    task_dir: str,
    stop_reason: str,
    notes: str,
) -> Dict[str, Any]:
    results = []
    for fallback_index, task in enumerate(keyword_tasks, start=1):
        results.append(
            _write_keyword_result(
                task=task,
                run_id=run_id,
                session_index=session_index,
                task_dir=task_dir,
                fallback_index=fallback_index,
                mode="real",
                status=REAL_NOT_AVAILABLE_STATUS,
                rough_state="not_started",
                stop_reason=stop_reason,
                notes=notes,
            )
        )
    return {
        "status": REAL_NOT_AVAILABLE_STATUS,
        "stop_reason": stop_reason,
        "keyword_results": results,
        "notes": notes,
    }


def _write_keyword_result(
    task: Dict[str, Any],
    run_id: str,
    session_index: int,
    task_dir: str,
    fallback_index: int,
    mode: str,
    status: str,
    rough_state: str,
    stop_reason: str,
    notes: str,
    screenshots: Optional[List[Dict[str, Any]]] = None,
    abnormal_screenshot: str = "",
    elapsed_seconds: float = 0,
) -> Dict[str, Any]:
    keyword = str(task.get("keyword") or "")
    keyword_index = int(task.get("keyword_index") or task.get("index") or fallback_index)
    evidence_dir = str(task.get("evidence_dir") or "")
    if not evidence_dir:
        evidence_dir = os.path.join(task_dir, "evidence", f"keyword_{keyword_index:03d}")
    result_path = str(
        task.get("result_path")
        or task.get("keyword_result_path")
        or os.path.join(evidence_dir, "keyword_result.json")
    )
    capture_plan = task.get("capture_plan") or {}
    now = _now()
    payload = {
        "schema": "taobao_visual_capture_keyword_result_v1",
        "task_id": task.get("task_id") or f"{run_id}-s{session_index:02d}-k{keyword_index:03d}",
        "keyword_index": keyword_index,
        "keyword": keyword,
        "status": status,
        "rough_state": rough_state,
        "mode": mode,
        "screenshots": screenshots or [],
        "abnormal_screenshot": abnormal_screenshot,
        "abnormal_screenshot_path": task.get("abnormal_screenshot_path")
        or capture_plan.get("abnormal_screenshot_path")
        or "",
        "elapsed_seconds": elapsed_seconds,
        "stop_reason": stop_reason,
        "notes": notes,
        "capture_plan": capture_plan,
        "result_path": result_path,
        "created_at": now,
        "updated_at": now,
    }
    _write_json(result_path, payload)
    write_task_event(
        task_dir,
        event="visual_capture_keyword_result_written",
        level="info" if status == "captured" else "warning",
        run_id=run_id,
        session_index=session_index,
        keyword=keyword,
        task_id=payload["task_id"],
        keyword_index=keyword_index,
        status=status,
        rough_state=rough_state,
        stop_reason=stop_reason,
        result_path=result_path,
    )
    return {
        "task_id": payload["task_id"],
        "keyword_index": keyword_index,
        "keyword": keyword,
        "status": status,
        "rough_state": rough_state,
        "mode": mode,
        "result_path": result_path,
        "stop_reason": stop_reason,
    }


class MidsceneStdioClient:
    """Tiny MCP stdio client for the local midscene-computer server."""

    def __init__(self, command: List[str], cwd: str, timeout_seconds: float = 60.0):
        self.command = command
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.process: Optional[subprocess.Popen] = None
        self._next_id = 1
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._stderr_lines: "queue.Queue[str]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def __enter__(self) -> "MidsceneStdioClient":
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "taobao_visual_capture_worker",
                    "version": "1.0",
                },
            },
        )
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()

    def list_tools(self) -> List[str]:
        result = self.request("tools/list", {})
        return [item.get("name") for item in result.get("tools", []) if item.get("name")]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(_tool_text(result) or f"MCP tool failed: {name}")
        return result

    def capture_screenshot(self, path: str) -> Dict[str, Any]:
        result = self.call_tool("take_screenshot", {})
        image = _first_image(result)
        if not image:
            raise RuntimeError("take_screenshot returned no image content")
        ensure_dir(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(base64.b64decode(image["data"]))
        return {"path": path, "mime_type": image.get("mimeType") or "image/png"}

    def request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            self._raise_if_dead()
            try:
                message = self._responses.get(timeout=0.2)
            except queue.Empty:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(message["error"].get("message") or message["error"])
            return message.get("result") or {}
        raise TimeoutError(f"MCP request timed out: {method}; stderr={self._stderr_tail()}")

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process is not running")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._responses.put(json.loads(line))
            except json.JSONDecodeError:
                self._stderr_lines.put(f"non-json stdout: {line[:500]}")

    def _read_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return
        for line in self.process.stderr:
            if line.strip():
                self._stderr_lines.put(line.strip())

    def _raise_if_dead(self) -> None:
        if self.process and self.process.poll() is not None:
            raise RuntimeError(f"MCP process exited with {self.process.returncode}: {self._stderr_tail()}")

    def _stderr_tail(self) -> str:
        items = []
        while True:
            try:
                items.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        return "\n".join(items[-8:])


def _call_act(client: MidsceneStdioClient, prompt: str) -> None:
    client.call_tool("act", {"prompt": prompt})


def _keyword_search_prompt(keyword: str, scroll_distance: int) -> str:
    return (
        "You are the bounded Taobao capture worker for one keyword. Use only "
        "visible-screen reasoning and system mouse/keyboard actions. Do not read "
        "DOM, HTML, network, cookies, storage, selector maps, page source, or JS "
        "evaluated data. Bring the existing Chrome window with the dedicated "
        "Taobao profile to the foreground if needed. If Codex, Terminal, Cursor, "
        "or another app is visible, switch to Chrome first and do not type the "
        "keyword into that app. If Chrome/Taobao is unavailable, or login, "
        "captcha, security verification, risk warning, unusual account state, "
        "or an automation permission panel is visible, stop and report failure. "
        "From the visible Taobao search box, search exactly this keyword: "
        f"{keyword!r}. Wait until visible search results settle. Leave the page "
        "positioned at the first results viewport. Do not output product rows. "
        f"Later tile captures will use about {scroll_distance} px between viewports."
    )


def _next_tile_prompt(keyword: str, tile_index: int, scroll_distance: int) -> str:
    return (
        "You are continuing the bounded Taobao capture session using only "
        "visible-screen reasoning and system mouse/keyboard/scroll actions. The "
        f"current keyword is {keyword!r}. If login, captcha, security/risk, "
        "unusual account state, white skeleton, or a permission panel is visible, "
        "stop and report failure. Otherwise move to the next visible results "
        f"viewport for tile_{tile_index:02d}; use a normal page-level downward "
        f"scroll of about {scroll_distance} px if appropriate, then wait for "
        "visible content to settle. Do not output product rows and do not change "
        "account state."
    )


def _first_image(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for item in result.get("content") or []:
        if item.get("type") == "image" and item.get("data"):
            return item
    return None


def _tool_text(result: Dict[str, Any]) -> str:
    texts = [
        str(item.get("text") or "")
        for item in result.get("content") or []
        if item.get("type") == "text"
    ]
    return "\n".join(text for text in texts if text)


def _tile_path(capture_plan: Dict[str, Any], evidence_dir: str, tile_index: int) -> str:
    if tile_index == 0 and capture_plan.get("primary_screenshot_path"):
        return str(capture_plan["primary_screenshot_path"])
    pattern = str(capture_plan.get("tile_path_pattern") or os.path.join(evidence_dir, "tile_<NN>.png"))
    return pattern.replace("<NN>", f"{tile_index:02d}")


def _mcp_launcher_path() -> str:
    launcher = os.environ.get("TAOBAO_MIDSCENE_MCP_LAUNCHER", "").strip()
    if launcher and os.path.exists(launcher):
        return launcher
    default = os.path.join(_project_root(), "local", "start_midscene_computer_mcp.sh")
    return default if os.path.exists(default) else ""


def _mcp_command(launcher: str) -> List[str]:
    if launcher.endswith(".sh"):
        return ["/bin/bash", launcher]
    return [launcher]


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
