import logging

from pythonosc.udp_client import SimpleUDPClient


class OSCSender:
    """UDP OSC client whose destination can change at runtime.

    REAPER's "Device IP/Port" mode receives on an ephemeral port that differs
    every launch, so the destination is learned from the packets it sends us
    rather than configured. See retarget().
    """

    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.client = SimpleUDPClient(ip, port)

    def retarget(self, ip: str, port: int) -> None:
        if (ip, port) == (self.ip, self.port):
            return
        logging.info(f"OSC destination now {ip}:{port}")
        self.ip, self.port = ip, port
        self.client = SimpleUDPClient(ip, port)

    def send(self, address: str, *args):
        if not self.port:
            return  # destination not known yet; see retarget()
        self.client.send_message(address, args)
