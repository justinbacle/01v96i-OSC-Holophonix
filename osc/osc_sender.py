from pythonosc.udp_client import SimpleUDPClient


class OSCSender:
    def __init__(self, ip: str, port: int):
        self.client = SimpleUDPClient(ip, port)

    def send(self, address: str, *args):
        self.client.send_message(address, args)
