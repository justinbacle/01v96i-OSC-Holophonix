import threading
import mido
from typing import Callable, List


class MidiSysexListener:
    def __init__(self, port_name: str):
        self.port_name = port_name
        self.callbacks: List[Callable[[bytes], None]] = []
        self._stop_flag = threading.Event()

    def add_callback(self, callback: Callable[[bytes], None]):
        self.callbacks.append(callback)

    def stop(self):
        self._stop_flag.set()

    def listen(self):
        with mido.open_input(self.port_name) as inport:  # pyright: ignore[reportAttributeAccessIssue]
            for msg in inport:
                if self._stop_flag.is_set():
                    break
                if msg.type == "sysex":
                    for cb in self.callbacks:
                        cb(msg.data)
