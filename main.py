from typing import List, Callable
import argparse
import logging
import math
import mido
from midi.midi_sysex import MidiSysexListener
from osc.osc_sender import OSCSender

# ----------------------------------- Masks ---------------------------------- #


class SysexHandler:
    """Class to group all sysex masks and mask matching functions"""

    @staticmethod
    def match_sysex(data: List[int], mask: List) -> bool:
        """Generic mask matching function"""
        if len(data) != len(mask):
            return False
        for d, m in zip(data, mask):
            if isinstance(m, str):
                continue
            if m is None:
                continue
            if d != m:
                return False
        return True

    @staticmethod
    def decode_value(data: List[int]) -> int:
        """Decode the 4-byte data field as a 28-bit two's-complement integer.

        Yamaha carries a parameter's value in four 7-bit bytes (Reference Manual
        §2.8.3.2, "Parameter change (Edit buffer)"). Negative values are two's
        complement, which is why the leading bytes read 0x7F below zero.
        """
        raw = (data[8] << 21) | (data[9] << 14) | (data[10] << 7) | data[11]
        if raw >= 1 << 27:
            raw -= 1 << 28
        return raw

    # --- Ignore Specific Message ---
    # The 01v96i broadcasts this SysEx frequently — can be used to auto-detect the port?
    IGNORE_MESSAGE = (67, 16, 62, 26, 127)

    @staticmethod
    def ignore_specific_message_mask(data: List[int]) -> bool:
        return tuple(data) == SysexHandler.IGNORE_MESSAGE

    @staticmethod
    def ignore_specific_message_handler(data: List[int], handler: 'OSC_Handler'):
        pass

    # Fader position index, not dB. Measured on the console:
    #   channel: raw 0 = -inf,  raw 823 = 0.0 dB,  raw 1023 = +10.0 dB
    #   master:  raw 0 = -inf,  raw 1023 = 0.0 dB  (tops out at unity, not +10)
    # Yamaha's exact table lives in the MIDI Protocol document, which is no longer
    # distributed, so the shape between anchors follows the IEC 60268-17 console
    # taper rescaled through raw 823. Exact at the anchors, approximate between;
    # add measured pairs to tighten it.
    FADER_MAX_RAW = 1023

    # (raw, dB) breakpoints, interpolated linearly in dB.
    FADER_LAW = [
        (0, -90.0),     # bottom stop; reported as -inf
        (55, -70.0),
        (166, -50.0),
        (331, -30.0),
        (552, -10.0),
        (823, 0.0),     # measured
        (1023, 10.0),   # measured
    ]

    # The stereo fader spans the same travel but ends at unity instead of +10.
    MASTER_FADER_LAW = [(raw, db - 10.0) for raw, db in FADER_LAW]

    @staticmethod
    def fader_db(raw: int, master: bool = False) -> float:
        """Convert a fader position index to dB via the interpolated fader law."""
        law = SysexHandler.MASTER_FADER_LAW if master else SysexHandler.FADER_LAW
        raw = max(law[0][0], min(law[-1][0], raw))
        for (r0, d0), (r1, d1) in zip(law, law[1:]):
            if raw <= r1:
                span = r1 - r0
                return d0 if span == 0 else d0 + (d1 - d0) * (raw - r0) / span
        return law[-1][1]

    # --- Master Fader ---
    MASTER_FADER = [67, 16, 62, 127, 1, 79, 0, "L/R", None, None, "u", "v"]

    @staticmethod
    def master_fader_mask(data: List[int]) -> bool:
        if not SysexHandler.match_sysex(data, SysexHandler.MASTER_FADER):
            return False
        # No u <= 7 bound: below 0 dB the value is two's complement, not a small int.
        return 0 <= data[7] <= 15

    @staticmethod
    def master_fader_handler(data: List[int], handler: 'OSC_Handler'):
        handler.master_volume(SysexHandler.fader_db(SysexHandler.decode_value(data), master=True))

    # --- Channel Fader ---
    CH_FADER = [67, 16, 62, 127, 1, 28, 0, "channel", None, None, "u", "v"]

    @staticmethod
    def channel_fader_mask(data: List[int]) -> bool:
        if not SysexHandler.match_sysex(data, SysexHandler.CH_FADER):
            return False
        # No u <= 7 bound: below 0 dB the value is two's complement, not a small int.
        return 0 <= data[7] <= 15

    @staticmethod
    def channel_fader_handler(data: List[int], handler: 'OSC_Handler'):
        channel = data[7]
        handler.volume(channel, SysexHandler.fader_db(SysexHandler.decode_value(data)))

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
        # Console range is L63..C..R63; the wire value is the displayed number.
        channel = data[7]
        pan = SysexHandler.decode_value(data) / 63
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
        # Console range is L63..C..R63; the wire value is the displayed number.
        channel = data[7]
        y = SysexHandler.decode_value(data) / 63
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
        # Console range is L63..C..R63; the wire value is the displayed number.
        channel = data[7]
        x = SysexHandler.decode_value(data) / 63
        handler.x(channel, x)

    # --- Master Mute ---
    MASTER_MUTE_1 = [67, 16, 62, 127, 1, 77, 0, None, 0, 0, 0, None]

    @staticmethod
    def master_mute_mask_1(data: List[int]) -> bool:
        if len(data) != len(SysexHandler.MASTER_MUTE_1):
            return False
        for d, m in zip(data, SysexHandler.MASTER_MUTE_1):
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
        for d, m in zip(data, SysexHandler.MASTER_MUTE_2):
            if m is None:
                continue
            if d != m:
                return False
        return True

    # --- Channel Mute ---
    MUTE_1 = [67, 16, 62, 127, 1, 26, 0, "channel", 0, 0, 0, "mute"]

    @staticmethod
    def mute_mask_1(data: List[int]) -> bool:
        if not SysexHandler.match_sysex(data, SysexHandler.MUTE_1):
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
        if not SysexHandler.match_sysex(data, SysexHandler.MUTE_2):
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

    # EQ                               V Element:   82 master L/R, 32 channels 1-16
    #                                          V Parameter: band + control, see EQ_PARAMS
    #                                                  V Channel:   0/1 (L/R) for master,
    #                                                              else the channel number
    EQ = [67, 16, 62, 127, 1, "Sel", "Param", "Ch", None, None, "u", "v"]

    # Parameter no. -> (band, control). Bands are contiguous blocks; band 1 and
    # band 4 each carry an extra "enable" because the console repurposes their gain
    # knob as the HPF/LPF on/off switch. Bands 2-4 observed on device via their
    # gain parameters (7, 10, 13); the freq/Q slots follow from the block layout.
    EQ_PARAMS = {
        1: (1, "q"), 2: (1, "freq"), 3: (1, "gain"), 4: (1, "enable"),
        5: (2, "q"), 6: (2, "freq"), 7: (2, "gain"),
        8: (3, "q"), 9: (3, "freq"), 10: (3, "gain"),
        11: (4, "q"), 12: (4, "freq"), 13: (4, "gain"), 14: (4, "enable"),
    }

    # Type and Q share one parameter: 0..40 select bell Q (10 .. 0.1) and the
    # filter types sit above that range, where the control stops -- it does not
    # wrap. The type codes are global; each band exposes only the two that apply
    # to it (band 1: low shelf + HPF, band 4: high shelf + LPF). Confirmed from
    # captures: band 1 emits 0..41 and 44, band 4 emits 0..40, 42 and 43.
    EQ_TYPE_CODES = {
        41: "L.Shelf",
        42: "H.Shelf",
        43: "LPF",
        44: "HPF",
    }

    @staticmethod
    def eq_mask(data: List[int]) -> bool:
        if len(data) != len(SysexHandler.EQ):
            return False
        for d, m in zip(data, SysexHandler.EQ):
            if isinstance(m, str):
                continue
            if m is None:
                continue
            if d != m:
                return False
        return (
            0 <= data[7] <= 15
            and data[5] in (82, 32)
            and data[6] in SysexHandler.EQ_PARAMS
        )

    # EQ Bands work differently in 01v96i than Holophonix
    #   01v96i  >   Holophonix
    #   Band 1  >   Band 1 or 2 or 3 depending on filter type (cut / shelf / bell)
    #   Band 2  >   Band 4
    #   Band 3  >   Band 5
    #   Band 4  >   Band 6 or 7 or 8 depending on filter type (cut / shelf / bell)

    @staticmethod
    def eq_handler(data: List[int], handler: 'OSC_Handler'):
        if data[5] == 82:  # Master
            selector = 'master'
            channel = None
        elif data[5] == 32:  # Channel
            selector = 'channel'
            channel = data[7]
        else:
            logging.error("Invalid selector in EQ message")
            return

        band, control = SysexHandler.EQ_PARAMS[data[6]]
        raw = SysexHandler.decode_value(data)

        if control == "gain":
            # Raw is 0.1 dB steps: 180 == +18.0 dB, confirmed on device.
            handler.eq(selector=selector, channel=channel, band=band, gain=raw / 10)
        elif control == "freq":
            # Logarithmic scaling: value=5 -> 21.2 Hz, value=124 -> 20000 Hz
            v_min, v_max = 5, 124
            hz_min, hz_max = 21.2, 20000
            freq = hz_min * ((hz_max / hz_min) ** ((raw - v_min) / (v_max - v_min)))
            handler.eq(selector=selector, channel=channel, band=band, freq=freq)
        elif control == "q":
            # Bands 1 and 4 are the shelving/cut bands (HPF + low shelf, LPF +
            # high shelf); bands 2-3 are bell only.
            filter_type = SysexHandler.EQ_TYPE_CODES.get(raw)
            if filter_type is None:
                filter_type = 'Bell'
                # Logarithmic scaling: 40 -> 0.1, 0 -> 10
                handler.eq(
                    selector=selector, channel=channel, band=band,
                    Q=10 * (0.1 / 10) ** (raw / 40),
                )
            logging.debug(
                f"EQ filter type: {selector} channel={channel} band={band} {filter_type}"
            )
        elif control == "enable":
            # HPF (band 1) or LPF (band 4): the console repurposes that band's gain
            # knob as the filter's on/off switch and sends this instead of a gain.
            # TODO: no OSC address yet — the Holophonix filter-slot mapping is
            # unresolved (docs/01v96i.md §5.2). Decoded and logged for now.
            logging.info(
                f"EQ filter enable: {selector} channel={channel} "
                f"band={band} enabled={bool(raw)}"
            )


