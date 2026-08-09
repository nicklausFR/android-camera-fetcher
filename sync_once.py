"""Copie ponctuelle de DCIM/Camera vers le PC via ADB USB ou Wi-Fi."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import adb_client
import camera_files


DEFAULT_DESTINATION = Path(r"D:\Pictures\Photos\Smartphone")


def target_path(destination: Path, item: camera_files.CameraFile) -> Path:
    target = destination / item.filename
    if not target.exists() or target.stat().st_size == item.size:
        return target
    return destination / f"{item.media_date:%Y%m%d}_{item.filename}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    connection = parser.add_mutually_exclusive_group()
    connection.add_argument("--usb", action="store_const", const="usb", dest="mode")
    connection.add_argument("--wifi", action="store_const", const="wifi", dest="mode")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    mode = args.mode or "auto"  # Auto privilégie l'USB.

    device = adb_client.select_device(mode)
    print(f"Téléphone : {device.model} via {device.connection_type}")
    media = adb_client.query_camera_files(
        device.serial,
        camera_files.PHONE_ROOT,
        date(2000, 1, 1),
        date.today(),
        newest_first=False,
    )
    files = camera_files.build_camera_files(media)
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=True)
    print(f"{len(files)} média(s) vers {destination}")

    copied = skipped = errors = 0
    for index, item in enumerate(files, start=1):
        target = target_path(destination, item)
        if target.exists() and target.stat().st_size == item.size:
            skipped += 1
        else:
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                if temporary.exists():
                    temporary.unlink()
                adb_client.pull_file(device.serial, item.remote_path, temporary)
                temporary.replace(target)
                copied += 1
            except Exception as error:
                errors += 1
                if temporary.exists():
                    temporary.unlink()
                print(f"Erreur : {item.filename} — {error}")
        print(f"[{index}/{len(files)}] {item.filename}")

    print(f"Terminé : {copied} copié(s), {skipped} déjà présent(s), {errors} erreur(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
