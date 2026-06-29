#!/usr/bin/env python3
"""Capture a Streamlit demo loop from a running Chrome DevTools session.

This intentionally uses only the Python standard library so it can run in the
project venv without adding browser automation dependencies.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import socket
import struct
import time
import urllib.parse
import urllib.request
from pathlib import Path


class CDPClient:
    def __init__(self, ws_url: str) -> None:
        self.url = urllib.parse.urlparse(ws_url)
        self.sock = socket.create_connection((self.url.hostname, self.url.port), timeout=10)
        self.next_id = 1
        self._handshake()

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = self.url.path
        if self.url.query:
            path += "?" + self.url.query
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.url.hostname}:{self.url.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket handshake failed: {response[:200]!r}")

    def _read_exact(self, n: int) -> bytes:
        chunks = []
        remaining = n
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise EOFError("WebSocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_text(self) -> str:
        parts: list[bytes] = []
        while True:
            first, second = self._read_exact(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 8:
                raise EOFError("WebSocket closed by peer")
            if opcode in (1, 2, 0):
                parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8")

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = random.randbytes(4) if hasattr(random, "randbytes") else os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def command(self, method: str, params: dict | None = None) -> dict:
        msg_id = self.next_id
        self.next_id += 1
        payload = {"id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send_text(json.dumps(payload, separators=(",", ":")))
        while True:
            message = json.loads(self._recv_text())
            if message.get("id") == msg_id:
                if "error" in message:
                    raise RuntimeError(f"{method} failed: {message['error']}")
                return message.get("result", {})


def target_ws_url(debugging_url: str) -> str:
    with urllib.request.urlopen(f"{debugging_url.rstrip('/')}/json/list", timeout=10) as response:
        targets = json.load(response)
    for target in targets:
        if target.get("type") == "page":
            return target["webSocketDebuggerUrl"]
    raise RuntimeError("No Chrome page target found")


def wait_for_text(client: CDPClient, text: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    expression = f"document.body && document.body.innerText.includes({json.dumps(text)})"
    while time.time() < deadline:
        result = client.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("result", {}).get("value"):
            return
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for text: {text}")


def capture_png(client: CDPClient, output: Path) -> None:
    result = client.command(
        "Page.captureScreenshot",
        {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
    )
    output.write_bytes(base64.b64decode(result["data"]))


def eval_js(client: CDPClient, expression: str) -> None:
    result = client.command("Runtime.evaluate", {"expression": expression, "awaitPromise": True})
    if "exceptionDetails" in result:
        raise RuntimeError(f"JavaScript evaluation failed: {result['exceptionDetails']}")


def navigate(client: CDPClient, url: str, wait_text: str) -> None:
    client.command("Page.navigate", {"url": url})
    wait_for_text(client, wait_text)
    eval_js(
        client,
        "(() => {"
        "const main = document.querySelector('section.stMain');"
        "if (main) { main.scrollTop = 0; } else { window.scrollTo(0, 0); }"
        "})()",
    )
    time.sleep(1.5)


def hold(client: CDPClient, frames: list[Path], out_dir: Path, seconds: float, fps: int) -> None:
    total = max(1, round(seconds * fps))
    for _ in range(total):
        frames.append(out_dir / f"frame_{len(frames):04d}.png")
        capture_png(client, frames[-1])
        time.sleep(1 / fps)


def scroll_to(client: CDPClient, frames: list[Path], out_dir: Path, top: int, seconds: float, fps: int) -> None:
    start_result = client.command(
        "Runtime.evaluate",
        {
            "expression": "document.querySelector('section.stMain')?.scrollTop || window.scrollY",
            "returnByValue": True,
        },
    )
    start = int(start_result.get("result", {}).get("value", 0))
    total = max(2, round(seconds * fps))
    for i in range(total):
        progress = i / (total - 1)
        eased = progress * progress * (3 - 2 * progress)
        y = round(start + (top - start) * eased)
        eval_js(
            client,
            "(() => {"
            "const main = document.querySelector('section.stMain');"
            f"if (main) {{ main.scrollTop = {y}; }} else {{ window.scrollTo(0, {y}); }}"
            "})()",
        )
        frames.append(out_dir / f"frame_{len(frames):04d}.png")
        capture_png(client, frames[-1])
        time.sleep(1 / fps)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debugging-url", default="http://127.0.0.1:9223")
    parser.add_argument("--app-url", default="http://localhost:8560")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--fps", type=int, default=8)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.png"):
        old.unlink()

    client = CDPClient(target_ws_url(args.debugging_url))
    client.command("Page.enable")
    client.command("Runtime.enable")
    client.command(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1600, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )

    frames: list[Path] = []
    navigate(client, f"{args.app_url}/", "Hilti Territory Growth Dashboard")
    hold(client, frames, out_dir, 4.0, args.fps)
    scroll_to(client, frames, out_dir, 540, 5.0, args.fps)
    hold(client, frames, out_dir, 3.0, args.fps)

    navigate(client, f"{args.app_url}/External_Market_Intelligence", "External Data Integration Check")
    hold(client, frames, out_dir, 4.0, args.fps)
    scroll_to(client, frames, out_dir, 420, 4.0, args.fps)

    navigate(client, f"{args.app_url}/Methodology_Notes", "Methodology Notes")
    hold(client, frames, out_dir, 4.0, args.fps)
    scroll_to(client, frames, out_dir, 360, 4.0, args.fps)

    navigate(client, f"{args.app_url}/", "Hilti Territory Growth Dashboard")
    hold(client, frames, out_dir, 4.0, args.fps)

    print(f"Captured {len(frames)} frames to {out_dir}")


if __name__ == "__main__":
    main()
