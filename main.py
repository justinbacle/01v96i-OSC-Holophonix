from typing import List, Callable
import logging
import mido
import math
from osc.osc_sender import OSCSender

# ----------------------------------- Masks ---------------------------------- #


class SysexMasks:
    """Class to group all sysex masks and mask matching functions"""

    @staticmethod
    def match_sysex(data: List[int], mask: List) -> bool:
        """Generic mask matching function"""
        if len(data) != len(mask):
            return False
        for idx, (d, m) in enumerate(zip(data, mask)):
            if m in ("channel", "x", "v", "pan", "mute", "Y", "X"):
                continue
            if m is None:
                continue
            if d != m:
                return False
        return True


    # --- Ignore Specific Message ---
    IGNORE_MESSAGE = (67, 16, 62, 26, 127)

    @staticmethod
    def ignore_specific_message_mask(data: List[int]) -> bool:
        return tuple(data) == SysexMasks.IGNORE_MESSAGE

    @staticmethod
    def ignore_specific_message_handler(data: List[int], handler):
        pass

    # --- Master Fader ---
    MASTER_FADER = [67, 16, 62, 127, 1, 79, 0, "L/R", 0, 0, "u", "v"]

    @staticmethod
    def master_fader_mask(data: List[int]) -> bool:
        if not SysexMasks.match_sysex(data, SysexMasks.MASTER_FADER):
            return False
        x = data[10]
        v = data[11]
        channel = data[7]
        return 0 <= channel <= 15 and 0 <= x <= 7 and 0 <= v <= 127

    @staticmethod
    def master_fader_handler(data: List[int], handler):
        x = data[10]
        v = data[11]
        volume = (x * 128 + v) / 1023.0
        handler.master_volume(volume)

    # --- Channel Fader ---
    CH_FADER = [67, 16, 62, 127, 1, 28, 0, "channel", 0, 0, "u", "v"]

    @staticmethod
    def channel_fader_mask(data: List[int]) -> bool:
        if not SysexMasks.match_sysex(data, SysexMasks.CH_FADER):
            return False
        channel = data[7]
        x = data[10]
        v = data[11]
        return 0 <= channel <= 15 and 0 <= x <= 7 and 0 <= v <= 127

    @staticmethod
    def channel_fader_handler(data: List[int], handler):
        channel = data[7]
        x = data[10]
        v = data[11]
        volume = (x * 128 + v) / 1023.0
        handler.volume(channel, volume)

    # --- Pan ---
    PAN = [67, 16, 62, 127, 1, 27, 0, "channel", None, None, None, "pan"]

    @staticmethod
    def pan_mask(data: List[int]) -> bool:
        if len(data) != 12:
            return False
        if not (
            data[0] == 67
            and data[1] == 16
            and data[2] == 62
            and data[3] == 127
            and data[4] == 1
            and data[5] == 27
            and data[6] == 0
        ):
            return False
        channel = data[7]
        pan = data[11]
        return 0 <= channel <= 15 and 0 <= pan <= 127

    @staticmethod
    def pan_handler(data: List[int], handler):
        channel = data[7]
        if data[8] == 0:  # Right Pan
            pan = data[11] / 63
        elif data[8] == 127:  # Left Pan
            pan = -(1 - data[11] / 63) - 1
        else:
            pan = 0
            logging.warning(f"Unexpected pan value: {data[8]}")
        handler.pan(channel, pan)

    # --- Y ---
    Y = [67, 16, 62, 127, 1, 37, 6, "channel", None, None, None, "Y"]

    @staticmethod
    def y_mask(data: List[int]) -> bool:
        if len(data) != 12:
            return False
        if not (
            data[0] == 67
            and data[1] == 16
            and data[2] == 62
            and data[3] == 127
            and data[4] == 1
            and data[5] == 37
            and data[6] == 6
        ):
            return False
        channel = data[7]
        y = data[11]
        return 0 <= channel <= 15 and 0 <= y <= 127

    @staticmethod
    def y_handler(data: List[int], handler):
        channel = data[7]
        if data[8] == 0:  # Positive Y
            y = data[11] / 63
        elif data[8] == 127:  # Negative Y
            y = -(1 - data[11] / 63) - 1
        else:
            y = 0
            logging.warning(f"Unexpected y value: {data[8]}")
        handler.y(channel, y)

    # --- X ---
    X = [67, 16, 62, 127, 1, 37, 5, "channel", None, None, None, "X"]

    @staticmethod
    def x_mask(data: List[int]) -> bool:
        if len(data) != 12:
            return False
        if not (
            data[0] == 67
            and data[1] == 16
            and data[2] == 62
            and data[3] == 127
            and data[4] == 1
            and data[5] == 37
            and data[6] == 5
        ):
            return False
        channel = data[7]
        x = data[11]
        return 0 <= channel <= 15 and 0 <= x <= 127

    @staticmethod
    def x_handler(data: List[int], handler):
        channel = data[7]
        if data[8] == 0:  # Positive X
            x = data[11] / 63
        elif data[8] == 127:  # Negative X
            x = -(1 - data[11] / 63) - 1
        else:
            x = 0
            logging.warning(f"Unexpected x value: {data[8]}")
        handler.x(channel, x)

    # --- Master Mute ---
    MASTER_MUTE_1 = [67, 16, 62, 127, 1, 77, 0, None, 0, 0, 0, None]

    @staticmethod
    def master_mute_mask_1(data: List[int]) -> bool:
        if len(data) != len(SysexMasks.MASTER_MUTE_1):
            return False
        for idx, (d, m) in enumerate(zip(data, SysexMasks.MASTER_MUTE_1)):
            if m is None:
                continue
            if d != m:
                return False
        return True

    @staticmethod
    def master_mute_handler(data: List[int], handler):
        mute_val = data[11]
        osc_mute = 0 if mute_val == 1 else 1
        handler.master_mute(osc_mute)

    MASTER_MUTE_2 = [67, 16, 62, 26, 4, 94, 0, None, 0, 0, 0, None]

    @staticmethod
    def master_mute_mask_2(data: List[int]) -> bool:
        if len(data) != len(SysexMasks.MASTER_MUTE_2):
            return False
        for idx, (d, m) in enumerate(zip(data, SysexMasks.MASTER_MUTE_2)):
            if m is None:
                continue
            if d != m:
                return False
        return True

    # --- Channel Mute ---
    @staticmethod
    def match_mute_sysex(data: List[int], mask: List) -> bool:
        if len(data) != len(mask):
            return False
        for d, m in zip(data, mask):
            if isinstance(m, str):
                continue
            if d != m:
                return False
        return True

    MUTE_1 = [67, 16, 62, 127, 1, 26, 0, "channel", 0, 0, 0, "mute"]

    @staticmethod
    def mute_mask_1(data: List[int]) -> bool:
        if not SysexMasks.match_mute_sysex(data, SysexMasks.MUTE_1):
            return False
        channel = data[7]
        mute = data[11]
        return 0 <= channel <= 15 and mute in (0, 1)

    @staticmethod
    def mute_handler_1(data: List[int], handler):
        channel = data[7]
        mute = data[11]
        osc_mute = 0 if mute == 1 else 1
        handler.mute(channel, osc_mute)

    MUTE_2 = [67, 16, 62, 26, 4, 90, 0, "channel", 0, 0, 0, "mute"]

    @staticmethod
    def mute_mask_2(data: List[int]) -> bool:
        if not SysexMasks.match_mute_sysex(data, SysexMasks.MUTE_2):
            return False
        channel = data[7]
        mute = data[11]
        return 0 <= channel <= 15 and mute in (0, 1)

    @staticmethod
    def mute_handler_2(data: List[int], handler):
        channel = data[7]
        mute = data[11]
        osc_mute = 0 if mute == 1 else 1
        handler.mute(channel, osc_mute)

    # EQ
    # Band 1                                 V => 82 : Master L/R, 32 : Chan 1-16
    #                                                V : if Master : 0/1 : L/R. If Channel : channel number
    # --- EQ Band 1 Gain ---
    EQ_BAND_1_GAIN = [67, 16, 62, 127, 1, "Sel", 3, "Ch", None, None, "u", "v"]

    @staticmethod
    def eq_band_1_gain_mask(data: List[int]) -> bool:
        if len(data) != len(SysexMasks.EQ_BAND_1_GAIN):
            return False
        for d, m in zip(data, SysexMasks.EQ_BAND_1_GAIN):
            if isinstance(m, str):
                continue
            if m is None:
                continue
            if d != m:
                return False
        channel = data[7]
        u = data[10]
        v = data[11]
        selector = data[5]
        return 0 <= channel <= 15 and 0 <= u <= 127 and 0 <= v <= 127 and selector in (82, 32)

    # EQ Bands work differently in 01v96i than Holophonix
    #   01v96i  >   Holophonix
    #   Band 1  >   Band 1 or Band 2 depending on filter type (shelf / bell)
    #   Band 2  >   Band 3
    #   Band 3  >   Band 4
    #   Band 4  >   Band 5 or Band 6 depending on filter type (shelf / bell)

    @staticmethod
    def eq_band_1_gain_handler(data: List[int], handler):
        if data[10] < 64:
            value = data[10] * 127 + data[11]
        else:
            value = -((127 - data[10]) * 127 + (127 - data[11]))
        value = value / 178 * 18
        if data[5] == 82:  # Master
            handler.eq(selector='master', band=1, value=value)
        else:
            channel = data[7]
            handler.eq(selector='channel', channel=channel, band=1, value=value)