# --------------------------------- Handlers --------------------------------- #


class OSC_Handler:
    def __init__(self, osc_sender: OSCSender):
        self.osc_sender = osc_sender

        self.XY_SCALE = 10
        self._x: dict[int, float] = {}
        self._y: dict[int, float] = {}

    def pan(self, channel: int, value: float):
        azim = value * 45  # -45.0 to 45.0
        osc_address = f"/track/{channel+1}/azim"
        self.osc_sender.send(osc_address, azim)
        logging.debug(f"OSC sent: {osc_address} {azim:.1f}")

    def x(self, channel: int, value: float):
        self._x[channel] = value * self.XY_SCALE
        self._xy(channel)

    def y(self, channel: int, value: float):
        self._y[channel] = value * self.XY_SCALE
        self._xy(channel)

    def _xy(self, channel: int):
        x = self._x.get(channel, 0.0)
        y = self._y.get(channel, 0.0)
        azim = math.degrees(math.atan2(x, y))  # <-- swapped arguments
        dist = (x**2 + y**2) ** 0.5
        osc_address_azim = f"/track/{channel+1}/azim"
        osc_address_dist = f"/track/{channel+1}/dist"
        self.osc_sender.send(osc_address_azim, azim)
        self.osc_sender.send(osc_address_dist, dist)
        logging.debug(f"OSC sent: {osc_address_azim} {azim:.1f}")
        logging.debug(f"OSC sent: {osc_address_dist} {dist:.3f}")

    def volume(self, channel: int, db_value: float):
        osc_address = f"/track/{channel+1}/gain"
        self.osc_sender.send(osc_address, db_value)
        logging.debug(f"OSC sent: {osc_address} {db_value:.1f}dB")

    def master_volume(self, db_value: float):
        osc_address = "/master/gain"
        self.osc_sender.send(osc_address, db_value)
        logging.debug(f"OSC sent: {osc_address} {db_value:.1f}dB")

    def mute(self, channel: int, value: int):
        osc_address = f"/track/{channel+1}/mute"
        self.osc_sender.send(osc_address, value)
        logging.debug(f"OSC sent: {osc_address} {value}")

    def master_mute(self, value: int):
        osc_address = "/master/mute"
        self.osc_sender.send(osc_address, value)
        logging.debug(f"OSC sent: {osc_address} {value}")

    def eq(
            self, selector: str, band: int,
            gain: float | None = None, freq: float | None = None, Q: float | None = None,
            channel: int | None = None
    ):
        if selector != 'master' and channel is None:
            logging.error("Channel must be provided for channel EQ")
            return
        assert channel is not None
        if gain is not None:
            if selector == 'master':
                osc_address = f"/master/equalizer/filter/{band}/gain"
            else:
                osc_address = f"/track/{channel+1}/equalizer/filter/{band}/gain"
            self.osc_sender.send(osc_address, gain)
            logging.debug(f"OSC sent: {osc_address} {gain}")
        if freq is not None:
            if selector == 'master':
                osc_address = f"/master/equalizer/filter/{band}/freq"
            else:
                osc_address = f"/track/{channel+1}/equalizer/filter/{band}/freq"
            self.osc_sender.send(osc_address, freq)
            logging.debug(f"OSC sent: {osc_address} {freq}")
        if Q is not None:
            if selector == 'master':
                osc_address = f"/master/equalizer/filter/{band}/q"
            else:
                osc_address = f"/track/{channel+1}/equalizer/filter/{band}/q"
            self.osc_sender.send(osc_address, Q)
            logging.debug(f"OSC sent: {osc_address} {Q}")


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
        logging.warning(f"Unhandled Sysex: {data}")


