# PE Builder

**Windows PE 定制工具** — 一键制作自己的 PE 启动盘，无需任何外部依赖。

[![Gitee](https://img.shields.io/badge/Gitee-源码-blue)](https://gitee.com/eric_Coding/pe-builder)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows_10/11-blue)]()
[![Arch](https://img.shields.io/badge/Arch-x64%20%7C%20x86-lightgrey)]()

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| 🚀 **即开即用** | 单文件 exe，无需安装任何依赖 |
| 🪟 **自带 PE 源** | 自动从系统 WinRE 提取，无需下载 ISO |
| 🧰 **内置工具** | DiskGenius · Dism++ · WinNTSetup · PE-Browser |
| 🌐 **一键网络** | 启用网络自动附带浏览器 + 网卡驱动 |
| 🚫 **免 ADK** | 纯 Python ISO 生成器，无需 6GB ADK |
| 📦 **轻量输出** | ISO < 2GB |
| 🎨 **深度定制** | 组件 · 驱动 · 壁纸 · 主题 · 注册表 |

---

## 📥 下载

| 版本 | 下载 | 大小 |
|------|------|------|
| **x64** | [PE-Builder-v1.0.zip](https://gitee.com/eric_Coding/pe-builder/releases) | 42MB |
| **x86** | PE-Builder-v1.0-x86.zip | 23MB |

---

## 🔧 快速开始

### 第一步：运行

双击 `PE-Builder.exe`，即开即用。

### 第二步：选择 PE 源

- **推荐**：源文件 → **使用系统 WinRE** — 自动提取当前系统
- 或手动选择 ISO / WIM

### 第三步：配置

| 面板 | 说明 |
|------|------|
| **项目设置** | 架构、语言、压缩、临时目录、页面文件 |
| **源文件** | 使用系统 WinRE 或选择外部 ISO/WIM |
| **工具管理** | 内置 4 工具（DiskGenius/Dism++/WinNTSetup/PE-Browser），可添加更多 |
| **桌面定制** | 壁纸、主题色、字体、桌面图标 |
| **驱动注入** | 存储 / 网卡 / WiFi / USB 驱动预设，一键从本机提取 |
| **注册表优化** | 16 项优化预设（显示、性能、安全等） |

### 第四步：构建 ISO

切到 **构建 ISO** 面板 → 点击 **开始构建**

输出 ISO 文件，可直接用于制作 PE 启动 U 盘。

---

## 📋 内置工具

| 工具 | 用途 | 路径 |
|------|------|------|
| **DiskGenius** | 磁盘分区与数据恢复 | `%ProgramFiles%\PBTools\` |
| **Dism++** | 系统优化与部署 | `%ProgramFiles%\PBTools\` |
| **WinNTSetup** | Windows 安装器 | `%ProgramFiles%\PBTools\` |
| **PE-Browser** | 简易网页浏览器 | `%ProgramFiles%\PBTools\` |

> 勾选「启用网络支持」自动添加 PE-Browser 和网卡驱动。

---

## 🏗️ 构建选项

| 选项 | 说明 |
|------|------|
| **架构** | x64 / x86 / ARM64 |
| **PE 语言** | 简体中文 / 繁体中文 / English / 日本語 |
| **压缩方式** | 最大 / 快速 / 不压缩 |
| **临时目录** | PE 运行时临时目录（默认 X:\Temp） |
| **页面文件** | 页面文件大小（MB） |
| **网络支持** | 自动附带浏览器 + 网卡驱动 |
| **从本机提取驱动** | 扫描已安装驱动，筛选存储/网络/USB |

---

## 🔄 驱动预设

| 类别 | 驱动 |
|------|------|
| **存储** | Intel VMD (RST) / NVMe / SATA AHCI / AMD RAID |
| **网卡** | Realtek PCIe / Intel PRO/1000 / Broadcom NetXtreme |
| **WiFi** | Intel AX201 / Realtek 8821CE / Broadcom BCM4360 |
| **USB** | xHCI / Intel USB 3.0 可扩展主机 |

---

## 🖥️ 系统要求

| 要求 | 说明 |
|------|------|
| **系统** | Windows 10/11 (x64 / x86) |
| **内存** | 2GB+ |
| **磁盘** | 500MB 可用空间 |
| **权限** | 构建时需要管理员权限（DISM 操作） |
| **ADK** | 可选 — 不装 ADK 也能构建 |

---

## 📦 文件结构

```
PE-Builder/
├── PE-Builder.exe              # 主程序
├── electron/
│   ├── main.py                 # Python 后端
│   ├── index.html              # 前端界面
│   ├── iso_builder.py          # ISO 生成器
│   └── mini_browser.py         # 简易浏览器源码
├── tools/
│   ├── PE-Browser.exe          # 便携浏览器 (x64)
│   └── PE-Browser-x86.exe      # 便携浏览器 (x86)
├── build-all.bat               # 多架构构建脚本
├── LICENSE                     # MIT 许可
└── README.md                   # 本文件
```

---

## 🛠️ 自行构建

需要 Python 3.12+ 和 pip：

```bash
# 安装依赖
pip install pywebview pyinstaller pycdlib

# 构建
pyinstaller --onefile --windowed ^
  --add-data "electron/index.html;." ^
  --add-data "electron/iso_builder.py;." ^
  --add-data "tools/PE-Browser.exe;tools/" ^
  --hidden-import pycdlib ^
  --name "PE-Builder" ^
  electron/main.py
```

或运行 `build-all.bat` 选择目标架构。

---

## 📜 许可

[MIT License](LICENSE)

Copyright © 2026 Eric

---

## 🔗 链接

- [项目主页](https://7d5d5d8c390d44569ba99611fab964f5.app.codebuddy.work)
- [Gitee 仓库](https://gitee.com/eric_Coding/pe-builder)
- [GitHub 镜像](https://github.com/eric_Coding/pe-builder)
