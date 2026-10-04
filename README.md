# adb-desk

Admin desk for an Android phone you own. It talks to the handset through ADB after USB debugging is on and the Allow prompt on that phone has been tapped.

This is not a remote-access tool. A locked phone, or a phone that never accepted debugging, will not connect. iPhones are not supported.

## Install

Ubuntu / Debian:

```bash
sudo apt install android-tools-adb
# optional, for screen mirror
sudo apt install scrcpy
git clone https://github.com/ttmolly/adb-desk.git
cd adb-desk
python3 adb_desk.py check
```

No pip packages. Python 3.9 or newer.

## Use

Plug the phone in, enable Developer options, turn on USB debugging, and tap Allow.

```bash
python3 adb_desk.py check
python3 adb_desk.py info
python3 adb_desk.py storage
python3 adb_desk.py packages
python3 adb_desk.py perms
python3 adb_desk.py shot
python3 adb_desk.py record --seconds 15
python3 adb_desk.py mirror
python3 adb_desk.py backup
python3 adb_desk.py install ./app.apk
python3 adb_desk.py pull /sdcard/Download/notes.txt ./notes.txt
python3 adb_desk.py wifi 192.168.1.20
python3 adb_desk.py log
python3 adb_desk.py
```

`wifi` still needs a USB allow first. It only switches a phone you already authorized over to port 5555.

`backup` copies Camera, Pictures, Download, and Documents into `backups/<date>/`.

Commands that change the phone (`uninstall`, `reboot`) ask before they run. Pass `--yes` to skip the question.

If more than one allowed phone is plugged in, pass `--serial` with the value from `adb devices`.

The connection log is local only: `~/.local/share/adb-desk/connections.log`.

## What it will not do

- No license key and no encrypted blob.
- No SMS dump, call-log dump, or send-SMS action.
- No iOS support.
- No Bluetooth path. Android does not expose this kind of control over BLE.

Use it only on a device you own or have permission to admin.