# TODO: auto-detect the 01v96i by probing each available port for SysexHandler.IGNORE_MESSAGE ?
# which the mixer sends frequently. First port to emit it wins; fall back to interactive
# selection if none detected within a short timeout.
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

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Yamaha 01v96i MIDI to OSC bridge")
    parser.add_argument("--ip", default="192.168.1.104", help="OSC destination IP")
    parser.add_argument("--port", type=int, default=4003, help="OSC destination port")
    args = parser.parse_args()

    osc_sender = OSCSender(args.ip, args.port)
    handler = OSC_Handler(osc_sender)
    dispatcher = SysexDispatcher(handler)
    dispatcher.add_handler(SysexHandler.ignore_specific_message_mask, SysexHandler.ignore_specific_message_handler)
    dispatcher.add_handler(SysexHandler.master_fader_mask, SysexHandler.master_fader_handler)
    dispatcher.add_handler(SysexHandler.master_mute_mask_1, SysexHandler.master_mute_handler)
    dispatcher.add_handler(SysexHandler.master_mute_mask_2, SysexHandler.master_mute_handler)
    dispatcher.add_handler(SysexHandler.channel_fader_mask, SysexHandler.channel_fader_handler)
    dispatcher.add_handler(SysexHandler.mute_mask_1, SysexHandler.mute_handler_1)
    dispatcher.add_handler(SysexHandler.mute_mask_2, SysexHandler.mute_handler_2)
    dispatcher.add_handler(SysexHandler.pan_mask, SysexHandler.pan_handler)
    dispatcher.add_handler(SysexHandler.y_mask, SysexHandler.y_handler)
    dispatcher.add_handler(SysexHandler.x_mask, SysexHandler.x_handler)
    dispatcher.add_handler(SysexHandler.eq_mask, SysexHandler.eq_handler)

    midi_port = select_midi_port()
    if not midi_port:
        return

    listener = MidiSysexListener(midi_port)
    listener.add_callback(lambda data: dispatcher.dispatch(list(data)))

    def check_exit():
        while True:
            if input().strip().lower() == "q":
                listener.stop()
                logging.info("Exiting Sysex listener...")
                break

    exit_thread = threading.Thread(target=check_exit, daemon=True)
    exit_thread.start()

    logging.info(f"Listening for Sysex on {midi_port}... (press 'q' + Enter to exit)")
    listener.listen()


if __name__ == "__main__":
    main()
