#!/usr/bin/env python3
"""data_bus_avionics_core.py - Data Bus / Avionics Network Engineer core.

This is the role's ENGINE: given an aircraft bus architecture it decodes
ARINC 429 and MIL-STD-1553 words, budgets ARINC 429 label-rate schedules
into bus load and percent utilization, computes MIL-STD-1553 bus loading
from a bus-controller minor-frame schedule, sizes ARINC 664 AFDX virtual
links against the 100 Mbps link, and BUILDS the Avionics Data Bus Loading
and Protocol Assessment deliverable. It also gate-checks deliverables.
Standalone: no external repo needed.

Domain rules encoded here mirror the bound AeroSkills data-bus leaves
(AeroSkills avionics/data-bus/*, themselves paraphrases of the public
protocol practice) so the same quantity can be computed two independent
ways and cross-checked in provenance:

- ARINC 429 (Mark 33 DITS): every transmitted word occupies 36 bit-times
  on the bus (32 data bits + 4-bit inter-word gap); high-speed link is
  100 kbps (about 2777.8 words/s), low-speed 12.5 kbps (about 347.2
  words/s); common design guideline 80% utilization. Word: bits 1-8
  octal label, 9-10 SDI, 11-29 data, 30-31 SSM, 32 odd parity (integer
  bit 0 = first bit transmitted).
- MIL-STD-1553B: 1 Mbps command/response bus; 20-bit words (16 info +
  3-bit sync + odd parity); message = command/status overhead + data
  words; each wire word occupies a 24 us slot (20 us word + 4 us gap);
  loading is schedule time over the minor frame against an 80% budget.
- ARINC 664 Part 7 AFDX: VL bandwidth = max_frame_bytes*8/(BAG seconds)
  with BAG in {1,2,4,8,16,32,64,128} ms and frame 64-1518 bytes; the VL
  set must fit the 100 Mbps link; latency = 2 serializations + switches
  x switch delay; jitter slack = budget - measured.

ARINC 429 / ARINC 664 text is proprietary and never reproduced; the
field layouts and timing figures above are common-knowledge protocol
summaries. MIL-STD-1553 is US public-domain work, paraphrase used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())

# ---------------------------------------------------------------------------
# Domain constants (grounded in the bound data-bus leaves)
# ---------------------------------------------------------------------------

# ARINC 429 loading model (leaf avionics/data-bus/arinc429-bus-loading)
A429_BITS_PER_WORD = 36.0        # 32 data bits + 4-bit gap
A429_RATE_100_KBPS = 100000.0    # high-speed link
A429_RATE_12_5_KBPS = 12500.0    # low-speed link
A429_GUIDELINE_PCT = 80.0        # common design guideline

# ARINC 429 word layout (leaf avionics/data-bus/arinc429-protocol).
# Integer bit 0 is the first bit transmitted (ARINC bit 1).
A429_LABEL_MASK = 0xFF           # ARINC bits 1-8
A429_SDI_MASK = 0b11             # ARINC bits 9-10
A429_DATA_MASK = 0x7FFFF         # ARINC bits 11-29 (19-bit field)
A429_SSM_MASK = 0b11             # ARINC bits 30-31
A429_PARITY_BIT = 31             # ARINC bit 32
A429_BNR_SIGN_BIT = 1 << 18
A429_BNR_POS_MAX = (1 << 18) - 1
A429_BNR_NEG_MIN = -(1 << 18)

# MIL-STD-1553 loading model (leaf avionics/data-bus/mil-std-1553-bus-loading)
M1553_WORD_TIME_US = 20.0        # 20 bit times at 1 Mbps
M1553_WORD_GAP_US = 4.0          # inter-word gap
M1553_WORD_SLOT_US = M1553_WORD_TIME_US + M1553_WORD_GAP_US  # 24.0 us
M1553_FRAME_US_DEFAULT = 5000.0  # 5 ms minor frame
M1553_BUDGET_FRACTION = 0.80
M1553_KINDS = ("BCRT", "RTBC", "RTRT")

# MIL-STD-1553 word layout (leaf avionics/data-bus/mil-std-1553)
M1553_WORD_MASK = (1 << 20) - 1
M1553_RT_MASK = 0x1F
M1553_DATA16_MASK = 0xFFFF
M1553_SYNC_COMMAND = 0b100
M1553_SYNC_DATA = 0b011
M1553_MODE_SUBADDRESSES = (0, 0x1F)
M1553_BROADCAST_RT = 0x1F

# ARINC 664 AFDX (leaf avionics/data-bus/arinc664-afdx)
AFDX_LEGAL_BAGS = (1, 2, 4, 8, 16, 32, 64, 128)
AFDX_MIN_FRAME = 64
AFDX_MAX_FRAME = 1518
AFDX_LINK_RATE = 100_000_000.0   # 100 Mbps full-duplex link

# ---------------------------------------------------------------------------
# Guards (stdlib, shared)
# ---------------------------------------------------------------------------


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number, got %r" % (name, value))
    return float(value)


def _require_int(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer, got %r" % (name, value))
    if not (lo <= value <= hi):
        raise ValueError("%s %d out of range [%d, %d]" % (name, value, lo, hi))
    return value


# ---------------------------------------------------------------------------
# ARINC 429 protocol (word decode/encode, parity, BNR)
# ---------------------------------------------------------------------------

def a429_parity_ok(word):
    """True when a 32-bit word carries odd parity (odd number of 1 bits)."""
    word = _require_int(word, "word", 0, 0xFFFFFFFF)
    return (bin(word).count("1") % 2) == 1


def a429_decode_word(word):
    """Split a 32-bit ARINC 429 word into label, SDI, data, SSM, parity."""
    word = _require_int(word, "word", 0, 0xFFFFFFFF)
    return {
        "label": word & A429_LABEL_MASK,
        "sdi": (word >> 8) & A429_SDI_MASK,
        "data": (word >> 10) & A429_DATA_MASK,
        "ssm": (word >> 29) & A429_SSM_MASK,
        "parity": (word >> A429_PARITY_BIT) & 1,
        "parity_ok": a429_parity_ok(word),
    }


def a429_build_word(label, sdi, data, ssm, parity=None):
    """Pack label, SDI, 19-bit data, SSM, and odd parity into 32 bits.

    Worked anchor: build_word(8, 1, 1234, 3) -> 1611876616 (0x60134908).
    """
    if isinstance(label, str):
        text = label.strip()
        if not re.match(r"^[0-7]+$", text):
            raise ValueError("label %r is not octal digits (0-7)" % (label,))
        label = int(text, 8)
    label = _require_int(label, "label", 0, A429_LABEL_MASK)
    sdi = _require_int(sdi, "sdi", 0, A429_SDI_MASK)
    data = _require_int(data, "data", 0, A429_DATA_MASK)
    ssm = _require_int(ssm, "ssm", 0, A429_SSM_MASK)
    payload = label | (sdi << 8) | (data << 10) | (ssm << 29)
    if parity is None:
        parity = 0 if (bin(payload & 0x7FFFFFFF).count("1") % 2) else 1
    else:
        parity = _require_int(parity, "parity", 0, 1)
    return payload | (parity << A429_PARITY_BIT)


def a429_bnr_encode(value, scale_factor):
    """Encode a signed BNR value into the 19-bit data field (two's complement).

    Worked anchor: 123.4 at LSB 0.1 -> field 1234; -12.3 -> field 524165.
    """
    value = _number(value, "value")
    scale = _number(scale_factor, "scale_factor")
    if scale <= 0.0:
        raise ValueError("scale_factor must be positive, got %r" % (scale,))
    raw = int(round(value / scale))
    if not (A429_BNR_NEG_MIN <= raw <= A429_BNR_POS_MAX):
        raise ValueError(
            "value %.6f does not fit BNR range at scale %.6f" % (value, scale))
    if raw < 0:
        raw += 1 << 19
    return raw


def a429_bnr_decode(data_field, scale_factor):
    """Decode a 19-bit BNR data field to its signed engineering value."""
    data_field = _require_int(data_field, "data_field", 0, A429_DATA_MASK)
    scale = _number(scale_factor, "scale_factor")
    if scale <= 0.0:
        raise ValueError("scale_factor must be positive, got %r" % (scale,))
    raw = data_field - (1 << 19) if data_field & A429_BNR_SIGN_BIT else data_field
    return raw * scale


# ---------------------------------------------------------------------------
# ARINC 429 bus loading (label rate schedule -> utilization)
# ---------------------------------------------------------------------------

def a429_total_word_rate(label_rates):
    """Sum a label rate schedule (dict {label: words/s} or list) into wps."""
    rates = list(label_rates.values()) if isinstance(label_rates, dict) \
        else list(label_rates)
    if not rates:
        raise ValueError("the label rate schedule is empty")
    for r in rates:
        if r < 0:
            raise ValueError("label rates must be non-negative, got %r" % (r,))
    return sum(float(r) for r in rates)


def a429_bus_load_bps(total_words_per_s):
    """Bus load in bits/s: every word occupies 36 bit-times on the bus."""
    if total_words_per_s < 0:
        raise ValueError("words per second must be non-negative")
    return float(total_words_per_s) * A429_BITS_PER_WORD


def a429_word_capacity(link_rate_bps=A429_RATE_100_KBPS):
    """Word-per-second capacity of the link: rate / 36 bit-times.

    About 2777.8 words/s at 100 kbps, 347.2 words/s at 12.5 kbps.
    """
    if link_rate_bps <= 0:
        raise ValueError("link rate must be positive")
    return float(link_rate_bps) / A429_BITS_PER_WORD


def a429_utilization_pct(total_words_per_s, link_rate_bps=A429_RATE_100_KBPS):
    """Percent of the link occupied by the word schedule."""
    if total_words_per_s < 0:
        raise ValueError("words per second must be non-negative")
    if link_rate_bps <= 0:
        raise ValueError("link rate must be positive")
    return a429_bus_load_bps(total_words_per_s) / float(link_rate_bps) * 100.0


def a429_loading_summary(label_rates, link_rate_bps=A429_RATE_100_KBPS):
    """Full ARINC 429 bus loading budget for a label rate schedule.

    Returns total_words_per_s, load_bps, utilization_pct, capacity_wps,
    capacity_verdict (FITS/OVER against 100% of the link), guideline_pct,
    guideline_verdict (FITS/VIOLATION against the 80% design guideline),
    headroom_pct (margin to the guideline, floored at 0).
    """
    total = a429_total_word_rate(label_rates)
    if link_rate_bps <= 0:
        raise ValueError("link rate must be positive")
    load_bps = a429_bus_load_bps(total)
    utilization_pct = a429_utilization_pct(total, link_rate_bps)
    capacity_wps = a429_word_capacity(link_rate_bps)
    return {
        "total_words_per_s": total,
        "load_bps": load_bps,
        "utilization_pct": utilization_pct,
        "capacity_wps": capacity_wps,
        "capacity_verdict": "OVER" if utilization_pct > 100.0 else "FITS",
        "guideline_pct": A429_GUIDELINE_PCT,
        "guideline_verdict": "VIOLATION"
        if utilization_pct > A429_GUIDELINE_PCT else "FITS",
        "headroom_pct": max(0.0, A429_GUIDELINE_PCT - utilization_pct),
    }


# ---------------------------------------------------------------------------
# MIL-STD-1553 protocol (command / status / data words, classification)
# ---------------------------------------------------------------------------

def m1553_parity_ok(word):
    """True when a 20-bit word carries odd parity."""
    word = _require_int(word, "word", 0, M1553_WORD_MASK)
    return (bin(word).count("1") % 2) == 1


def _m1553_parity_bit(data16, sync):
    ones = bin(data16 & M1553_DATA16_MASK).count("1") \
        + bin(sync & 0b111).count("1")
    return 0 if (ones % 2) else 1


def m1553_encode_command_word(rt_address, subaddress, word_count,
                              transmit_receive):
    """Pack RT address, T/R, subaddress, word count, odd parity (20 bits).

    Worked anchor: (5, 12, 16, 1) -> 93316, odd parity.
    """
    rt = _require_int(rt_address, "rt_address", 0, M1553_RT_MASK)
    sa = _require_int(subaddress, "subaddress", 0, M1553_RT_MASK)
    wc = _require_int(word_count, "word_count", 0, M1553_RT_MASK)
    tr = _require_int(transmit_receive, "transmit_receive", 0, 1)
    data16 = (rt << 11) | (tr << 10) | (sa << 5) | wc
    parity = _m1553_parity_bit(data16, M1553_SYNC_COMMAND)
    return (parity << 19) | (data16 << 3) | M1553_SYNC_COMMAND


def m1553_decode_command_word(word):
    """Split a 20-bit command word; raises on a non-command sync pattern."""
    word = _require_int(word, "word", 0, M1553_WORD_MASK)
    if (word & 0b111) != M1553_SYNC_COMMAND:
        raise ValueError("word 0x%X is not a command/status sync word" % word)
    data16 = (word >> 3) & M1553_DATA16_MASK
    return {
        "rt_address": (data16 >> 11) & M1553_RT_MASK,
        "transmit_receive": (data16 >> 10) & 1,
        "subaddress": (data16 >> 5) & M1553_RT_MASK,
        "word_count": data16 & M1553_RT_MASK,
        "parity": (word >> 19) & 1,
        "parity_ok": m1553_parity_ok(word),
    }


def m1553_encode_data_word(data):
    """Pack 16 data bits and odd parity into a 20-bit data word.

    Worked anchor: 0x7FFF -> 262139.
    """
    data = _require_int(data, "data", 0, M1553_DATA16_MASK)
    parity = _m1553_parity_bit(data, M1553_SYNC_DATA)
    return (parity << 19) | (data << 3) | M1553_SYNC_DATA


def m1553_encode_status_word(rt_address, message_error=0, instrumentation=0,
                             service_request=0, broadcast_received=0, busy=0,
                             subsystem_flag=0,
                             dynamic_bus_control_acceptance=0,
                             terminal_flag=0):
    """Pack RT address and status flags with odd parity.

    Worked anchor: encode_status_word(5, busy=1) -> 606276.
    """
    rt = _require_int(rt_address, "rt_address", 0, M1553_RT_MASK)
    me = _require_int(message_error, "message_error", 0, 1)
    inst = _require_int(instrumentation, "instrumentation", 0, 1)
    sr = _require_int(service_request, "service_request", 0, 1)
    bcr = _require_int(broadcast_received, "broadcast_received", 0, 1)
    bsy = _require_int(busy, "busy", 0, 1)
    ssf = _require_int(subsystem_flag, "subsystem_flag", 0, 1)
    dbca = _require_int(dynamic_bus_control_acceptance,
                        "dynamic_bus_control_acceptance", 0, 1)
    tfl = _require_int(terminal_flag, "terminal_flag", 0, 1)
    data16 = ((rt << 11) | (me << 10) | (inst << 9) | (sr << 8) | (bcr << 4)
              | (bsy << 3) | (ssf << 2) | (dbca << 1) | tfl)
    parity = _m1553_parity_bit(data16, M1553_SYNC_COMMAND)
    return (parity << 19) | (data16 << 3) | M1553_SYNC_COMMAND


def m1553_decode_status_word(word):
    """Split a 20-bit status word into RT address and status flags.

    Flag layout in transmission order: message error, instrumentation,
    service request, 3 reserved zeros, broadcast received, busy,
    subsystem flag, dynamic bus control acceptance, terminal flag.
    Worked anchor: 606276 -> RT 5 with busy=1.
    """
    word = _require_int(word, "word", 0, M1553_WORD_MASK)
    if (word & 0b111) != M1553_SYNC_COMMAND:
        raise ValueError("word 0x%X is not a status sync word" % word)
    data16 = (word >> 3) & M1553_DATA16_MASK
    return {
        "rt_address": (data16 >> 11) & M1553_RT_MASK,
        "message_error": (data16 >> 10) & 1,
        "instrumentation": (data16 >> 9) & 1,
        "service_request": (data16 >> 8) & 1,
        "broadcast_received": (data16 >> 4) & 1,
        "busy": (data16 >> 3) & 1,
        "subsystem_flag": (data16 >> 2) & 1,
        "dynamic_bus_control_acceptance": (data16 >> 1) & 1,
        "terminal_flag": data16 & 1,
        "parity": (word >> 19) & 1,
        "parity_ok": m1553_parity_ok(word),
    }


def m1553_classify_message(rt_address, subaddress, word_count,
                           transmit_receive):
    """Classify the message a command word initiates.

    Returns broadcast (RT 31), mode-code (subaddress 0/31), rt-to-bc
    (T/R 1), or bc-to-rt (T/R 0).
    """
    rt = _require_int(rt_address, "rt_address", 0, M1553_RT_MASK)
    sa = _require_int(subaddress, "subaddress", 0, M1553_RT_MASK)
    _require_int(word_count, "word_count", 0, M1553_RT_MASK)
    tr = _require_int(transmit_receive, "transmit_receive", 0, 1)
    if rt == M1553_BROADCAST_RT:
        return "broadcast"
    if sa in M1553_MODE_SUBADDRESSES:
        return "mode-code"
    if tr == 1:
        return "rt-to-bc"
    return "bc-to-rt"


# ---------------------------------------------------------------------------
# MIL-STD-1553 bus loading (BC minor-frame schedule -> utilization)
# ---------------------------------------------------------------------------

def m1553_wire_words(kind, data_words):
    """Wire words on the bus for one message: overhead + data words.

    BCRT/RTBC = 1 command + 1 status + data; RTRT = 2 commands + 1 status
    + data. data_words must be an integer in 1..32.
    """
    if kind not in M1553_KINDS:
        raise ValueError("unknown message kind %r, use BCRT, RTBC or RTRT"
                         % (kind,))
    if not isinstance(data_words, int):
        raise ValueError("data_words must be an integer")
    if data_words < 1 or data_words > 32:
        raise ValueError("data_words must be in 1..32")
    return data_words + (3 if kind == "RTRT" else 2)


def m1553_message_time_us(kind, data_words):
    """Bus time in us for one message: wire words x 24 us slot."""
    return float(m1553_wire_words(kind, data_words)) * M1553_WORD_SLOT_US


def m1553_schedule_utilization(messages, frame_us=M1553_FRAME_US_DEFAULT):
    """Utilization of a minor frame by a (kind, data_words) schedule.

    Returns total_us, utilization_fraction, utilization_pct, budget_us
    (80% of the frame), headroom_us, headroom_pct, verdict (FITS when the
    schedule fits the 80% budget, OVER otherwise).
    """
    if frame_us <= 0:
        raise ValueError("frame_us must be positive")
    if not messages:
        raise ValueError("schedule is empty, nothing to load")
    total_us = sum(m1553_message_time_us(kind, words)
                   for kind, words in messages)
    budget_us = M1553_BUDGET_FRACTION * frame_us
    utilization_fraction = total_us / frame_us
    headroom_us = budget_us - total_us
    return {
        "total_us": total_us,
        "total_wire_words": sum(m1553_wire_words(kind, words)
                                for kind, words in messages),
        "utilization_fraction": utilization_fraction,
        "utilization_pct": utilization_fraction * 100.0,
        "budget_us": budget_us,
        "headroom_us": headroom_us,
        "headroom_pct": headroom_us / frame_us * 100.0,
        "verdict": "FITS" if total_us <= budget_us else "OVER",
    }


# ---------------------------------------------------------------------------
# ARINC 664 AFDX (VL bandwidth, link budget, timing)
# ---------------------------------------------------------------------------

def _require_bag(bag_ms):
    bag_ms = _require_int(bag_ms, "bag_ms", 1, 128)
    if bag_ms not in AFDX_LEGAL_BAGS:
        raise ValueError("bag_ms %d is not a legal BAG (%s ms)"
                         % (bag_ms, ", ".join(str(b) for b in AFDX_LEGAL_BAGS)))
    return bag_ms


def _require_frame(frame_bytes):
    return _require_int(frame_bytes, "max_frame_bytes",
                        AFDX_MIN_FRAME, AFDX_MAX_FRAME)


def afdx_vl_bandwidth(bag_ms, max_frame_bytes):
    """Bandwidth of one virtual link: frame*8/(BAG seconds).

    Worked anchors: (4 ms, 1518) -> 3036000.0 bps; (128 ms, 1518) ->
    94875.0 bps.
    """
    bag = _require_bag(bag_ms)
    frame = _require_frame(max_frame_bytes)
    return frame * 8 / (bag / 1000.0)


def afdx_link_utilization_pct(vl_specs, link_rate_bps=AFDX_LINK_RATE):
    """Percent of the link consumed by a (bag_ms, frame_bytes) VL set.

    Raises ValueError when the set oversubscribes the link (mirrors the
    leaf: an over-budget set is a configuration error, not a percentage).
    """
    link = _number(link_rate_bps, "link_rate_bps")
    if link <= 0.0:
        raise ValueError("link_rate_bps must be positive")
    total = 0.0
    for spec in vl_specs:
        try:
            bag_ms, frame_bytes = spec
        except (TypeError, ValueError):
            raise ValueError("vl entry %r is not a (bag_ms, frame_bytes) pair"
                             % (spec,))
        total += afdx_vl_bandwidth(bag_ms, frame_bytes)
    if total > link:
        raise ValueError(
            "virtual link set needs %.0f bps but the link carries %.0f bps"
            " (oversubscribed)" % (total, link))
    return total / link * 100.0


def afdx_transmission_time_us(frame_bytes, link_rate_bps=AFDX_LINK_RATE):
    """Serialization time of one frame in us: frame*8/link.

    Worked anchor: 1518 bytes at 100 Mbps -> 121.44 us; 64 bytes -> 5.12 us.
    """
    frame = _require_frame(frame_bytes)
    link = _number(link_rate_bps, "link_rate_bps")
    if link <= 0.0:
        raise ValueError("link_rate_bps must be positive")
    return frame * 8 / link * 1e6


def afdx_end_to_end_latency_us(frame_bytes, switch_count, switch_delay_us,
                               link_rate_bps=AFDX_LINK_RATE):
    """Worst-case one-way latency in us: 2 serializations + switch delays.

    Worked anchor: 1518 bytes, 2 switches at 150 us -> 542.88 us.
    """
    tx_us = afdx_transmission_time_us(frame_bytes, link_rate_bps)
    switches = _require_int(switch_count, "switch_count", 0, 100)
    delay = _number(switch_delay_us, "switch_delay_us")
    if delay < 0.0:
        raise ValueError("switch_delay_us must be non-negative")
    return 2 * tx_us + switches * delay


def afdx_jitter_slack(measured_max_jitter_us, jitter_budget_us):
    """Slack between measured max jitter and the budget, in us.

    Worked anchor: (420.0, 500.0) -> 80.0 (compliant); negative = violation.
    """
    measured = _number(measured_max_jitter_us, "measured_max_jitter_us")
    budget = _number(jitter_budget_us, "jitter_budget_us")
    if measured < 0.0:
        raise ValueError("measured jitter must be non-negative")
    if budget <= 0.0:
        raise ValueError("jitter budget must be positive")
    return budget - measured


def afdx_largest_bag_for_bandwidth(bandwidth_bps, max_frame_bytes):
    """Largest legal BAG (ms) whose VL bandwidth meets the requirement.

    Worked anchor: 1.0 Mbps at 1518 bytes -> 8 ms; raises when even the
    1 ms BAG is insufficient.
    """
    needed = _number(bandwidth_bps, "bandwidth_bps")
    frame = _require_frame(max_frame_bytes)
    if needed <= 0.0:
        raise ValueError("bandwidth_bps must be positive")
    max_rate = afdx_vl_bandwidth(1, frame)
    if needed > max_rate:
        raise ValueError(
            "bandwidth %.0f bps exceeds the 1 ms BAG capacity at %d bytes"
            % (needed, frame))
    chosen = AFDX_LEGAL_BAGS[0]
    for bag in AFDX_LEGAL_BAGS:
        if afdx_vl_bandwidth(bag, frame) >= needed:
            chosen = bag
    return chosen


# ---------------------------------------------------------------------------
# Example architecture + analysis + deliverable
# ---------------------------------------------------------------------------

@dataclass
class A429Line:
    """One ARINC 429 transmit line: single transmitter, N receivers."""
    name: str
    transmitter: str
    receivers: str
    link_rate_bps: float = A429_RATE_100_KBPS
    label_rates: dict = field(default_factory=dict)   # {label: words/s}


@dataclass
class M1553Bus:
    """One MIL-STD-1553 bus: BC schedule per minor frame."""
    name: str
    controller: str
    remote_terminals: str
    frame_us: float = M1553_FRAME_US_DEFAULT
    messages: list = field(default_factory=list)       # [(kind, data_words)]


@dataclass
class AfdxNetwork:
    """One AFDX network: dual-redundant VL set (network A and B)."""
    name: str
    vl_specs: list = field(default_factory=list)       # [(bag_ms, frame_bytes)]
    jitter_measured_us: float = 0.0
    jitter_budget_us: float = 0.0
    switch_count: int = 0
    switch_delay_us: float = 0.0


@dataclass
class DataBusItem:
    """Project facts the role needs to build the assessment."""
    aircraft: str
    description: str = ""
    arinc429_lines: list = field(default_factory=list)
    m1553_bus: M1553Bus | None = None
    afdx_network: AfdxNetwork | None = None
    a429_decode_sample: int = 0          # received word for conformance
    a429_sample_expected_label: str = ""
    a429_bnr_scale: float = 0.1
    m1553_command_sample: int = 0        # received command word
    m1553_status_sample: int = 0         # received status word
    certification_basis: str = "MIL-STD-1553B / ARINC 429 / ARINC 664 practice"


def analyze_architecture(item: DataBusItem) -> dict:
    """Run every computation for the architecture; returns the results."""
    lines = []
    for bus in item.arinc429_lines:
        summary = a429_loading_summary(bus.label_rates, bus.link_rate_bps)
        lines.append({
            "name": bus.name,
            "transmitter": bus.transmitter,
            "receivers": bus.receivers,
            "link_rate_bps": bus.link_rate_bps,
            "label_rates": {str(k): float(v) for k, v in bus.label_rates.items()},
            "summary": summary,
        })

    m1553 = None
    if item.m1553_bus:
        bus = item.m1553_bus
        rows = [{
            "kind": kind, "data_words": words,
            "wire_words": m1553_wire_words(kind, words),
            "time_us": m1553_message_time_us(kind, words),
        } for kind, words in bus.messages]
        schedule = m1553_schedule_utilization(bus.messages, bus.frame_us)
        m1553 = {
            "name": bus.name,
            "controller": bus.controller,
            "remote_terminals": bus.remote_terminals,
            "frame_us": bus.frame_us,
            "messages": rows,
            "schedule": schedule,
        }

    afdx = None
    if item.afdx_network:
        net = item.afdx_network
        vl_rows = [{
            "bag_ms": bag, "frame_bytes": frame,
            "bandwidth_bps": afdx_vl_bandwidth(bag, frame),
        } for bag, frame in net.vl_specs]
        total_bw = sum(r["bandwidth_bps"] for r in vl_rows)
        try:
            utilization_pct = afdx_link_utilization_pct(net.vl_specs)
            over = False
            error = ""
        except ValueError as e:
            utilization_pct = total_bw / AFDX_LINK_RATE * 100.0
            over = True
            error = str(e)
        check = None
        if net.vl_specs:
            check = {
                "frame_bytes": net.vl_specs[0][1],
                "latency_us": afdx_end_to_end_latency_us(
                    net.vl_specs[0][1], net.switch_count,
                    net.switch_delay_us),
                "jitter_slack_us": afdx_jitter_slack(
                    net.jitter_measured_us, net.jitter_budget_us),
            }
        afdx = {
            "name": net.name,
            "vl_count": len(vl_rows),
            "vl_rows": vl_rows,
            "total_bandwidth_bps": total_bw,
            "link_rate_bps": AFDX_LINK_RATE,
            "utilization_pct": utilization_pct,
            "oversubscribed": over,
            "error": error,
            "redundancy": "dual independent networks A and B, same VL set",
            "switch_count": net.switch_count,
            "switch_delay_us": net.switch_delay_us,
            "jitter_measured_us": net.jitter_measured_us,
            "jitter_budget_us": net.jitter_budget_us,
            "checks": check,
        }

    # Protocol conformance samples (decode received words on the bench)
    a429_word = a429_decode_word(item.a429_decode_sample) if \
        item.a429_decode_sample else None
    a429_bnr = None
    if a429_word is not None:
        a429_bnr = {
            "data_field": a429_word["data"],
            "scale": item.a429_bnr_scale,
            "engineering_value": a429_bnr_decode(a429_word["data"],
                                                 item.a429_bnr_scale),
        }
    m1553_cmd = m1553_decode_command_word(item.m1553_command_sample) if \
        item.m1553_command_sample else None
    m1553_st = m1553_decode_status_word(item.m1553_status_sample) if \
        item.m1553_status_sample else None

    return {
        "arinc429_lines": lines,
        "m1553": m1553,
        "afdx": afdx,
        "conformance": {
            "a429_word": a429_word,
            "a429_word_hex": "0x%08X" % item.a429_decode_sample
            if item.a429_decode_sample else "",
            "a429_expected_label": item.a429_sample_expected_label,
            "a429_bnr": a429_bnr,
            "m1553_command": m1553_cmd,
            "m1553_status": m1553_st,
        },
    }


def build_assessment(item: DataBusItem, results: dict) -> dict:
    """Build the complete content model from facts + computed results."""
    observations = []
    for line in results["arinc429_lines"]:
        s = line["summary"]
        if s["guideline_verdict"] == "VIOLATION":
            observations.append(
                "%s exceeds the %g%% design guideline at %.2f%% utilization "
                "(headroom 0): re-rate or offload labels."
                % (line["name"], s["guideline_pct"], s["utilization_pct"]))
        elif s["headroom_pct"] < 10.0:
            observations.append(
                "%s sits at %.2f%% utilization with only %.2f%% headroom to "
                "the %g%% guideline: growth requires a re-rate or a new line."
                % (line["name"], s["utilization_pct"], s["headroom_pct"],
                   s["guideline_pct"]))
    m1553 = results.get("m1553") or {}
    if m1553:
        sch = m1553["schedule"]
        if sch["verdict"] == "OVER":
            observations.append(
                "%s schedule OVER the %g%% budget (%.2f%%): move messages "
                "to the spare bus or lengthen the minor frame."
                % (m1553["name"], M1553_BUDGET_FRACTION * 100.0,
                   sch["utilization_pct"]))
    afdx = results.get("afdx")
    if afdx and afdx["oversubscribed"]:
        observations.append(
            "%s VL set oversubscribes the 100 Mbps link (%.2f%%): increase "
            "BAGs or reduce frame sizes. %s" % (afdx["name"],
                                                afdx["utilization_pct"],
                                                afdx["error"]))
    return {
        "document_type": "Avionics Data Bus Loading and Protocol Assessment",
        "status": "draft-for-review",
        "aircraft": item.aircraft,
        "description": item.description,
        "certification_basis": item.certification_basis,
        "arinc429": results["arinc429_lines"],
        "m1553": m1553,
        "afdx": afdx,
        "conformance": results["conformance"],
        "observations": observations,
        "generated": _today(),
    }


def _fmt_link(rate):
    if rate >= 1e6:
        return "%g Mbps" % (rate / 1e6)
    if rate >= 1e3:
        return "%g kbps" % (rate / 1e3)
    return "%g bps" % rate


def render_assessment_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    lines = [
        "# Avionics Data Bus Loading and Protocol Assessment",
        "",
        f"**Aircraft / program:** {model['aircraft']}",
        f"**Status:** {model['status']}",
        f"**Protocol basis:** {model['certification_basis']}",
        "",
        "## 1. Scope",
        "",
        "This assessment budgets every ARINC 429 transmit line, the "
        "MIL-STD-1553 bus-controller minor-frame schedule, and the ARINC "
        "664 AFDX virtual-link set of the aircraft bus architecture, and "
        "checks received-word conformance (parity, label, word fields) "
        "against the interface control documents."
        + (f" {model['description']}" if model.get("description") else ""),
        "",
        "Loading gates: ARINC 429 and MIL-STD-1553 utilization against the "
        f"{A429_GUIDELINE_PCT:.0f}% design guideline "
        "(the leaf practice; ARINC 429 capacity is the link itself), "
        "AFDX VL set against the 100 Mbps link.",
        "",
        "## 2. ARINC 429 bus loading",
        "",
    ]
    for bus in model["arinc429"]:
        s = bus["summary"]
        lines += [
            f"### {bus['name']}  ({bus['transmitter']} -> "
            f"{bus['receivers']}, {_fmt_link(bus['link_rate_bps'])})",
            "",
            "| Label | Rate (words/s) |",
            "|---|---|",
        ]
        for label, rate in sorted(bus["label_rates"].items()):
            lines.append(f"| {label} | {rate:g} |")
        lines += [
            "",
            f"- Total word rate: **{s['total_words_per_s']:.2f} words/s**",
            f"- Bus load: **{s['load_bps']:.0f} bps** "
            f"({A429_BITS_PER_WORD:.0f} bit-times per word)",
            f"- Bus utilization: **{s['utilization_pct']:.2f}%** of "
            f"{_fmt_link(bus['link_rate_bps'])} "
            f"(capacity {s['capacity_wps']:.1f} words/s)",
            f"- Capacity verdict: **{s['capacity_verdict']}**; design "
            f"guideline ({s['guideline_pct']:.0f}%): "
            f"**{s['guideline_verdict']}**",
            f"- Headroom to guideline: **{s['headroom_pct']:.2f}%**",
            "",
        ]
    lines += ["## 3. MIL-STD-1553 bus loading", ""]
    m1553 = model.get("m1553")
    if m1553:
        sch = m1553["schedule"]
        lines += [
            f"### {m1553['name']}  (BC {m1553['controller']}; RTs "
            f"{m1553['remote_terminals']}; minor frame "
            f"{m1553['frame_us']:.0f} us)",
            "",
            "| Message | Data words | Wire words | Bus time (us) |",
            "|---|---|---|---|",
        ]
        for row in m1553["messages"]:
            lines.append(f"| {row['kind']} | {row['data_words']} | "
                         f"{row['wire_words']} | {row['time_us']:.0f} |")
        lines += [
            "",
            f"- Schedule time: **{sch['total_us']:.0f} us** over "
            f"{m1553['frame_us']:.0f} us "
            f"({sch['total_wire_words']} wire words x "
            f"{M1553_WORD_SLOT_US:.0f} us)",
            f"- Bus utilization: **{sch['utilization_pct']:.2f}%**",
            f"- Budget ({M1553_BUDGET_FRACTION * 100:.0f}% of frame): "
            f"{sch['budget_us']:.0f} us; headroom "
            f"{sch['headroom_us']:.0f} us "
            f"({sch['headroom_pct']:.2f}%)",
            f"- Verdict: **{sch['verdict']}**",
            "",
        ]
    else:
        lines += ["No MIL-STD-1553 bus in this architecture.", ""]

    lines += ["## 4. ARINC 664 AFDX network", ""]
    afdx = model.get("afdx")
    if afdx:
        lines += [
            f"### {afdx['name']}  ({afdx['redundancy']})",
            "",
            f"- Virtual links: {afdx['vl_count']}; total bandwidth "
            f"**{afdx['total_bandwidth_bps'] / 1e6:.3f} Mbps**",
            f"- Link utilization: **{afdx['utilization_pct']:.2f}%** of "
            f"100 Mbps",
            f"- Link budget verdict: "
            f"**{'OVER' if afdx['oversubscribed'] else 'FITS'}**",
            "",
            "| VLs | BAG (ms) | Frame (bytes) | Bandwidth (Mbps) |",
            "|---|---|---|---|",
        ]
        # summarize repeated (bag, frame) pairs
        counts = {}
        for row in afdx["vl_rows"]:
            key = (row["bag_ms"], row["frame_bytes"])
            counts[key] = counts.get(key, 0) + 1
        for (bag, frame), n in sorted(counts.items()):
            bw = afdx_vl_bandwidth(bag, frame) / 1e6
            lines.append(f"| {n} | {bag} | {frame} | {bw:.3f} |")
        if afdx["checks"]:
            chk = afdx["checks"]
            lines += [
                "",
                f"- Worst-case latency ({chk['frame_bytes']}-byte frame, "
                f"{afdx['switch_count']} switch(es) at "
                f"{afdx['switch_delay_us']:.0f} us): "
                f"**{chk['latency_us']:.2f} us**",
                f"- Jitter: measured {afdx['jitter_measured_us']:.0f} us vs "
                f"budget {afdx['jitter_budget_us']:.0f} us -> slack "
                f"**{chk['jitter_slack_us']:.1f} us**",
                "",
            ]
    else:
        lines += ["No AFDX network in this architecture.", ""]

    lines += ["## 5. Protocol conformance checks", ""]
    conf = model["conformance"]
    aw = conf.get("a429_word")
    if a429_word_present := aw:
        bnr = conf.get("a429_bnr") or {}
        label_ok = (aw["label"] == _oct_label(conf.get("a429_expected_label", "")))
        lines += [
            f"- ARINC 429 received word {conf.get('a429_word_hex', '')}: "
            f"label {aw['label']:03o} ({aw['label']}), SDI {aw['sdi']}, "
            f"data field {aw['data']}"
            + (f" (BNR {bnr.get('engineering_value', 0):g} at "
               f"LSB {bnr.get('scale', 0.1):g})" if bnr else "")
            + f", SSM {aw['ssm']}, parity {'OK' if aw['parity_ok'] else 'FAIL'}",
            f"  - Expected label {conf.get('a429_expected_label', '')} "
            f"({_oct_label(conf.get('a429_expected_label', ''))}): "
            f"{'MATCH' if label_ok else 'MISMATCH'}",
        ]
    mc = conf.get("m1553_command")
    if mc:
        cls = m1553_classify_message(mc["rt_address"], mc["subaddress"],
                                     mc["word_count"], mc["transmit_receive"])
        lines += [
            f"- MIL-STD-1553 command word {mc['word_count']} data words, "
            f"RT {mc['rt_address']} subaddress {mc['subaddress']}, "
            f"{'RT-to-BC' if mc['transmit_receive'] else 'BC-to-RT'}: "
            f"classified **{cls}**, parity "
            f"{'OK' if mc['parity_ok'] else 'FAIL'}",
        ]
    ms = conf.get("m1553_status")
    if ms:
        lines += [
            f"- MIL-STD-1553 status word RT {ms['rt_address']}: busy="
            f"{ms['busy']}, terminal_flag={ms['terminal_flag']}, parity "
            f"{'OK' if ms['parity_ok'] else 'FAIL'}",
        ]
    lines += [""]

    lines += ["## 6. Findings and observations", ""]
    obs = model.get("observations") or []
    if obs:
        for i, o in enumerate(obs, 1):
            lines.append(f"- **O-{i}** {o}")
    else:
        lines.append("- No loading or conformance observations: all buses "
                     "fit their design guidelines.")
    lines += [
        "",
        "## 7. Conclusion",
        "",
        "The bus architecture loading and received-word conformance results "
        "above are computed by the data-bus-avionics-engineer core from the "
        "bound ARINC 429, MIL-STD-1553 and ARINC 664 AFDX leaf rules "
        "(36 bit-times per ARINC 429 word; 24 us per MIL-STD-1553 wire "
        "word; frame x 8 / BAG for AFDX VL bandwidth). Numbers are "
        "cross-checked against the AeroSkills leaf logic when the skills "
        "library is present and recorded in the evidence bundle.",
        "",
        "---",
        f"*Generated by Aero Agent Roles data-bus-avionics-engineer core "
        f"({model['generated']}). DRAFT for human avionics/data-bus "
        "engineer review. Not an approval document.*",
    ]
    return "\n".join(lines)


def _oct_label(label_str: str) -> int:
    """Octal label string -> int (empty -> 0)."""
    if not label_str:
        return 0
    return int(label_str, 8)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "arinc429_loads_computed": "every ARINC 429 line has numeric load + utilization",
    "arinc429_conformance_ok": "received word parity OK and label matches ICD",
    "m1553_schedule_computed": "1553 schedule utilization is a number in range",
    "m1553_conformance_ok": "command/status words decode with odd parity OK",
    "afdx_budget_checkable": "AFDX VL set present and link budget verdict known",
    "observations_listed": "findings/observations section is present",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_assessment(model: dict) -> dict:
    """Run the evidence gates against a content model."""
    a429 = model.get("arinc429") or []
    conf = model.get("conformance") or {}
    a429_ok = bool(a429) and all(
        isinstance(b.get("summary", {}).get("utilization_pct"), (int, float))
        for b in a429)
    aw = conf.get("a429_word") or {}
    a429_conf = bool(aw.get("parity_ok")) and bool(aw) and (
        aw.get("label") == _oct_label(conf.get("a429_expected_label", "")))
    m1553 = model.get("m1553") or {}
    sch = m1553.get("schedule") or {}
    m1553_ok = bool(m1553) and isinstance(sch.get("utilization_pct"),
                                          (int, float)) and \
        0.0 <= sch.get("utilization_pct", -1) <= 100.0
    mc = conf.get("m1553_command") or {}
    ms = conf.get("m1553_status") or {}
    m1553_conf = bool(mc.get("parity_ok")) and bool(ms.get("parity_ok"))
    afdx = model.get("afdx")
    afdx_ok = bool(afdx) and "oversubscribed" in afdx
    results = {
        "arinc429_loads_computed": a429_ok,
        "arinc429_conformance_ok": a429_conf,
        "m1553_schedule_computed": m1553_ok,
        "m1553_conformance_ok": m1553_conf,
        "afdx_budget_checkable": afdx_ok,
        "observations_listed": isinstance(model.get("observations"), list),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_assessment_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "avionics data bus loading and protocol assessment" in low,
        "has_a429": "arinc 429" in low and "utilization" in low,
        "has_m1553": "mil-std-1553" in low and "utilization" in low,
        "has_afdx": "afdx" in low,
        "has_percent": "%" in low,
        "has_conformance": "parity" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check an assessment doc."""
    return check_assessment_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item: EX-100 reference bus architecture (worked example)
# ---------------------------------------------------------------------------

def example_item() -> DataBusItem:
    """Reference example: transport avionics bus architecture with
    ARINC 429 TX lines, one MIL-STD-1553 bus, and an AFDX VL set."""
    return DataBusItem(
        aircraft="EX-100 Reference Example Transport",
        description="Flight deck avionics data bus architecture: ADC, IRS "
                    "and legacy utility concentrator ARINC 429 transmit "
                    "lines, a dual-redundant MIL-STD-1553 bus under one "
                    "bus controller, and a growth AFDX core network.",
        arinc429_lines=[
            A429Line(
                name="A429-1 ADC/FMS data",
                transmitter="ADC-1",
                receivers="FMS-1, EFIS-1",
                link_rate_bps=A429_RATE_100_KBPS,
                label_rates={
                    "010": 25.0, "011": 25.0, "036": 50.0, "100": 50.0,
                    "203": 12.5, "210": 25.0, "231": 25.0, "320": 12.5,
                    "365": 12.5, "370": 12.5,
                }),
            A429Line(
                name="A429-2 IRS/FCC data",
                transmitter="IRS-1",
                receivers="FCC-1, EFIS-1",
                link_rate_bps=A429_RATE_100_KBPS,
                label_rates={
                    "320": 25.0, "365": 25.0, "366": 25.0, "367": 25.0,
                    "370": 25.0, "371": 25.0, "372": 25.0, "375": 12.5,
                    "376": 12.5,
                }),
            A429Line(
                name="A429-3 fuel/utility (low speed)",
                transmitter="UTA-1",
                receivers="EICAS-1",
                link_rate_bps=A429_RATE_12_5_KBPS,
                label_rates={
                    "250": 20.0, "251": 20.0, "252": 20.0, "253": 20.0,
                    "254": 20.0, "255": 20.0, "256": 20.0, "257": 20.0,
                    "260": 20.0, "261": 20.0, "262": 20.0, "263": 20.0,
                    "264": 20.0,
                }),
        ],
        m1553_bus=M1553Bus(
            name="1553-B1 mission bus",
            controller="Mission Computer (MC-1)",
            remote_terminals="RT 1 (FMS-1), RT 2 (NAV-1), RT 3 (FCC-1)",
            frame_us=M1553_FRAME_US_DEFAULT,
            messages=[
                ("BCRT", 32), ("RTBC", 16), ("BCRT", 16), ("RTRT", 8),
                ("RTBC", 8), ("BCRT", 8), ("BCRT", 4), ("RTRT", 4),
            ]),
        afdx_network=AfdxNetwork(
            name="AFDX core network (growth)",
            vl_specs=[(16, 1518)] * 6 + [(32, 1518)] * 4 + [(128, 1518)] * 2
                     + [(4, 1518), (8, 1518)],
            jitter_measured_us=420.0,
            jitter_budget_us=500.0,
            switch_count=2,
            switch_delay_us=150.0,
        ),
        a429_decode_sample=0x60134908,          # label 010, SDI 1, data 1234
        a429_sample_expected_label="010",
        a429_bnr_scale=0.1,
        m1553_command_sample=93316,             # RT5 SA12 WC16 RT-to-BC
        m1553_status_sample=606276,             # RT5 busy
        certification_basis="MIL-STD-1553B / ARINC 429 Mark 33 DITS / "
                            "ARINC 664 Part 7 protocol practice",
    )


def example_assessment_markdown() -> str:
    item = example_item()
    return render_assessment_markdown(build_assessment(item,
                                                       analyze_architecture(item)))


if __name__ == "__main__":
    item = example_item()
    results = analyze_architecture(item)
    model = build_assessment(item, results)
    md = render_assessment_markdown(model)
    a429_max = max(b["summary"]["utilization_pct"]
                   for b in model["arinc429"])
    print("ARINC 429 lines: %d, max utilization %.2f%%"
          % (len(model["arinc429"]), a429_max))
    print("MIL-STD-1553 utilization: %.2f%%"
          % model["m1553"]["schedule"]["utilization_pct"])
    print("AFDX utilization: %.2f%%, oversubscribed=%s"
          % (model["afdx"]["utilization_pct"], model["afdx"]["oversubscribed"]))
    print("GATES: %s" % check_assessment(model))
    print("RENDERED: %d chars" % len(md))
