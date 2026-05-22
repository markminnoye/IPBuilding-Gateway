#!/usr/bin/env python3
"""Write tests/fixtures/minimal_udp1001_session/ for correlate_capture_session dry runs."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path


def ip_checksum(header: bytes) -> int:
    assert len(header) % 2 == 0
    s = sum(struct.unpack(f"!{len(header)//2}H", header))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def build_udp_frame(src_ip: bytes, dst_ip: bytes, sport: int, dport: int, payload: bytes) -> bytes:
    udp_len = 8 + len(payload)
    total_len = 20 + udp_len
    ver_ihl_tos = struct.pack("!BBH", 0x45, 0, total_len)
    ident_flags = struct.pack("!HH", 0x1234, 0)
    hdr_wo = ver_ihl_tos + ident_flags + struct.pack("!BBH", 64, 17, 0) + src_ip + dst_ip
    csum = ip_checksum(hdr_wo)
    ip_hdr = ver_ihl_tos + ident_flags + struct.pack("!BBH", 64, 17, csum) + src_ip + dst_ip
    udp_body = struct.pack("!HHHH", sport, dport, udp_len, 0) + payload
    return ip_hdr + udp_body


def eth_wrap(ip_payload: bytes) -> bytes:
    eth = bytes.fromhex("0200000000000011223344550800") + ip_payload
    pad = 60 - len(eth)
    if pad > 0:
        eth += b"\x00" * pad
    return eth


def pcap_packet(ts_sec: int, ts_usec: int, data: bytes) -> bytes:
    return struct.pack("<IIII", ts_sec, ts_usec, len(data), len(data)) + data


def write_pcap(path: Path, frames: list[bytes]) -> None:
    global_hdr = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    buf = bytearray(global_hdr)
    for i, fr in enumerate(frames):
        buf.extend(pcap_packet(i, 0, fr))
    path.write_bytes(buf)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    session = repo / "tests" / "fixtures" / "minimal_udp1001_session"
    session.mkdir(parents=True, exist_ok=True)
    pcap_legacy = session / "_tmp.pcap"
    pcapng = session / "capture.pcapng"

    src = bytes([10, 10, 1, 1])
    dst = bytes([10, 10, 1, 30])
    pl = b"TEST"
    f1 = eth_wrap(build_udp_frame(src, dst, 50446, 1001, pl))
    f2 = eth_wrap(build_udp_frame(dst, src, 1001, 50446, pl))
    write_pcap(pcap_legacy, [f1, f2])

    try:
        subprocess.run(
            ["editcap", "-F", "pcapng", str(pcap_legacy), str(pcapng)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print("editcap failed; install Wireshark CLI tools.", exc, file=sys.stderr)
        return 1
    finally:
        pcap_legacy.unlink(missing_ok=True)

    manifest = session / "manifest.jsonl"
    line = {
        "event": "rest_action",
        "step_id": "fixture",
        "t_utc": "2026-05-15T00:00:00+00:00",
        "url": "http://192.168.0.185:30200/api/v1/fixture",
    }
    manifest.write_text(json.dumps(line) + "\n", encoding="utf-8")
    print(f"Wrote {pcapng} and {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
