================================================================================
  IPBuilding — Legacy centrale import (dry-run test)
================================================================================

This zip contains a small standalone Python script. It reads component names
and channel mapping from your legacy IPBuilding central (IP0000) mobile UI
and writes a local JSON file. Nothing is sent to or changed on the gateway.

Contents:
  - import_from_legacy_central.py   (the script)
  - README.txt                      (this file)

Requirements:
  - Python 3.9 or newer (3.11+ recommended)
  - Your computer must reach the legacy central at 10.10.1.1 on the
    IPBuilding field network (VLAN 10.10.1.x).
    Typical setups: run from the Home Assistant host, a PC on that VLAN, or
    a machine with VPN/route to 10.10.1.1.
    Running from a random home laptop on 192.168.x.x usually will NOT work
    unless you have network access to 10.10.1.1.

================================================================================
  WINDOWS
================================================================================

1) Install Python (if not already installed)
   - Download from https://www.python.org/downloads/
   - During setup, check "Add python.exe to PATH"
   - Open Command Prompt (cmd) or PowerShell and verify:
       python --version
     or:
       py --version

2) Unzip this folder
   - Right-click the zip -> Extract All...
   - Open the extracted folder, e.g.:
       C:\Users\You\Downloads\legacy-central-import\

3) Test network access to the central
   In Command Prompt or PowerShell:
       curl "http://10.10.1.1/mobile/core/actions.php?methode=searchItems&searchStr="
   You should see HTML text (not "connection refused" or timeout).

4) Run the import script
   cd C:\Users\You\Downloads\legacy-central-import
   python import_from_legacy_central.py

   Or with explicit options:
       python import_from_legacy_central.py --central-host 10.10.1.1 --output devices.import.json

   Save raw HTML if something goes wrong:
       python import_from_legacy_central.py --save-html legacy_raw.html

5) Check the result
   - Open devices.import.json in Notepad or VS Code
   - Compare module IPs, channel numbers, and names with the mobile UI at:
       http://10.10.1.1/mobile/

6) Send back to the project team
   - devices.import.json (required)
   - legacy_raw.html (if parsing failed or names look wrong)
   - A screenshot of the mobile UI showing 2-3 components you compared
   - Copy/paste of the script output from the terminal

================================================================================
  macOS
================================================================================

1) Check Python
   Open Terminal (Applications -> Utilities -> Terminal):
       python3 --version
   macOS usually has python3 pre-installed. If missing, install from
   https://www.python.org/downloads/ or via Homebrew:
       brew install python

2) Unzip this folder
   Double-click the zip file, or in Terminal:
       cd ~/Downloads
       unzip legacy-central-import.zip
       cd legacy-central-import

3) Test network access
       curl "http://10.10.1.1/mobile/core/actions.php?methode=searchItems&searchStr="
   Expect HTML output.

4) Run the import script
       python3 import_from_legacy_central.py

   With options:
       python3 import_from_legacy_central.py --central-host 10.10.1.1 --output devices.import.json

   Save HTML for troubleshooting:
       python3 import_from_legacy_central.py --save-html legacy_raw.html

5) Quick summary in Terminal
       python3 -c "
import json
d=json.load(open('devices.import.json'))
for m in d['modules']:
    print(m['ip'], m['type'], len(m['channels']), 'channels')
    for c in m['channels'][:3]:
        print('  ch', c['ch'], c['name'], '-', c['room'])
"

6) Send back to the project team (same as Windows step 6)

================================================================================
  COMMAND-LINE OPTIONS
================================================================================

  --central-host IP     Central unit address (default: 10.10.1.1)
  --output FILE         Output JSON path (default: devices.import.json)
  --group NAME          Import one menu group only (exact name from mobile UI)
  --search TEXT         Filter searchItems (default: empty = all items)
  --save-html FILE      Save raw HTML response for debugging

Examples:
  python3 import_from_legacy_central.py --group Verlichting
  python3 import_from_legacy_central.py --search keuken

================================================================================
  WHAT TO EXPECT IN THE JSON
================================================================================

  - "ip" and "ch" per channel (e.g. 10.10.1.32 channel 0 = address ...-00)
  - "name" and "room" from the central (URL-encoded names are decoded)
  - "type": relay or dimmer
  - "mac": empty (normal — filled later by gateway discovery)
  - "active": false (normal — enabled later in Home Assistant)

================================================================================
  TROUBLESHOOTING
================================================================================

  ERROR: cannot reach legacy central
    -> No route to 10.10.1.1. Run the script from a machine on the field VLAN.

  ERROR: no modules parsed from central HTML
    -> Re-run with --save-html legacy_raw.html and send that file back.

  Wrong or missing channel names
    -> Send devices.import.json + legacy_raw.html + mobile UI screenshot.

================================================================================
  IMPORTANT
================================================================================

  This is a READ-ONLY test. The script does not modify the central, the
  gateway, or Home Assistant. It only creates a local JSON file for review.

================================================================================
