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
        self._var_map: dict[str, str] = {}  # lower(var)->real var from LIST

        self._diff_callbacks: dict[str, ValueCallback] = {}
        self._restart_callback: RestartCallback | None = None

        self._io_lock = asyncio.Lock()
        self._task = None
        self._stop_event = asyncio.Event()
        self._connected = False
        self._subscribed = False
        self._plc_run_state = None

    def resolve_var(self, var_name: str) -> str:
        """Return real variable name (case as reported by LIST)."""
        if not var_name:
            return var_name
        return self._var_map.get(var_name.lower(), var_name)

    async def async_connect(self, list_only: bool = False) -> None:
        """
        list_only=True používame v Config Flow len na test konektivity.
        Tam NESMIEME čítať celý LIST (pri veľkých projektoch to často prekročí timeout).
        """
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self._connected = True
        self._subscribed = False

        if list_only:
            # lacný „ping“: GET na __plc_run (má to aj tvoj runtime hook)
            await self._send("GET:__plc_run")
            # ak PLCComS odpovie hocijako, konektivita je OK
            await self._read_line()
            return

        await self._send("LIST:")
        await self._read_list()

    async def async_disconnect(self) -> None:
        self.stop()
        if self._task:
            try:
                await self._task
            except Exception:
                pass

        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

        self.reader = None
        self.writer = None
        self._connected = False
        self._subscribed = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = self.hass.loop.create_task(self._run())

    def stop(self) -> None:
        self._stop_event.set()

    def register_value_entity(self, var_name: str, callback: ValueCallback) -> None:
        real = self.resolve_var(var_name)
        self._diff_callbacks[real.lower()] = callback

    def unregister_value_entity(self, var_name: str) -> None:
        real = self.resolve_var(var_name)
        self._diff_callbacks.pop(real.lower(), None)

    def register_restart_callback(self, callback: RestartCallback) -> None:
        self._restart_callback = callback

    async def _send(self, msg: str) -> None:
        async with self._io_lock:
            self.writer.write((msg + "\n").encode(ENCODING))
            await self.writer.drain()

    async def _read_line(self) -> str:
        line = await self.reader.readline()
        if not line:
            raise ConnectionError("PLCComS connection closed")
        return line.decode(ENCODING, errors="replace").strip()

    async def _read_list(self) -> None:
        self.variables = []
        self._var_map = {}

        # tolerantné čítanie LIST:
        while True:
            line = await self._read_line()
            if line == "LIST:" or not line.startswith("LIST:"):
                break

            payload = line.split(":", 1)[1].strip()
            if not payload:
                break

            var = payload.split(",", 1)[0].strip()
            var = var.rstrip("*").rstrip("~")
            if not var:
                continue

            self.variables.append(var)
            self._var_map[var.lower()] = var

    def _parse_get_kv(self, line: str) -> tuple[str | None, str]:
        """
        Pokus o parsovanie GET odpovede na (var, value).
        PLCComS býva typicky:
          GET:VAR,"value"
          GET:VAR,value
          VAR,value
        Ak var nevieme zistiť, vrátime (None, value).
        """
        if "," not in line:
            return None, ""

        head, tail = line.split(",", 1)
        head = head.strip()
        tail = tail.strip()

        # odstráň "GET:" ak je tam
        if ":" in head:
            head = head.split(":", 1)[1].strip()

        value = tail
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]

        return (head or None), value

    async def async_get(self, var_name: str) -> str:
        real = self.resolve_var(var_name)
        async with self._io_lock:
            self.writer.write((f"GET:{real}\n").encode(ENCODING))
            await self.writer.drain()
            line = await self._read_line()
        _var, value = self._parse_get_kv(line)
        return value

    async def async_get_many(self, var_names: list[str]) -> list[str]:
        """
        Bulk GET odolný voči tomu, že PLCComS môže odpovedať mimo poradia.
        - Ak odpoveď obsahuje názov premennej, mapujeme podľa nej.
        - Ak odpoveď názov neobsahuje, použijeme fallback: poradie.
        """
        if not var_names:
            return []

        reals = [self.resolve_var(v) for v in var_names]

        async with self._io_lock:
            for r in reals:
                self.writer.write((f"GET:{r}\n").encode(ENCODING))
            await self.writer.drain()

            lines = [await self._read_line() for _ in reals]

        mapped: dict[str, str] = {}
        fallback_values: list[str] = []
        mapped_count = 0

        for line in lines:
            var, value = self._parse_get_kv(line)
            if var:
                mapped[var.lower()] = value
                mapped_count += 1
            else:
                fallback_values.append(value)

        # ideálny prípad: všetko mapovateľné podľa mena
        if mapped_count == len(reals):
            return [mapped.get(r.lower(), "") for r in reals]

        # ak nič nemá var v odpovedi -> poradie
        if len(fallback_values) == len(reals):
            return fallback_values

        # mixed -> best effort
        out: list[str] = []
        fb_iter = iter(fallback_values)
        for r in reals:
            out.append(mapped.get(r.lower(), next(fb_iter, "")))
        return out

    async def async_set(self, var_name: str, value: str) -> None:
        real = self.resolve_var(var_name)
        await self._send(f"SET:{real},{value}")

    async def async_subscribe(self) -> None:
        if self._subscribed:
            return
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
                if not line.startswith("DIFF:"):
                    continue

                body = line[5:]
                if "," not in body:
                    continue

                var, value = body.split(",", 1)
                var_lower = var.lower()
                value_stripped = value.strip()

                # PLC restart hook
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

            except Exception:
                await asyncio.sleep(delay)
                delay = min(int(delay * 1.6), RECONNECT_MAX_DELAY)
                self._connected = False
                self._subscribed = False

    async def _reload_variables(self) -> None:
        try:
            await self._send("LIST:")
            await self._read_list()
        except Exception:
            pass