# --------------------------------- Handlers --------------------------------- #


class OSC_Handler:
    def __init__(self, osc_sender: OSCSender):
        self.osc_sender = osc_sender

        # Surround mode handling
        self.XY_SCALE = 10
        # States to save
        self._x = 0.0
        self._y = 0.0

    def pan(self, channel: int, value: float):
        azim = value * 45  # -45.0 to 45.0
        osc_address = f"/track/{channel+1}/azim"
        self.osc_sender.send(osc_address, azim)
        print(f"OSC sent: {osc_address} {azim:.1f}")

    def x(self, channel: int, value: float):
        self._x = value * self.XY_SCALE
        self._xy(channel)

    def y(self, channel: int, value: float):
        self._y = value * self.XY_SCALE
        self._xy(channel)

    def _xy(self, channel: int):
        # Calculate azimuth and distance using trigonometry
        azim = math.degrees(math.atan2(self._x, self._y))  # <-- swapped arguments
        dist = (self._x**2 + self._y**2) ** 0.5  # Euclidean distance, normalized
        osc_address_azim = f"/track/{channel+1}/azim"
        osc_address_dist = f"/track/{channel+1}/dist"
        self.osc_sender.send(osc_address_azim, azim)
        self.osc_sender.send(osc_address_dist, dist)
        print(f"OSC sent: {osc_address_azim} {azim:.1f}")
        print(f"OSC sent: {osc_address_dist} {dist:.3f}")

    def volume(self, channel: int, value: float):
        db_value = (value * 72) - 60
        osc_address = f"/track/{channel+1}/gain"
        self.osc_sender.send(osc_address, db_value)
        print(f"OSC sent: {osc_address} {db_value:.1f}dB")

    def master_volume(self, value: float):
        db_value = (value * 72) - 60
        osc_address = "/master/gain"
        self.osc_sender.send(osc_address, db_value)
        print(f"OSC sent: {osc_address} {db_value:.1f}dB")

    def mute(self, channel: int, value: int):
        osc_address = f"/track/{channel+1}/mute"
        self.osc_sender.send(osc_address, value)
        print(f"OSC sent: {osc_address} {value}")

    def master_mute(self, value: int):
        osc_address = "/master/mute"
        self.osc_sender.send(osc_address, value)
        print(f"OSC sent: {osc_address} {value}")

    def eq(self, selector: str, band: int, value: float, channel: int | None = None):
        if selector == 'master':
            osc_address = f"/master/equalizer/filter/{band}/gain"
        else:
            if channel is None:
                logging.error("Channel must be provided for channel EQ")
            else:
                osc_address = f"/track/{channel+1}/equalizer/filter/{band}/gain"
        self.osc_sender.send(osc_address, value)
        print(f"OSC sent: {osc_address} {value}")


