#!/usr/bin/env python3
"""Test relay ON via IPBox REST API (已有的 working manier)."""

import asyncio
import aiohttp
import sys

sys.path.insert(0, "/Users/markminnoye/git/IPBuilding Gateway")
from gateway.payloads.relay import decode_relay_payload

INKOM_ID = 557  # Inkom [30.2.3] — relay kanaal 10
IPBOX = "http://192.168.0.185:30200"

async def main():
    async with aiohttp.ClientSession() as sess:
        # Check huidige status
        async with sess.get(f"{IPBOX}/api/v1/comp/items") as resp:
            items = await resp.json()
            inkom = next((i for i in items if i["ID"] == INKOM_ID), None)
            if inkom:
                print(f"Inkom: {inkom['Description']} (channel={inkom['Output']})")

        # Stuur ON
        print(f"\n→ INKOM AAN (via IPBox REST)...")
        async with sess.get(f"{IPBOX}/api/v1/action/action?id={INKOM_ID}&actionType=ON&value=1") as resp:
            print(f"HTTP {resp.status}")
            text = await resp.text()
            print(f"Response: {text!r}")

        await asyncio.sleep(3)

        # Stuur UIT
        print(f"\n→ INKOM UIT...")
        async with sess.get(f"{IPBOX}/api/v1/action/action?id={INKOM_ID}&actionType=OFF&value=0") as resp:
            print(f"HTTP {resp.status}")
            text = await resp.text()
            print(f"Response: {text!r}")

if __name__ == "__main__":
    asyncio.run(main())