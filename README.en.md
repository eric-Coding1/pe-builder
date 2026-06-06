# PE Builder

**Custom Windows PE Builder** — Build your own bootable PE ISO in one click. Zero external dependencies.

[![Gitee](https://img.shields.io/badge/Gitee-Source_Code-blue)](https://gitee.com/eric_Coding/pe-builder)
[![GitHub](https://img.shields.io/badge/GitHub-Mirror-black)](https://github.com/eric_Coding/pe-builder)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows_10/11-blue)]()
[![Arch](https://img.shields.io/badge/Arch-x64%20%7C%20x86-lightgrey)]()

---

## ✨ Features

| Feature | Description |
|---------|------------|
| 🚀 **Portable** | Single-file exe, no installation or dependencies needed |
| 🪟 **Built-in PE Source** | Auto-extracts WinRE from your system — no ISO download required |
| 🧰 **Bundled Tools** | DiskGenius · Dism++ · WinNTSetup · PE-Browser |
| 🌐 **One-Click Network** | Toggle networking — auto-adds browser + NIC drivers |
| 🚫 **No ADK Required** | Pure Python ISO generator — no need for the 6GB ADK suite |
| 📦 **Lightweight Output** | ISO < 2GB |
| 🎨 **Deep Customization** | Components · Drivers · Wallpaper · Theme · Registry |

---

## 📥 Downloads

| Arch | Package | Size |
|------|---------|------|
| **x64** | [PE-Builder-v1.0.zip](https://gitee.com/eric_Coding/pe-builder/releases/download/v1.0/PE-Builder-v1.0.zip) | 42MB |
| **x86** | [PE-Builder-v1.0-x86.zip](https://gitee.com/eric_Coding/pe-builder/releases/download/v1.0/PE-Builder-v1.0-x86.zip) | 23MB |

---

## 🔧 Quick Start

### Step 1: Run

Double-click `PE-Builder.exe`. No installation needed.

### Step 2: Choose PE Source

- **Recommended**: Source panel → **Use System WinRE** — auto-extracts from your running Windows
- Or manually select an ISO / WIM file

### Step 3: Configure

| Panel | Description |
|-------|------------|
| **Project Settings** | Architecture, language, compression, temp dir, pagefile |
| **Source** | Use system WinRE or load external ISO/WIM |
| **Tools** | 4 built-in tools (DiskGenius/Dism++/WinNTSetup/PE-Browser), add more |
| **Desktop** | Wallpaper, accent color, fonts, desktop icons |
| **Drivers** | Storage / Network / WiFi / USB presets, one-click extract from host |
| **Registry** | 16 optimization presets (display, performance, security, etc.) |

### Step 4: Build ISO

Switch to the **Build ISO** panel → Click **Start Build**

The output ISO can be used directly for creating a bootable PE USB drive.

---

## 📋 Bundled Tools

| Tool | Purpose | Location |
|------|---------|----------|
| **DiskGenius** | Disk partition & data recovery | `%ProgramFiles%\PBTools\` |
| **Dism++** | System optimization & deployment | `%ProgramFiles%\PBTools\` |
| **WinNTSetup** | Windows installer | `%ProgramFiles%\PBTools\` |
| **PE-Browser** | Lightweight web browser | `%ProgramFiles%\PBTools\` |

> Toggle **Enable Network** to auto-add PE-Browser and NIC drivers.

---

## 🏗️ Build Options

| Option | Description |
|--------|-------------|
| **Architecture** | x64 / x86 / ARM64 |
| **PE Language** | zh-CN / zh-TW / en-US / ja-JP |
| **Compression** | Max / Fast / None |
| **Temp Directory** | PE runtime temp directory (default: X:\Temp) |
| **Pagefile** | Page file size (MB) |
| **Network Support** | Auto-includes browser + NIC drivers |
| **Extract Drivers** | Scan host for installed drivers, filter storage/network/USB |

---

## 🔄 Driver Presets

| Category | Drivers |
|----------|---------|
| **Storage** | Intel VMD (RST) / NVMe / SATA AHCI / AMD RAID |
| **NIC** | Realtek PCIe / Intel PRO/1000 / Broadcom NetXtreme |
| **WiFi** | Intel AX201 / Realtek 8821CE / Broadcom BCM4360 |
| **USB** | xHCI / Intel USB 3.0 eXtensible Host |

---

## 🖥️ System Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10/11 (x64 / x86) |
| **RAM** | 2GB+ |
| **Disk** | 500MB free space |
| **Permissions** | Administrator rights required for building (DISM operations) |
| **ADK** | Optional — builds work without ADK |

---

## 📦 Project Structure

```
PE-Builder/
├── PE-Builder.exe              # Main executable
├── electron/
│   ├── main.py                 # Python backend
│   ├── index.html              # Frontend UI
│   ├── iso_builder.py          # ISO builder engine
│   └── mini_browser.py         # Mini browser source
├── tools/
│   ├── PE-Browser.exe          # Portable browser (x64)
│   └── PE-Browser-x86.exe      # Portable browser (x86)
├── build-all.bat               # Multi-arch build script
├── LICENSE                     # MIT License
├── README.md                   # Documentation (Chinese)
└── README.en.md                # This file
```

---

## 🛠️ Building from Source

Requires Python 3.12+ and pip:

```bash
# Install dependencies
pip install pywebview pyinstaller pycdlib

# Build
pyinstaller --onefile --windowed ^
  --add-data "electron/index.html;." ^
  --add-data "electron/iso_builder.py;." ^
  --add-data "tools/PE-Browser.exe;tools/" ^
  --hidden-import pycdlib ^
  --name "PE-Builder" ^
  electron/main.py
```

Or run `build-all.bat` to pick a target architecture interactively.

---

## 📜 License

[MIT License](LICENSE)

Copyright © 2026 Eric

---

## 🔗 Links

- [Project Site](https://7d5d5d8c390d44569ba99611fab964f5.app.codebuddy.work)
- [Gitee Repository](https://gitee.com/eric_Coding/pe-builder)
- [GitHub Mirror](https://github.com/eric_Coding/pe-builder)
