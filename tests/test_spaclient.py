"""Regression coverage for Spa Client using only loopback TCP and Python's stdlib.

Run with a Python 3.11+ interpreter. No Home Assistant instance or spa is needed.
Optional SPACLIENT_SOURCE points to a copy of spaclient.py under test.
"""
import asyncio
import importlib.util
import logging
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


def load_spaclient():
    source = Path(os.environ.get("SPACLIENT_SOURCE", Path(__file__).resolve().parents[1] / "custom_components/spaclient/spaclient.py"))
    for name in ("homeassistant", "homeassistant.util", "homeassistant.util.dt", "homeassistant.const", "homeassistant.util.unit_conversion", "spa_test_package", "spa_test_package.const"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["homeassistant"].util = sys.modules["homeassistant.util"]
    sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]
    sys.modules["homeassistant.const"].UnitOfTemperature = types.SimpleNamespace(CELSIUS="C", FAHRENHEIT="F")
    sys.modules["homeassistant.util.unit_conversion"].TemperatureConverter = type("TemperatureConverter", (), {})
    sys.modules["spa_test_package.const"]._LOGGER = logging.getLogger("spaclient_transport_test")
    spec = importlib.util.spec_from_file_location("spa_test_package.spaclient", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


spa_module = load_spaclient()


def frame(message_type, payload):
    """Encode a peer frame; checksum polynomial is part of the Balboa protocol."""
    content = bytes([5 + len(payload)]) + message_type + payload
    crc = 0xB5
    for value in content:
        for bit in range(7, -1, -1):
            high = crc & 0x80
            crc = ((crc << 1) & 0xFF) | ((value >> bit) & 1)
            if high:
                crc ^= 7
    for _ in range(8):
        crc = ((crc << 1) ^ (7 if crc & 0x80 else 0)) & 0xFF
    return b"~" + content + bytes([crc ^ 2]) + b"~"


def status_frame():
    payload = bytearray(24)
    payload[2], payload[3], payload[4] = 76, 12, 34
    payload[9], payload[20] = 1, 78
    return frame(b"\xff\xaf\x13", payload)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.peers = asyncio.Queue()
        self.peer_writers = []
        self.peer_tasks = set()
        self.tasks = []
        self.spa = spa_module.spaclient("127.0.0.1")

        async def accepted(reader, writer):
            task = asyncio.current_task()
            self.peer_tasks.add(task)
            self.peer_writers.append(writer)
            await self.peers.put((reader, writer))
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()
                self.peer_tasks.discard(task)

        self.server = await asyncio.start_server(accepted, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        real_open_connection = asyncio.open_connection

        async def loopback_connection(host, requested_port, **kwargs):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(requested_port, 4257)
            return await real_open_connection(host, port, **kwargs)

        self.patches = [
            patch.object(spa_module.asyncio, "open_connection", loopback_connection),
            patch.object(spa_module, "IO_TIMEOUT", 0.12),
            patch.object(spa_module, "REQUEST_TIMEOUT", 0.25),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.spa.close()
        self.server.close()
        for writer in self.peer_writers:
            writer.close()
        for task in tuple(self.peer_tasks):
            task.cancel()
        await asyncio.gather(*self.peer_tasks, return_exceptions=True)
        await self.server.wait_closed()
        for item in reversed(self.patches):
            item.stop()

    def task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task

    async def connect(self):
        await self.spa.get_socket()
        return await asyncio.wait_for(self.peers.get(), 1)

    async def test_fragmented_frame_waits_for_complete_payload(self):
        _, writer = await self.connect()
        read_task = self.task(self.spa.read_msg())
        packet = status_frame()
        # Split the marker, length, type and body separately; TCP is a byte stream.
        cuts = [1, 2, 4, 12, len(packet)]
        begin = 0
        for end in cuts:
            writer.write(packet[begin:end])
            await writer.drain()
            await asyncio.sleep(0.005)
            if end < len(packet):
                self.assertFalse(read_task.done(), "Partial frame was parsed prematurely")
            begin = end
        await asyncio.wait_for(read_task, 1)
        self.assertTrue(self.spa.socket_is_connected)
        self.assertEqual(self.spa.current_temp, 76)
        self.assertEqual(self.spa.set_temp, 78)
        self.assertEqual(self.spa.minute, 34)

    async def test_coalesced_frames_remain_separate(self):
        _, writer = await self.connect()
        writer.write(status_frame() + frame(b"\x0a\xbf\x2e", b"\x0a\x00\x01\x80\x00\x00"))
        await writer.drain()
        await self.spa.read_msg()
        await self.spa.read_msg()
        self.assertEqual(self.spa.current_temp, 76)
        self.assertTrue(self.spa.configuration_loaded)
        self.assertEqual(self.spa.cfg_pump_array[:2], [2, 2])
        self.assertEqual(self.spa.cfg_light_array, [1, 0])
        self.assertEqual(self.spa.cfg_circ_pump_array, [1])

    async def test_silent_peer_times_out_without_blocking_event_loop(self):
        ticks = []

        async def heartbeat():
            while True:
                ticks.append(asyncio.get_running_loop().time())
                await asyncio.sleep(0.005)

        heartbeat_task = self.task(heartbeat())
        start = asyncio.get_running_loop().time()
        connected = await asyncio.wait_for(self.spa.validate_connection(), 0.8)
        elapsed = asyncio.get_running_loop().time() - start
        heartbeat_task.cancel()
        self.assertFalse(connected)
        self.assertLess(elapsed, 0.8)
        self.assertGreaterEqual(len(ticks), 8, "A silent spa starved unrelated HA tasks")
        self.assertIsNone(self.spa.socket_s)

    async def test_validation_deadline_survives_continuous_nonstatus_frames(self):
        async def noise():
            _, writer = await self.peers.get()
            packet = frame(b"\x0a\xbf\x2b", b"\x01")
            while True:
                writer.write(packet)
                await writer.drain()
                await asyncio.sleep(0.01)

        self.task(noise())
        connected = await asyncio.wait_for(self.spa.validate_connection(), 0.8)
        self.assertFalse(connected)
        self.assertIsNone(self.spa.socket_s)

    async def test_request_deadline_survives_unrelated_status_frames(self):
        _, writer = await self.connect()

        async def unrelated_frames():
            while True:
                writer.write(status_frame())
                await writer.drain()
                await asyncio.sleep(0.01)

        self.task(unrelated_frames())
        with self.assertRaises((TimeoutError, ConnectionError)):
            await asyncio.wait_for(self.spa.send_information_request(), 0.8)
        self.assertFalse(self.spa.information_loaded)

    async def test_eof_disconnects_and_identical_status_reconnects(self):
        _, writer = await self.connect()
        packet = status_frame()
        writer.write(packet)
        await writer.drain()
        await self.spa.read_msg()
        self.assertTrue(self.spa.socket_is_connected)
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(self.spa.read_msg(), 0.5)
        self.assertFalse(self.spa.socket_is_connected)
        self.assertIsNone(self.spa.socket_s)
        _, replacement = await self.connect()
        replacement.write(packet)
        await replacement.drain()
        await self.spa.read_msg()
        self.assertTrue(self.spa.socket_is_connected)

    async def test_eof_in_partial_frame_closes_transport(self):
        _, writer = await self.connect()
        writer.write(status_frame()[:8])
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(self.spa.read_msg(), 0.5)
        self.assertFalse(self.spa.socket_is_connected)
        self.assertIsNone(self.spa.socket_s)

    async def test_old_reader_failure_does_not_close_replacement_connection(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                await self.connect()
                started = asyncio.Event()
                release = asyncio.Event()

                class DelayedEOF:
                    async def readexactly(self, size):
                        started.set()
                        await release.wait()
                        raise asyncio.IncompleteReadError(b"", size)

                self.spa._reader = DelayedEOF()
                old_read = self.task(self.spa.read_msg())
                await started.wait()
                self.spa._disconnect()
                _, replacement_peer = await self.connect()
                replacement_writer = self.spa.socket_s
                if cancelled:
                    old_read.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await old_read
                else:
                    release.set()
                    await old_read
                self.assertIs(self.spa.socket_s, replacement_writer)
                self.assertFalse(replacement_writer.is_closing())
                replacement_peer.write(status_frame())
                await replacement_peer.drain()
                await self.spa.read_msg()
                self.assertTrue(self.spa.socket_is_connected)
                await self.spa.close()

    async def test_command_wire_bytes_are_unchanged(self):
        reader, _ = await self.connect()
        self.spa.send_toggle_message(0x04)
        self.spa.send_message(b"\x0a\xbf\x20", b"\x4e")
        expected = bytes.fromhex("7e070abf110400857e7e060abf204eff7e")
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(expected)), 0.5), expected)

    async def test_cancelling_validation_closes_connection(self):
        validation = self.task(self.spa.validate_connection())
        reader, _ = await asyncio.wait_for(self.peers.get(), 0.5)
        await asyncio.sleep(0.01)
        validation.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await validation
        self.assertIsNone(self.spa.socket_s)
        self.assertEqual(await asyncio.wait_for(reader.read(), 0.5), b"")

    async def test_close_unblocks_pending_reader_and_is_idempotent(self):
        reader, _ = await self.connect()
        pending = self.task(self.spa.read_msg())
        await asyncio.sleep(0.01)
        await self.spa.close()
        await asyncio.wait_for(pending, 0.5)
        await self.spa.close()
        self.assertIsNone(self.spa.socket_s)
        self.assertFalse(self.spa.socket_is_connected)
        self.assertEqual(await asyncio.wait_for(reader.read(), 0.5), b"")



def load_functions(path, names, namespace):
    """Run actual lifecycle functions with narrow HA stand-ins, without HA imports."""
    import ast

    tree = ast.parse(path.read_text(), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("A lifecycle function under test was removed or renamed")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class ConfigEntryNotReady(Exception):
    pass


class CannotConnect(Exception):
    pass


class AlreadyConfigured(Exception):
    pass


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import AsyncMock, Mock

        self.created_tasks = []
        self.stop_callbacks = []
        self.unload_callbacks = []
        self.spa = spa_module.spaclient("127.0.0.1")
        self.spa.socket_is_connected = True
        self.spa.validate_connection = AsyncMock(return_value=True)
        self.spa.close = AsyncMock(wraps=self.spa.close)
        self.spa.set_current_time = AsyncMock()
        self.spa.print_variables = Mock()
        for name in (
            "send_additional_information_request", "send_configuration_request",
            "send_fault_log_request", "send_filter_cycles_request",
            "send_gfci_test_request", "send_information_request",
            "send_module_identification_request", "send_preferences_request",
        ):
            setattr(self.spa, name, AsyncMock())

        async def background():
            await asyncio.Future()

        self.spa.keep_alive_call = background
        self.spa.read_all_msg = background

        def create_background(coroutine, name):
            task = asyncio.create_task(coroutine, name=name)
            self.created_tasks.append(task)
            return task

        def stop_listener(event, callback):
            self.assertEqual(event, "homeassistant_stop")
            self.stop_callbacks.append(callback)
            return Mock()

        self.entry = types.SimpleNamespace(
            entry_id="test_entry", data={"host": "127.0.0.1"},
            options={"sync_time": True}, add_update_listener=Mock(return_value=Mock()),
            async_on_unload=self.unload_callbacks.append,
        )
        self.hass = types.SimpleNamespace(
            data={"spaclient": {}}, async_create_background_task=create_background,
            config_entries=types.SimpleNamespace(
                async_forward_entry_setups=AsyncMock(),
                async_unload_platforms=AsyncMock(return_value=True),
                async_entries=Mock(return_value=[]),
            ),
            bus=types.SimpleNamespace(async_listen_once=stop_listener),
        )
        namespace = {
            "asyncio": asyncio, "spaclient": lambda host: self.spa,
            "SPA": "spa", "DOMAIN": "spaclient", "CONF_HOST": "host",
            "CONF_SYNC_TIME": "sync_time", "SPACLIENT_COMPONENTS": ["climate"],
            "EVENT_HOMEASSISTANT_STOP": "homeassistant_stop",
            "ConfigEntryNotReady": ConfigEntryNotReady,
            "CannotConnect": CannotConnect, "AlreadyConfigured": AlreadyConfigured,
            "_LOGGER": logging.getLogger("spaclient_lifecycle_test"),
        }
        source_dir = Path(spa_module.__file__).parent
        self.functions = load_functions(
            source_dir / "__init__.py",
            {"async_setup_entry", "async_unload_entry", "_async_close", "update_listener"},
            namespace,
        )
        load_functions(source_dir / "config_flow.py", {"validate_input"}, namespace)

    async def asyncTearDown(self):
        for task in self.created_tasks:
            task.cancel()
        await asyncio.gather(*self.created_tasks, return_exceptions=True)
        await self.spa.close()

    async def setup(self):
        result = await self.functions["async_setup_entry"](self.hass, self.entry)
        await asyncio.sleep(0)
        return result

    def assert_tasks_stopped(self):
        self.assertTrue(all(task.done() for task in self.created_tasks))
        self.assertTrue(all(task.cancelled() for task in self.created_tasks))

    async def test_failed_connection_cleans_up_entry(self):
        self.spa.validate_connection.return_value = False
        with self.assertRaises(ConfigEntryNotReady):
            await self.setup()
        self.assertEqual(self.hass.data["spaclient"], {})
        self.assertEqual(self.created_tasks, [])
        self.assertEqual(self.unload_callbacks, [])
        self.spa.close.assert_awaited_once()

    async def test_setup_timeout_cleans_up_entry(self):
        self.spa.send_information_request.side_effect = TimeoutError("No reply")
        with self.assertRaises(ConfigEntryNotReady):
            await self.setup()
        self.assertEqual(self.hass.data["spaclient"], {})
        self.assertEqual(self.created_tasks, [])
        self.spa.close.assert_awaited_once()

    async def test_failed_platform_setup_cancels_created_tasks(self):
        self.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("Platform failed")
        with self.assertRaisesRegex(RuntimeError, "Platform failed"):
            await self.setup()
        self.assertEqual(len(self.created_tasks), 3)
        self.assert_tasks_stopped()
        self.assertEqual(self.hass.data["spaclient"], {})
        self.assertEqual(self.unload_callbacks, [])
        self.spa.close.assert_awaited_once()

    async def test_cancelled_setup_closes_connection(self):
        started = asyncio.Event()

        async def wait_for_status():
            started.set()
            await asyncio.Future()

        self.spa.validate_connection.side_effect = wait_for_status
        setup = asyncio.create_task(self.setup())
        await started.wait()
        setup.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await setup
        self.assertEqual(self.hass.data["spaclient"], {})
        self.spa.close.assert_awaited_once()

    async def test_unload_cancels_reader_keepalive_and_sync_timer(self):
        self.assertTrue(await self.setup())
        self.assertEqual(len(self.created_tasks), 3)
        self.assertFalse(any(task.done() for task in self.created_tasks))
        # Uses the real spa object's connection getter to catch wrong method names.
        self.spa.set_current_time.assert_awaited_once()
        self.assertEqual(len(self.unload_callbacks), 2)
        self.assertTrue(await self.functions["async_unload_entry"](self.hass, self.entry))
        self.assert_tasks_stopped()
        self.assertEqual(self.hass.data["spaclient"], {})
        self.spa.close.assert_awaited_once()

    async def test_failed_unload_preserves_connection_and_background_tasks(self):
        await self.setup()
        self.hass.config_entries.async_unload_platforms.return_value = False
        self.assertFalse(await self.functions["async_unload_entry"](self.hass, self.entry))
        self.assertIn(self.entry.entry_id, self.hass.data["spaclient"])
        self.assertFalse(any(task.done() for task in self.created_tasks))
        self.spa.close.assert_not_awaited()
        self.assertTrue(self.spa.socket_is_connected)

    async def test_options_replace_sync_timer_and_disabling_cancels_it(self):
        await self.setup()
        data = self.hass.data["spaclient"][self.entry.entry_id]
        first = data["sync_time_task"]
        await self.functions["update_listener"](self.hass, self.entry)
        await asyncio.sleep(0)
        second = data["sync_time_task"]
        self.assertIsNot(first, second)
        self.assertTrue(first.cancelled())
        self.assertFalse(second.done())
        self.assertEqual(self.spa.set_current_time.await_count, 2)
        self.entry.options["sync_time"] = False
        await self.functions["update_listener"](self.hass, self.entry)
        self.assertTrue(second.cancelled())
        self.assertIsNone(data["sync_time_task"])
        self.assertEqual(sum(not task.done() for task in self.created_tasks), 2)

    async def test_home_assistant_stop_cancels_all_background_tasks(self):
        await self.setup()
        self.assertEqual(len(self.stop_callbacks), 1)
        await self.stop_callbacks[0](None)
        self.assert_tasks_stopped()
        self.spa.close.assert_awaited_once()

    async def test_config_flow_always_closes_validation_connection(self):
        for result in (True, False, TimeoutError("No reply"), asyncio.CancelledError()):
            with self.subTest(result=type(result).__name__ + str(result)):
                self.spa.close.reset_mock()
                self.spa.validate_connection.reset_mock()
                self.spa.validate_connection.side_effect = result if isinstance(result, BaseException) else None
                self.spa.validate_connection.return_value = result
                if result is True:
                    await self.functions["validate_input"](self.hass, self.entry.data)
                else:
                    error = CannotConnect if result is False else type(result)
                    with self.assertRaises(error):
                        await self.functions["validate_input"](self.hass, self.entry.data)
                self.spa.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
