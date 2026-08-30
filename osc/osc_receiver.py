"""OSC server: receives messages and hands them to a callback.

The counterpart to OSCSender. Runs the pythonosc server on its own thread so the
MIDI listener keeps the main one.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer


class OSCReceiver:
    """Listen on a UDP port and call ``on_message(address, args)`` for everything.

    Also reports the sender's address via ``on_source``, so a peer that receives
    on an ephemeral port can be replied to without being configured.
    """

    def __init__(self, ip: str, port: int, on_message: Callable[[str, tuple], None],
                 on_source: Optional[Callable[[str, int], None]] = None) -> None:
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(lambda address, *args: on_message(address, args))

        class Server(ThreadingOSCUDPServer):
            def verify_request(self, request, client_address):
                if on_source is not None:
                    on_source(client_address[0], client_address[1])
                return True

            def handle_error(self, request, client_address):
                # REAPER emits the occasional packet pythonosc cannot parse
                # ("OSC addresses cannot be empty"). Log it and carry on rather
                # than letting the handler thread die with a traceback.
                logging.debug(f"ignoring unparseable OSC packet from {client_address}",
                              exc_info=True)

        self.server = Server((ip, port), dispatcher)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        host, port = self.server.server_address[:2]
        logging.info(f"Listening for OSC on {host}:{port}")
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