def ignore_specific_message_handler(data: List[int], handler: OSC_Handler):
    pass


def fader_volume_handler(data: List[int], handler: OSC_Handler):
    channel = data[7]
    x = data[10]
    v = data[11]
    volume = (x * 128 + v) / 1023.0
    handler.volume(channel, volume)


def master_fader_handler(data: List[int], handler: OSC_Handler):
    x = data[10]
    v = data[11]
    volume = (x * 128 + v) / 1023.0
    handler.master_volume(volume)


def pan_handler(data: List[int], handler: OSC_Handler):
    channel = data[7]
    if data[8] == 0:  # Right Pan
        pan = data[11] / 63
    elif data[8] == 127:  # Left Pan
        pan = -(1 - data[11] / 63) - 1
    else:
        pan = 0
        logging.warning(f"Unexpected pan value: {data[8]}")
    handler.pan(channel, pan)


def y_handler(data: List[int], handler: OSC_Handler):
    channel = data[7]
    if data[8] == 0:  # Positive Y
        y = data[11] / 63
    elif data[8] == 127:  # Negative Y
        y = -(1 - data[11] / 63) - 1
    else:
        y = 0
        logging.warning(f"Unexpected pan value: {data[8]}")
    handler.y(channel, y)


def x_handler(data: List[int], handler: OSC_Handler):
    channel = data[7]
    if data[8] == 0:  # Positive X
        x = data[11] / 63
    elif data[8] == 127:  # Negative X
        x = -(1 - data[11] / 63) - 1
    else:
        x = 0
        logging.warning(f"Unexpected pan value: {data[8]}")
    handler.x(channel, x)


