from __future__ import annotations

import asyncio
from typing import Callable

from .const import (
    SUBSCRIBE_WILDCARD,
    RECONNECT_MIN_DELAY,
    RECONNECT_MAX_DELAY,
    ENCODING,
)

ValueCallback = Callable[[str], None]
RestartCallback = Callable[[], None]

class PLCComSClient:
    def __init__(self, hass, host: str, port: int):
        self.hass = hass
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.variables: list[str] = []
        self._diff_callbacks: dict[str, ValueCallback] = {}
        self._restart_callback: RestartCallback | None = None
        self._io_lock = asyncio.Lock()
        self._task = None
        self._stop_event = asyncio.Event()
        self._connected = False
        self._subscribed = False
        self._plc_run_state = None

    async def async_connect(self, list_only: bool = False) -> None:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self._connected = True
        self._subscribed = False
        await self._send("LIST:")
        await self._read_list()

    async def async_disconnect(self) -> None:
        self.stop()
        if self._task:
            try: await self._task
            except Exception: pass
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.reader = None
        self.writer = None
        self._connected = False
        self._subscribed = False

    def start(self) -> None:
        if self._task and not self._task.done(): return
        self._stop_event.clear()
        self._task = self.hass.loop.create_task(self._run())

    def stop(self) -> None:
        self._stop_event.set()

    def register_value_entity(self, var_name: str, callback: ValueCallback) -> None:
        self._diff_callbacks[var_name.lower()] = callback

    def unregister_value_entity(self, var_name: str) -> None:
        self._diff_callbacks.pop(var_name.lower(), None)

    def register_restart_callback(self, callback: RestartCallback) -> None:
        self._restart_callback = callback

    async def _send(self, msg: str) -> None:
        async with self._io_lock:
            self.writer.write((msg + "\n").encode(ENCODING))
            await self.writer.drain()

    async def _read_line(self) -> str:
        line = await self.reader.readline()
        if not line: raise ConnectionError("PLCComS connection closed")
        return line.decode(ENCODING, errors="strict").strip()

    async def _read_list(self) -> None:
        self.variables = []
        while True:
            line = await self._read_line()
            if line == "LIST:" or not line.startswith("LIST:"): break
            payload = line.split(":", 1)[1].strip()
            if not payload: break
            var = payload.split(",", 1)[0].strip()
            var = var.rstrip("*").rstrip("~")
            if var: self.variables.append(var)

    async def async_get(self, var_name: str) -> str:
        async with self._io_lock:
            self.writer.write((f"GET:{var_name}\n").encode(ENCODING))
            await self.writer.drain()
            line = await self._read_line()
        head, value = line.split(",", 1)
        return value.strip().strip('"')

    async def async_set(self, var_name: str, value: str) -> None:
        await self._send(f"SET:{var_name},{value}")

    async def async_subscribe(self) -> None:
        if self._subscribed: return
        await self._send(SUBSCRIBE_WILDCARD)
        self._subscribed = True

    async def _run(self) -> None:
        delay = RECONNECT_MIN_DELAY
        while not self._stop_event.is_set():
            try:
                if not self._connected:
                    await self.async_connect()
                    delay = RECONNECT_MIN_DELAY
                if not self._subscribed:
                    await self.async_subscribe()
                line = await self._read_line()
                if line.startswith("DIFF:"):
                    body = line[5:]
                    var, value = body.split(",", 1)
                    var_lower = var.lower()
                    value_stripped = value.strip()
                    
                    if var_lower == "__plc_run":
                        try:
                            plc_run_value = int(value_stripped)
                            if self._plc_run_state == 0 and plc_run_value == 1:
                                await asyncio.sleep(2)
                                await self._reload_variables()
                                if self._restart_callback:
                                    self.hass.async_create_task(self._restart_callback())
                            self._plc_run_state = plc_run_value
                        except (ValueError, TypeError):
                            pass
                    
                    cb = self._diff_callbacks.get(var_lower)
                    if cb: 
                        cb(value_stripped)
            except Exception as exc:
                await asyncio.sleep(delay)
                delay = min(int(delay * 1.6), RECONNECT_MAX_DELAY)
                self._connected = False
                self._subscribed = False

    async def _reload_variables(self) -> None:
        try:
            await self._send("LIST:")
            await self._read_list()
        except Exception as exc:
            pass