"""OSC server: receives messages and hands them to a callback.

The counterpart to OSCSender. Runs the pythonosc server on its own thread so the
MIDI listener keeps the main one.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer


class OSCReceiver:
    """Listen on a UDP port and call ``on_message(address, args)`` for everything."""

    def __init__(self, ip: str, port: int, on_message: Callable[[str, tuple], None]) -> None:
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(lambda address, *args: on_message(address, args))
        self.server = ThreadingOSCUDPServer((ip, port), dispatcher)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        host, port = self.server.server_address[:2]
        logging.info(f"Listening for OSC on {host}:{port}")
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