def master_mute_handler(data: List[int], handler: OSC_Handler):
    mute_val = data[11]
    osc_mute = 0 if mute_val == 1 else 1
    handler.master_mute(osc_mute)


def mute_handler_1(data: List[int], handler: OSC_Handler):
    channel = data[7]
    mute = data[11]
    osc_mute = 0 if mute == 1 else 1
    handler.mute(channel, osc_mute)


def mute_handler_2(data: List[int], handler: OSC_Handler):
    channel = data[7]
    mute = data[11]
    osc_mute = 0 if mute == 1 else 1
    handler.mute(channel, osc_mute)


class SysexDispatcher:

    def __init__(self, handler: OSC_Handler):
        self.handlers: List[
            tuple[Callable[[List[int]], bool], Callable[[List[int], OSC_Handler], None]]
        ] = []
        self.handler = handler

    def add_handler(
        self,
        mask_fn: Callable[[List[int]], bool],
        handler_fn: Callable[[List[int], OSC_Handler], None],
    ):
        self.handlers.append((mask_fn, handler_fn))

    def dispatch(self, data: List[int]):
        for mask_fn, handler_fn in self.handlers:
            if mask_fn(data):
                handler_fn(data, self.handler)
                return
        print(f"Unhandled Sysex: {data}")


def print_sysex(data, dispatcher):
    dispatcher.dispatch(list(data))


def select_midi_port():
    ports = mido.get_input_names()  # pyright: ignore[reportAttributeAccessIssue]
    if not ports:
        print("No MIDI input ports found.")
        return None
    print("Available MIDI input ports:")
    for idx, port in enumerate(ports):
        print(f"  [{idx}] {port}")
    while True:
        try:
            selection = int(input("Select MIDI port number: "))
            if 0 <= selection < len(ports):
                return ports[selection]
        except (ValueError, IndexError):
            pass
        print("Invalid selection. Please try again.")


def main():
    import threading

    OSC_IP = "192.168.1.104"
    OSC_PORT = 4003
    osc_sender = OSCSender(OSC_IP, OSC_PORT)
    handler = OSC_Handler(osc_sender)
    dispatcher = SysexDispatcher(handler)
    dispatcher.add_handler(
        SysexMasks.ignore_specific_message_mask, SysexMasks.ignore_specific_message_handler
    )
    dispatcher.add_handler(SysexMasks.master_fader_mask, SysexMasks.master_fader_handler)
    dispatcher.add_handler(SysexMasks.master_mute_mask_1, SysexMasks.master_mute_handler)
    dispatcher.add_handler(SysexMasks.master_mute_mask_2, SysexMasks.master_mute_handler)
    dispatcher.add_handler(SysexMasks.channel_fader_mask, SysexMasks.channel_fader_handler)
    dispatcher.add_handler(SysexMasks.mute_mask_1, SysexMasks.mute_handler_1)
    dispatcher.add_handler(SysexMasks.mute_mask_2, SysexMasks.mute_handler_2)
    dispatcher.add_handler(SysexMasks.pan_mask, SysexMasks.pan_handler)
    dispatcher.add_handler(SysexMasks.y_mask, SysexMasks.y_handler)
    dispatcher.add_handler(SysexMasks.x_mask, SysexMasks.x_handler)
    dispatcher.add_handler(SysexMasks.eq_band_1_gain_mask, SysexMasks.eq_band_1_gain_handler)

    midi_port = select_midi_port()
    if not midi_port:
        return

    stop_flag = threading.Event()

    def check_exit():
        while not stop_flag.is_set():
            user_input = input()
            if user_input.strip().lower() == "q":
                stop_flag.set()
                print("Exiting Sysex listener...")

    exit_thread = threading.Thread(target=check_exit, daemon=True)
    exit_thread.start()

    with mido.open_input(  # pyright: ignore[reportAttributeAccessIssue]
        midi_port
    ) as inport:
        print(f"Listening for Sysex on {midi_port}... (press 'q' + Enter to exit)")
        for msg in inport:
            if stop_flag.is_set():
                break
            if msg.type == "sysex":
                print_sysex(msg.data, dispatcher)


if __name__ == "__main__":
    main()
