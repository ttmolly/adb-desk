#!/usr/bin/env python3
"""adb-desk: admin desk for an Android phone you own.

Talks to a handset only after USB debugging is on and the Allow prompt
on that phone has been accepted. No hidden payload, no license key.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

APP = "adb-desk"
LOG_PATH = Path.home() / ".local" / "share" / "adb-desk" / "connections.log"

DANGEROUS = {
    "android.permission.READ_SMS",
    "android.permission.SEND_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.READ_CONTACTS",
    "android.permission.WRITE_CONTACTS",
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.CAMERA",
    "android.permission.RECORD_AUDIO",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_PHONE_STATE",
    "android.permission.CALL_PHONE",
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.REQUEST_INSTALL_PACKAGES",
}

BACKUP_DIRS = (
    "/sdcard/DCIM/Camera",
    "/sdcard/Pictures",
    "/sdcard/Download",
    "/sdcard/Documents",
)


class AdbError(RuntimeError):
    pass


def run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AdbError(f"missing command: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"timed out: {' '.join(cmd)}") from exc


def require_adb() -> None:
    if shutil.which("adb") is None:
        raise AdbError(
            "adb is not installed. On Ubuntu: sudo apt install android-tools-adb"
        )


def adb(serial: str | None, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return run(cmd, timeout=timeout)


def list_devices() -> list[tuple[str, str]]:
    result = adb(None, "devices", "-l")
    if result.returncode != 0:
        raise AdbError(result.stderr.strip() or "adb devices failed")
    found: list[tuple[str, str]] = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        serial, state = parts[0], parts[1] if len(parts) > 1 else "unknown"
        found.append((serial, state))
    return found


def pick_device(serial: str | None) -> str:
    devices = list_devices()
    ready = [item for item in devices if item[1] == "device"]
    if serial:
        match = [item for item in devices if item[0] == serial]
        if not match:
            raise AdbError(f"no device with serial {serial}")
        if match[0][1] != "device":
            raise AdbError(
                f"{serial} is {match[0][1]}. Unlock the phone and tap Allow on the debugging prompt."
            )
        return serial
    if not devices:
        raise AdbError(
            "no phone found. Plug it in, turn on USB debugging, and tap Allow."
        )
    if not ready:
        states = ", ".join(f"{s} ({st})" for s, st in devices)
        raise AdbError(f"phone is connected but not allowed yet: {states}")
    if len(ready) == 1:
        return ready[0][0]
    print("More than one allowed phone:")
    for index, (item, _state) in enumerate(ready, 1):
        print(f"  {index}. {item}")
    choice = input("Pick a number: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(ready):
        raise AdbError("bad selection")
    return ready[int(choice) - 1][0]


def prop(serial: str, name: str) -> str:
    result = adb(serial, "shell", "getprop", name, timeout=20)
    return result.stdout.strip() or "-"


def shell_out(serial: str, *args: str, timeout: int = 30) -> str:
    result = adb(serial, "shell", *args, timeout=timeout)
    if result.returncode != 0 and not result.stdout.strip():
        raise AdbError(result.stderr.strip() or "shell command failed")
    return result.stdout.strip()


def log_seen(serial: str, action: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp}  {serial}  {action}\n")


def cmd_check(_args: argparse.Namespace) -> int:
    require_adb()
    devices = list_devices()
    if not devices:
        print("no phone found")
        return 1
    for serial, state in devices:
        mark = "ok" if state == "device" else state
        print(f"{serial}  {mark}")
    return 0 if any(state == "device" for _s, state in devices) else 1


def cmd_info(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    log_seen(serial, "info")
    rows = [
        ("serial", serial),
        ("model", prop(serial, "ro.product.model")),
        ("brand", prop(serial, "ro.product.brand")),
        ("android", prop(serial, "ro.build.version.release")),
        ("sdk", prop(serial, "ro.build.version.sdk")),
        ("patch", prop(serial, "ro.build.version.security_patch")),
        ("encryption", prop(serial, "ro.crypto.state")),
        ("build", prop(serial, "ro.build.display.id")),
    ]
    battery = shell_out(serial, "dumpsys", "battery")
    level = next((line.split(":", 1)[1].strip() for line in battery.splitlines() if "level:" in line), "-")
    rows.append(("battery", f"{level}%"))
    width = max(len(label) for label, _value in rows)
    print(f"adb-desk  {serial}")
    print("-" * (width + 24))
    for label, value in rows:
        print(f"{label.ljust(width)}  {value}")
    return 0


def cmd_storage(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    log_seen(serial, "storage")
    print(shell_out(serial, "df", "-h", "/sdcard", timeout=20))
    return 0


def cmd_packages(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    log_seen(serial, "packages")
    raw = shell_out(serial, "pm", "list", "packages", "-3", timeout=40)
    names = sorted(line.split(":", 1)[1] for line in raw.splitlines() if line.startswith("package:"))
    if args.user_only is False:
        raw = shell_out(serial, "pm", "list", "packages", timeout=40)
        names = sorted(line.split(":", 1)[1] for line in raw.splitlines() if line.startswith("package:"))
    print(f"{len(names)} packages")
    for name in names:
        print(name)
    return 0


def cmd_perms(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    log_seen(serial, "perms")
    raw = shell_out(serial, "pm", "list", "packages", "-3", timeout=40)
    names = sorted(line.split(":", 1)[1] for line in raw.splitlines() if line.startswith("package:"))
    hits = 0
    for name in names:
        dump = shell_out(serial, "dumpsys", "package", name, timeout=25)
        granted = sorted(perm for perm in DANGEROUS if f"{perm}: granted=true" in dump)
        if not granted:
            continue
        hits += 1
        print(name)
        for perm in granted:
            print(f"  {perm.rsplit('.', 1)[-1]}")
    if hits == 0:
        print("no third-party package reported a granted dangerous permission")
    else:
        print(f"\n{hits} packages")
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    out = Path(args.out) if args.out else Path(f"shot-{dt.datetime.now():%Y%m%d-%H%M%S}.png")
    remote = "/sdcard/adb-desk-shot.png"
    log_seen(serial, f"shot {out}")
    shot = adb(serial, "shell", "screencap", "-p", remote, timeout=30)
    if shot.returncode != 0:
        raise AdbError(shot.stderr.strip() or "screencap failed")
    pulled = adb(serial, "pull", remote, str(out), timeout=30)
    adb(serial, "shell", "rm", "-f", remote, timeout=15)
    if pulled.returncode != 0:
        raise AdbError(pulled.stderr.strip() or "pull failed")
    print(out.resolve())
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    seconds = max(1, min(args.seconds, 180))
    out = Path(args.out) if args.out else Path(f"rec-{dt.datetime.now():%Y%m%d-%H%M%S}.mp4")
    remote = "/sdcard/adb-desk-rec.mp4"
    log_seen(serial, f"record {seconds}s {out}")
    print(f"recording {seconds}s")
    recorded = adb(
        serial,
        "shell",
        "screenrecord",
        "--time-limit",
        str(seconds),
        remote,
        timeout=seconds + 30,
    )
    if recorded.returncode != 0:
        raise AdbError(recorded.stderr.strip() or "screenrecord failed")
    pulled = adb(serial, "pull", remote, str(out), timeout=60)
    adb(serial, "shell", "rm", "-f", remote, timeout=15)
    if pulled.returncode != 0:
        raise AdbError(pulled.stderr.strip() or "pull failed")
    print(out.resolve())
    return 0


def cmd_mirror(args: argparse.Namespace) -> int:
    require_adb()
    if shutil.which("scrcpy") is None:
        raise AdbError("scrcpy is not installed. On Ubuntu: sudo apt install scrcpy")
    serial = pick_device(args.serial)
    log_seen(serial, "mirror")
    result = subprocess.run(["scrcpy", "-s", serial], check=False)
    return result.returncode


def cmd_install(args: argparse.Namespace) -> int:
    require_adb()
    apk = Path(args.apk)
    if not apk.is_file():
        raise AdbError(f"not a file: {apk}")
    serial = pick_device(args.serial)
    log_seen(serial, f"install {apk.name}")
    result = adb(serial, "install", "-r", str(apk), timeout=180)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def cmd_uninstall(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    if not args.yes:
        answer = input(f"Uninstall {args.package} from {serial}? [y/N] ").strip().lower()
        if answer != "y":
            print("cancelled")
            return 1
    log_seen(serial, f"uninstall {args.package}")
    result = adb(serial, "uninstall", args.package, timeout=60)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def cmd_pull(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    log_seen(serial, f"pull {args.remote}")
    result = adb(serial, "pull", args.remote, str(dest), timeout=300)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def cmd_push(args: argparse.Namespace) -> int:
    require_adb()
    local = Path(args.local)
    if not local.exists():
        raise AdbError(f"not found: {local}")
    serial = pick_device(args.serial)
    log_seen(serial, f"push {local.name}")
    result = adb(serial, "push", str(local), args.remote, timeout=300)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def cmd_backup(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path(args.dest) / stamp
    root.mkdir(parents=True, exist_ok=True)
    log_seen(serial, f"backup {root}")
    copied = 0
    for remote in BACKUP_DIRS:
        probe = adb(serial, "shell", "ls", "-d", remote, timeout=20)
        if probe.returncode != 0:
            print(f"skip {remote}")
            continue
        folder = root / remote.strip("/").replace("/", "_")
        folder.mkdir(parents=True, exist_ok=True)
        print(f"pull {remote}")
        result = adb(serial, "pull", remote, str(folder), timeout=600)
        if result.returncode == 0:
            copied += 1
        else:
            print(result.stderr.strip() or f"failed {remote}")
    print(root.resolve())
    print(f"{copied} folders")
    return 0 if copied else 1


def cmd_reboot(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    if not args.yes:
        answer = input(f"Reboot {serial}? [y/N] ").strip().lower()
        if answer != "y":
            print("cancelled")
            return 1
    log_seen(serial, "reboot")
    result = adb(serial, "reboot", timeout=20)
    return result.returncode


def cmd_wifi(args: argparse.Namespace) -> int:
    require_adb()
    serial = pick_device(args.serial)
    log_seen(serial, f"wifi {args.ip}")
    switched = adb(serial, "tcpip", "5555", timeout=20)
    if switched.returncode != 0:
        raise AdbError(switched.stderr.strip() or "could not switch to tcpip")
    connected = adb(None, "connect", f"{args.ip}:5555", timeout=20)
    sys.stdout.write(connected.stdout)
    sys.stderr.write(connected.stderr)
    print("USB had to be allowed first. Unplug only after this says connected.")
    return connected.returncode


def cmd_log(_args: argparse.Namespace) -> int:
    if not LOG_PATH.exists():
        print(f"no log yet at {LOG_PATH}")
        return 0
    print(LOG_PATH)
    print(LOG_PATH.read_text(encoding="utf-8").rstrip())
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    actions = {
        "1": ("check", cmd_check),
        "2": ("info", cmd_info),
        "3": ("storage", cmd_storage),
        "4": ("packages", cmd_packages),
        "5": ("perms", cmd_perms),
        "6": ("shot", cmd_shot),
        "7": ("mirror", cmd_mirror),
        "8": ("backup", cmd_backup),
        "9": ("log", cmd_log),
        "q": ("quit", None),
    }
    while True:
        print("\nadb-desk")
        print("  1 check     2 info      3 storage")
        print("  4 packages  5 perms     6 screenshot")
        print("  7 mirror    8 backup    9 log")
        print("  q quit")
        choice = input("> ").strip().lower()
        if choice in {"q", "quit", "0"}:
            return 0
        item = actions.get(choice)
        if item is None:
            print("unknown option")
            continue
        _name, func = item
        try:
            func(args)
        except AdbError as exc:
            print(f"error: {exc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adb-desk",
        description="Admin desk for an Android phone you own. USB debugging must already be allowed.",
    )
    parser.add_argument("--serial", "-s", help="device serial from adb devices")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="list phones and exit")
    sub.add_parser("info", help="model, Android version, patch, battery")
    sub.add_parser("storage", help="show /sdcard free space")

    packages = sub.add_parser("packages", help="list installed packages")
    packages.add_argument("--all", dest="user_only", action="store_false", help="include system packages")
    packages.set_defaults(user_only=True)

    sub.add_parser("perms", help="dangerous permissions granted to your apps")

    shot = sub.add_parser("shot", help="save a screenshot")
    shot.add_argument("--out", help="output png path")

    record = sub.add_parser("record", help="record the screen, max 180s")
    record.add_argument("--seconds", type=int, default=15)
    record.add_argument("--out", help="output mp4 path")

    sub.add_parser("mirror", help="open scrcpy")

    install = sub.add_parser("install", help="install an apk onto the allowed phone")
    install.add_argument("apk")

    uninstall = sub.add_parser("uninstall", help="uninstall a package")
    uninstall.add_argument("package")
    uninstall.add_argument("--yes", action="store_true")

    pull = sub.add_parser("pull", help="copy a file from the phone")
    pull.add_argument("remote")
    pull.add_argument("dest")

    push = sub.add_parser("push", help="copy a file to the phone")
    push.add_argument("local")
    push.add_argument("remote")

    backup = sub.add_parser("backup", help="pull Camera, Pictures, Download, Documents")
    backup.add_argument("--dest", default="backups")

    reboot = sub.add_parser("reboot", help="reboot the phone")
    reboot.add_argument("--yes", action="store_true")

    wifi = sub.add_parser("wifi", help="switch an already-allowed phone to ADB over Wi-Fi")
    wifi.add_argument("ip", help="phone IP, for example 192.168.1.20")

    sub.add_parser("log", help="show the local connection log")
    sub.add_parser("menu", help="small text menu")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "menu"
        args.out = None
        args.seconds = 15
        args.dest = "backups"
        args.user_only = True
    handlers = {
        "check": cmd_check,
        "info": cmd_info,
        "storage": cmd_storage,
        "packages": cmd_packages,
        "perms": cmd_perms,
        "shot": cmd_shot,
        "record": cmd_record,
        "mirror": cmd_mirror,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "pull": cmd_pull,
        "push": cmd_push,
        "backup": cmd_backup,
        "reboot": cmd_reboot,
        "wifi": cmd_wifi,
        "log": cmd_log,
        "menu": cmd_menu,
    }
    try:
        return handlers[args.command](args)
    except AdbError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ncancelled")
        return 130


if __name__ == "__main__":
    sys.exit(main())
