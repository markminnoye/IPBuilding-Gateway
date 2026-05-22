#!/usr/bin/env python3
"""Fix corrupted device list JSON from IPBuilding relay/dimmer."""

import json, sys

def fix_channels(channels):
    """Apply the same corrections as fix_device_list but inside a channels array."""
    CORRECTIONS = {
        2:  "Achterdeur Licht [30.1.4]",
        9:  "Badkamer ventilatie [30.2.2]",
        11: "Slaapkamer achteraan [30.2.4]",
        13: "Slaapkamer vooraan [30.2.6]",
        17: "Keuken Kookeiland [30.3.2]",
        18: "Keuken rookmelder [30.3.3]",
        19: "Speelkamer Boven LED [30.3.4]",
        20: "Speelkamer Boven [30.3.5]",
        23: "Keuken Ventilatie [30.3.8]",
    }
    fixed = []
    for ch in channels:
        d = dict(ch)
        if d["id"] in CORRECTIONS:
            d["descr"] = CORRECTIONS[d["id"]]
        fixed.append(d)
    return fixed

def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    if "channels" in data:
        data["channels"] = fix_channels(data["channels"])
    else:
        raise ValueError("No 'channels' key found in JSON")

    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
