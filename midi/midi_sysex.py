import mido
from typing import Callable, List, Optional


class MidiSysexListener:
    def __init__(self, port_name: str, mask_filters: Optional[List[bytes]] = None):
        self.port_name = port_name
        self.mask_filters = mask_filters or []
        self.callbacks: List[Callable[[bytes], None]] = []

    def add_callback(self, callback: Callable[[bytes], None]):
        self.callbacks.append(callback)

    def _matches_mask(self, sysex: bytes) -> bool:
        if not self.mask_filters:
            return True
        return any(sysex.startswith(mask) for mask in self.mask_filters)

    def listen(self):
        with mido.open_input(self.port_name) as inport:  # pyright: ignore[reportAttributeAccessIssue]
            for msg in inport:
                if msg.type == "sysex":
                    data = msg.data
                    if self._matches_mask(data):
                        for cb in self.callbacks:
                            cb(data)
