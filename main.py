from typing import List, Callable
import logging
import mido
import math
from osc.osc_sender import OSCSender

# ----------------------------------- Masks ---------------------------------- #


class SysexHandler:
    """Class to group all sysex masks and mask matching functions"""

    @staticmethod
    def match_sysex(data: List[int], mask: List) -> bool:
        """Generic mask matching function"""
        if len(data) != len(mask):
            return False
        for idx, (d, m) in enumerate(zip(data, mask)):
            if isinstance(m, str):
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
        return tuple(data) == SysexHandler.IGNORE_MESSAGE

    @staticmethod
    def ignore_specific_message_handler(data: List[int], handler: 'OSC_Handler'):
        pass

    # --- Master Fader ---
    MASTER_FADER = [67, 16, 62, 127, 1, 79, 0, "L/R", 0, 0, "u", "v"]

    @staticmethod
    def master_fader_mask(data: List[int]) -> bool:
        if not SysexHandler.match_sysex(data, SysexHandler.MASTER_FADER):
            return False
        x = data[10]
        v = data[11]
        channel = data[7]
        return 0 <= channel <= 15 and 0 <= x <= 7 and 0 <= v <= 127

    @staticmethod
    def master_fader_handler(data: List[int], handler: 'OSC_Handler'):
        x = data[10]
        v = data[11]
        volume = (x * 128 + v) / 1023.0
        handler.master_volume(volume)

    # --- Channel Fader ---
    CH_FADER = [67, 16, 62, 127, 1, 28, 0, "channel", 0, 0, "u", "v"]

    @staticmethod
    def channel_fader_mask(data: List[int]) -> bool:
        if not SysexHandler.match_sysex(data, SysexHandler.CH_FADER):
            return False
        channel = data[7]
        x = data[10]
        v = data[11]
        return 0 <= channel <= 15 and 0 <= x <= 7 and 0 <= v <= 127

    @staticmethod
    def channel_fader_handler(data: List[int], handler: 'OSC_Handler'):
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
    def pan_handler(data: List[int], handler: 'OSC_Handler'):
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
    def y_handler(data: List[int], handler: 'OSC_Handler'):
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
    def x_handler(data: List[int], handler: 'OSC_Handler'):
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
        if len(data) != len(SysexHandler.MASTER_MUTE_1):
            return False
        for idx, (d, m) in enumerate(zip(data, SysexHandler.MASTER_MUTE_1)):
            if m is None:
                continue
            if d != m:
                return False
        return True

    @staticmethod
    def master_mute_handler(data: List[int], handler: 'OSC_Handler'):
        mute_val = data[11]
        osc_mute = 0 if mute_val == 1 else 1
        handler.master_mute(osc_mute)

    MASTER_MUTE_2 = [67, 16, 62, 26, 4, 94, 0, None, 0, 0, 0, None]

    @staticmethod
    def master_mute_mask_2(data: List[int]) -> bool:
        if len(data) != len(SysexHandler.MASTER_MUTE_2):
            return False
        for idx, (d, m) in enumerate(zip(data, SysexHandler.MASTER_MUTE_2)):
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
        if not SysexHandler.match_mute_sysex(data, SysexHandler.MUTE_1):
            return False
        channel = data[7]
        mute = data[11]
        return 0 <= channel <= 15 and mute in (0, 1)

    @staticmethod
    def mute_handler_1(data: List[int], handler: 'OSC_Handler'):
        channel = data[7]
        mute = data[11]
        osc_mute = 0 if mute == 1 else 1
        handler.mute(channel, osc_mute)

    MUTE_2 = [67, 16, 62, 26, 4, 90, 0, "channel", 0, 0, 0, "mute"]

    @staticmethod
    def mute_mask_2(data: List[int]) -> bool:
        if not SysexHandler.match_mute_sysex(data, SysexHandler.MUTE_2):
            return False
        channel = data[7]
        mute = data[11]
        return 0 <= channel <= 15 and mute in (0, 1)

    @staticmethod
    def mute_handler_2(data: List[int], handler: 'OSC_Handler'):
        channel = data[7]
        mute = data[11]
        osc_mute = 0 if mute == 1 else 1
        handler.mute(channel, osc_mute)

    # EQ
    # TODO find different EQ bands
    # Band 1                            V => 82 : Master L/R, 32 : Chan 1-16
    #                                          V => 3 : Gain, 2 : Frequency, 1 : type / Q
    #                                                  V : if Master : 0/1 : L/R. If Channel : channel number
    EQ_BAND_1 = [67, 16, 62, 127, 1, "Sel", "Param", "Ch", None, None, "u", "v"]

    @staticmethod
    def eq_band_1_mask(data: List[int]) -> bool:
        if len(data) != len(SysexHandler.EQ_BAND_1):
            return False
        for d, m in zip(data, SysexHandler.EQ_BAND_1):
            if isinstance(m, str):
                continue
            if m is None:
                continue
            if d != m:
                return False
        channel = data[7]
        u = data[10]
        v = data[11]
        param = data[6]
        selector = data[5]
        type = data[7]
        return (
            0 <= channel <= 15
            and 0 <= u <= 127
            and 0 <= v <= 127
            and selector in (82, 32)
            and param in (3, 2, 1)
            and type in range(0, 41)
        )

    # EQ Bands work differently in 01v96i than Holophonix
    #   01v96i  >   Holophonix
    #   Band 1  >   Band 1 or 2 or 3 depending on filter type (cut / shelf / bell)
    #   Band 2  >   Band 4
    #   Band 3  >   Band 5
    #   Band 4  >   Band 6 or 7 or 8 depending on filter type (cut / shelf / bell)

    @staticmethod
    def eq_band_1_handler(data: List[int], handler: 'OSC_Handler'):
        if data[5] == 82:  # Master
            selector = 'master'
            channel = None
        elif data[5] == 32:  # Channel
            selector = 'channel'
            channel = data[7]
        else:
            logging.error("Invalid selector in EQ message")
            return

        if data[6] == 3:  # Gain handling
            if data[10] < 64:
                gain = data[10] * 127 + data[11]
            else:
                gain = -((127 - data[10]) * 127 + (127 - data[11]))
            gain = gain / 178 * 18
            handler.eq(selector=selector, channel=channel, band=1, gain=gain)
        elif data[6] == 2:  # Frequency handling
            # Logarithmic scaling: value=5 -> 21.2 Hz, value=124 -> 20000 Hz
            v = data[11]
            v_min, v_max = 5, 124
            hz_min, hz_max = 21.2, 20000
            # Logarithmic interpolation
            freq = hz_min * ((hz_max / hz_min) ** ((v - v_min) / (v_max - v_min)))
            handler.eq(selector=selector, channel=channel, band=1, freq=freq)
        elif data[6] == 1:  # Type / Q handling
            # TODO add band handling for HPF / Shelf / Bell and input band
            if data[11] == 44:
                # HPF Filter -> Band 1
                _bandType = 'HPF'
            elif data[11] == 41:
                # Shelf filter -> Band 2
                _bandType = 'Shelf'
            else:
                # Bell filter -> Band 3
                _bandType = 'Bell'  # Noqa F841
                q_raw = data[11]
                # Logarithmic scaling: 40 -> 0.1, 0 -> 10
                q = 10 * (0.1 / 10) ** (q_raw / 40)
                handler.eq(selector=selector, channel=channel, band=3, Q=q)


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

    def eq(
            self, selector: str, band: int,
            gain: float | None = None, freq: float | None = None, Q: float | None = None,
            channel: int | None = None
    ):
        if gain is not None:
            if selector == 'master':
                osc_address = f"/master/equalizer/filter/{band}/gain"
            else:
                if channel is None:
                    logging.error("Channel must be provided for channel EQ")
                else:
                    osc_address = f"/track/{channel+1}/equalizer/filter/{band}/gain"
            self.osc_sender.send(osc_address, gain)
            print(f"OSC sent: {osc_address} {gain}")
        if freq is not None:
            if selector == 'master':
                osc_address = f"/master/equalizer/filter/{band}/freq"
            else:
                if channel is None:
                    logging.error("Channel must be provided for channel EQ")
                else:
                    osc_address = f"/track/{channel+1}/equalizer/filter/{band}/freq"
            self.osc_sender.send(osc_address, freq)
            print(f"OSC sent: {osc_address} {freq}")
        if Q is not None:
            if selector == 'master':
                osc_address = f"/master/equalizer/filter/{band}/q"
            else:
                if channel is None:
                    logging.error("Channel must be provided for channel EQ")
                else:
                    osc_address = f"/track/{channel+1}/equalizer/filter/{band}/q"
            self.osc_sender.send(osc_address, Q)
            print(f"OSC sent: {osc_address} {Q}")


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
        SysexHandler.ignore_specific_message_mask, SysexHandler.ignore_specific_message_handler
    )
    dispatcher.add_handler(SysexHandler.master_fader_mask, SysexHandler.master_fader_handler)
    dispatcher.add_handler(SysexHandler.master_mute_mask_1, SysexHandler.master_mute_handler)
    dispatcher.add_handler(SysexHandler.master_mute_mask_2, SysexHandler.master_mute_handler)
    dispatcher.add_handler(SysexHandler.channel_fader_mask, SysexHandler.channel_fader_handler)
    dispatcher.add_handler(SysexHandler.mute_mask_1, SysexHandler.mute_handler_1)
    dispatcher.add_handler(SysexHandler.mute_mask_2, SysexHandler.mute_handler_2)
    dispatcher.add_handler(SysexHandler.pan_mask, SysexHandler.pan_handler)
    dispatcher.add_handler(SysexHandler.y_mask, SysexHandler.y_handler)
    dispatcher.add_handler(SysexHandler.x_mask, SysexHandler.x_handler)
    dispatcher.add_handler(SysexHandler.eq_band_1_mask, SysexHandler.eq_band_1_handler)

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
