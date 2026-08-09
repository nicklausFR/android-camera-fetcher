# Android Camera Fetcher

Windows system-tray application for downloading the photos and videos in an
Android phone's `DCIM/Camera` folder through ADB, over USB or Wi-Fi.

## Main Features

- Detect an ADB-connected Android phone regularly from the system tray.
- Prefer USB automatically when both USB and Wi-Fi are available.
- Show a Windows notification when a phone becomes available and let the user start the synchronization manually.
- Synchronize all camera photos and videos to a configurable local folder.
- Start a one-off download to a folder selected in Windows Explorer, for all media, one date, or a date range.
- Choose photos, videos, or both for one-off downloads.
- Select a specific ADB device or connection type, and inspect the ADB diagnostic output in the options.
- Resume a stopped transfer: already complete local files are skipped.
- English interface by default, with French available in `Options`.

## Requirements

- Windows 10 or later.
- Android Platform Tools, with `adb` available in `PATH`.
- USB debugging or Wireless debugging enabled on the Android phone.

For Python development, install Python 3.11+ and the required packages:

```powershell
pip install PySide6 pywin32 pyinstaller
```

## Run from Source

```powershell
python main.py
```

Choose the synchronization folder, ADB transport, selected device, polling
interval, and language through the tray icon menu: `Options…`.

### One-off synchronization

Use the tray icon menu: `One-off download…`. Select all media, a date, or a
period, then choose the destination folder after clicking `Download`.

## Build the Executable

```powershell
python build_exe.py
```

The build script asks for the destination folder of `AndroidCameraFetcher.exe`.
It compiles the translations and packages them in the executable. Its last
selected build destination is saved locally in `build_exe_config.json`.

## Local Settings

Application settings are stored per Windows user through Qt settings:

- synchronization folder;
- phone presence-check interval;
- ADB transport and selected device;
- interface language.

No photo, video, or phone content is sent to an online service. Transfers use
the local ADB connection only.

## Translations

The interface uses standard Gettext catalogs:

- template: `locales/android-camera-fetcher.pot`;
- English: `locales/en/LC_MESSAGES/android-camera-fetcher.po`;
- French: `locales/fr/LC_MESSAGES/android-camera-fetcher.po`.

After editing a `.po` file, run:

```powershell
python tools/compile_translations.py
```

## License

Copyright (C) 2026 nicklausFR

GPL-3.0-or-later.
