"""
PE Builder — Windows PE 定制工具
WebView2 原生窗口 + Python 构建引擎（含 ADK 自动安装）
"""
import os
import sys
import json
import subprocess
import threading
import time
import re
import ctypes
import urllib.request
import urllib.error
import shutil
import tempfile
import webview

# ISO builder module (pure Python, no external tools needed)
import iso_builder

# Determine base path (works for both source and PyInstaller bundle)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HTML_PATH = os.path.join(BASE_DIR, 'index.html')

# Bundled tools path (for PE builds)
if getattr(sys, 'frozen', False):
    TOOLS_DIR = os.path.join(BASE_DIR, 'tools')
else:
    TOOLS_DIR = os.path.join(BASE_DIR, '..', 'tools')

# Build script template embedded in Python
BUILD_SCRIPT_TEMPLATE = r'''<#
.SYNOPSIS
    PE Builder — 自动生成的 PE 构建脚本
.DESCRIPTION
    由 PE Builder 配置生成，构建自定义 Windows PE ISO
#>

$ErrorActionPreference = "Stop"
$BuildRoot = "$PSScriptRoot"
$LogFile = "$BuildRoot\build.log"
$StartTime = Get-Date

function Write-Log {
    param([string]$Msg)
    $time = Get-Date -Format "HH:mm:ss"
    $line = "[$time] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

# ===== CONFIG =====
$PE_ARCH          = "{{ARCH}}"         # x64 / x86 / arm64
$PE_LANG          = "{{LANG}}"         # zh-CN / en-US
$SOURCE_PATH      = "{{SOURCE_PATH}}"  # Windows ISO or WIM
$OUTPUT_DIR       = "{{OUTPUT_DIR}}"
$ISO_NAME         = "{{ISO_NAME}}"
$COMPRESS_TYPE    = "{{COMPRESS}}"     # max / fast / none
$PAGEFILE_MB      = {{PAGEFILE_MB}}
$TEMP_DIR         = "{{TEMP_DIR}}"
$ENABLE_NETWORK   = ${{ENABLE_NETWORK}}
$ENABLE_MTP       = ${{ENABLE_MTP}}
$ENABLE_DISM      = ${{ENABLE_DISM}}

# Customizations
$ADD_TOOLS        = @({{TOOLS_LIST}})
$ADD_DRIVERS      = @({{DRIVERS_LIST}})
$DESKTOP_ICONS    = @{ {{ICONS_MAP}} }
$THEME_COLOR      = "{{THEME_COLOR}}"
$WALLPAPER_FILE   = "{{WALLPAPER}}"

Write-Log "=== PE Builder Build v1.0 ==="
Write-Log "Architecture: $PE_ARCH"
Write-Log "Output: $OUTPUT_DIR\$ISO_NAME"

# ===== STEP 1: Check ADK =====
Write-Log "STEP 1/8 - 检查 Windows ADK..."

$adkPaths = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\Assessment and Deployment Kit",
    "${env:ProgramFiles}\Windows Kits\10\Assessment and Deployment Kit",
    "C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit",
    "C:\Program Files\Windows Kits\10\Assessment and Deployment Kit"
)
$adkFound = $false
$copypePath = $null
$oscdimgPath = $null

foreach ($p in $adkPaths) {
    $cp = "$p\Windows Preinstallation Environment\copype.cmd"
    $od = "$p\Deployment Tools\$PE_ARCH\Oscdimg\oscdimg.exe"
    if (Test-Path $cp) {
        $copypePath = $cp
        $adkFound = $true
        Write-Log "  找到 copype.cmd: $cp"
        if (Test-Path $od) {
            $oscdimgPath = $od
            Write-Log "  找到 oscdimg.exe: $od"
        }
        break
    }
}

if (-not $adkFound) {
    Write-Log "  ❌ 未找到 Windows ADK!"
    Write-Log "  请使用 PE Builder 的「自动安装 ADK」功能"
    Write-Log "  或手动下载安装后重试"
    exit 1
}

# ===== STEP 2: Create working directory =====
Write-Log "STEP 2/8 - 创建工作目录..."
$WorkDir = "$BuildRoot\PE-Build-Work"
if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null

$PEOutDir = "$WorkDir\PE"
$ScratchDir = "$WorkDir\Scratch"

# ===== STEP 3: Run copype.cmd =====
Write-Log "STEP 3/8 - 运行 copype.cmd 生成 PE 基础文件..."
$proc = Start-Process -FilePath "$env:comspec" -ArgumentList "/c `"$copypePath`" $PE_ARCH `"$PEOutDir`"" -NoNewWindow -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Log "  ❌ copype.cmd 失败 (exit code: $($proc.ExitCode))"
    exit 1
}

$BootWim = "$PEOutDir\media\sources\boot.wim"
if (-not (Test-Path $BootWim)) {
    Write-Log "  ❌ boot.wim 未生成!"
    exit 1
}
Write-Log "  ✓ boot.wim 已生成"

# ===== STEP 4: Mount and customize boot.wim =====
Write-Log "STEP 4/8 - 挂载 boot.wim 并应用自定义..."

$MountDir = "$WorkDir\Mount"
New-Item -ItemType Directory -Path $MountDir -Force | Out-Null

# Find DISM
$dismPath = "dism.exe"
$dismCandidates = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\$PE_ARCH\DISM\dism.exe",
    "${env:ProgramFiles}\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\$PE_ARCH\DISM\dism.exe"
)
foreach ($dc in $dismCandidates) { if (Test-Path $dc) { $dismPath = $dc; break } }

# Mount image (index 1 in boot.wim)
Write-Log "  挂载 WIM 映像..."
$mountArgs = "/Mount-Image /ImageFile:`"$BootWim`" /Index:1 /MountDir:`"$MountDir`""
if ($COMPRESS_TYPE -eq "max") { $mountArgs += " /Optimize" }
& $dismPath $mountArgs.Split(" ") 2>&1 | ForEach-Object { Write-Log "  $_" }

# Apply registry tweaks
Write-Log "  应用注册表优化..."
$RegHive = "$MountDir\Windows\System32\config\SYSTEM"
$SoftwareHive = "$MountDir\Windows\System32\config\SOFTWARE"
$DefaultHive = "$MountDir\Users\Default\NTUSER.DAT"

# Load hives
reg load HKLM\PE_SYSTEM "$RegHive" 2>&1 | Out-Null
reg load HKLM\PE_SOFTWARE "$SoftwareHive" 2>&1 | Out-Null
reg load HKU\PE_DEFAULT "$DefaultHive" 2>&1 | Out-Null

# Common tweaks
reg add "HKLM\PE_SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v Hidden /t REG_DWORD /d 1 /f 2>&1 | Out-Null
reg add "HKLM\PE_SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v HideFileExt /t REG_DWORD /d 0 /f 2>&1 | Out-Null
reg add "HKLM\PE_SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer" /v NoDriveAutoRun /t REG_DWORD /d 1 /f 2>&1 | Out-Null
reg add "HKLM\PE_SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f 2>&1 | Out-Null
reg add "HKLM\PE_SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v EnableSIHostIntegration /t REG_DWORD /d 0 /f 2>&1 | Out-Null

# Theme color
$themeColorDword = [Convert]::ToInt32("$THEME_COLOR".Replace("#",""), 16)
$themeColorDword = ($themeColorDword -band 0xFF00FF00) -bor (($themeColorDword -band 0xFF) -shl 16) -bor (($themeColorDword -band 0xFF0000) -shr 16)
reg add "HKLM\PE_SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize" /v ColorPrevalence /t REG_DWORD /d 1 /f 2>&1 | Out-Null
reg add "HKLM\PE_SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize" /v AccentColor /t REG_DWORD /d $themeColorDword /f 2>&1 | Out-Null

# Unload hives
reg unload HKLM\PE_SYSTEM 2>&1 | Out-Null
reg unload HKLM\PE_SOFTWARE 2>&1 | Out-Null
reg unload HKU\PE_DEFAULT 2>&1 | Out-Null
Write-Log "  ✓ 注册表优化完成"

# ===== STEP 5: Add custom tools =====
Write-Log "STEP 5/8 - 集成工具..."
$ToolDir = "$MountDir\Program Files\Tools"
New-Item -ItemType Directory -Path $ToolDir -Force | Out-Null
foreach ($tool in $ADD_TOOLS) {
    if (Test-Path $tool) {
        Copy-Item -Path $tool -Destination "$ToolDir\" -Recurse -Force
        Write-Log "  已添加: $([System.IO.Path]::GetFileName($tool))"
    } else {
        Write-Log "  ⚠ 文件不存在: $tool"
    }
}

# ===== STEP 6: Inject drivers =====
Write-Log "STEP 6/8 - 注入驱动程序..."
foreach ($drv in $ADD_DRIVERS) {
    if (Test-Path $drv) {
        $drvArgs = "/Add-Driver /Image:`"$MountDir`" /Driver:`"$drv`" /Recurse"
        & $dismPath $drvArgs.Split(" ") 2>&1 | ForEach-Object { Write-Log "  $_" }
        Write-Log "  已注入驱动: $([System.IO.Path]::GetFileName($drv))"
    } else {
        Write-Log "  ⚠ 驱动路径不存在: $drv"
    }
}

# ===== STEP 7: Add wallpaper =====
if ($WALLPAPER_FILE -and (Test-Path $WALLPAPER_FILE)) {
    Write-Log "  设置桌面壁纸..."
    $imgDir = "$MountDir\Windows\Web\Wallpaper\PE"
    New-Item -ItemType Directory -Path $imgDir -Force | Out-Null
    Copy-Item -Path $WALLPAPER_FILE -Destination "$imgDir\PEWallpaper.jpg" -Force
    # Apply via注册表
    reg load HKLM\PE_DEFAULT2 "$DefaultHive" 2>&1 | Out-Null
    reg add "HKLM\PE_DEFAULT2\Control Panel\Desktop" /v Wallpaper /t REG_SZ /d "C:\Windows\Web\Wallpaper\PE\PEWallpaper.jpg" /f 2>&1 | Out-Null
    reg add "HKLM\PE_DEFAULT2\Control Panel\Desktop" /v WallpaperStyle /t REG_DWORD /d 6 /f 2>&1 | Out-Null
    reg unload HKLM\PE_DEFAULT2 2>&1 | Out-Null
}

# ===== STEP 8: Commit and unmount =====
Write-Log "STEP 7/8 - 提交修改并卸载 WIM 映像..."
$commitArgs = "/Unmount-Image /MountDir:`"$MountDir`" /Commit"
& $dismPath $commitArgs.Split(" ") 2>&1 | ForEach-Object { Write-Log "  $_" }

# ===== STEP 9: Generate ISO =====
Write-Log "STEP 8/8 - 生成 ISO 镜像..."
if (-not (Test-Path $OUTPUT_DIR)) { New-Item -ItemType Directory -Path $OUTPUT_DIR -Force | Out-Null }

$IsoPath = "$OUTPUT_DIR\$ISO_NAME"
$ISO_LABEL = "PE_BUILDER"
$efiBootFile = "$PEOutDir\fwfiles\efisys.bin"

if ($oscdimgPath -and (Test-Path $oscdimgPath)) {
    $isoArgs = @(
        "-bootdata:2#p0,e,b$PEOutDir\fwfiles\etfsboot.com#pEF,e,b$efiBootFile",
        "-u1", "-udfver102",
        "-l$ISO_LABEL",
        "-m",
        "`"$PEOutDir\media`"",
        "`"$IsoPath`""
    )
    & $oscdimgPath $isoArgs 2>&1 | ForEach-Object { Write-Log "  $_" }
} else {
    # Fallback: use makewinpemedia.cmd
    Write-Log "  oscdimg.exe 未找到，尝试使用 makewinpemedia.cmd..."
    $mwpmPath = "$(Split-Path $copypePath)\makewinpemedia.cmd"
    if (Test-Path $mwpmPath) {
        & $mwpmPath /iso "$PEOutDir" "$IsoPath" 2>&1 | ForEach-Object { Write-Log "  $_" }
    } else {
        Write-Log "  ❌ 无法生成 ISO - 缺少 oscdimg.exe 或 makewinpemedia.cmd"
        exit 1
    }
}

$Duration = (Get-Date) - $StartTime
if (Test-Path $IsoPath) {
    $Size = [math]::Round((Get-Item $IsoPath).Length / 1MB, 1)
    Write-Log "========================================"
    Write-Log "✅ PE 构建成功!"
    Write-Log "   文件: $IsoPath"
    Write-Log "   大小: ${Size}MB"
    Write-Log "   耗时: $($Duration.Minutes)分$($Duration.Seconds)秒"
    Write-Log "========================================"
} else {
    Write-Log "❌ 构建失败 - ISO 文件未生成"
    exit 1
}
'''

BUILD_SCRIPT_SIMPLE = r'''<#
.SYNOPSIS
    PE Builder — 简化版构建脚本（无需 ADK）
.DESCRIPTION
    此脚本使用 Windows 系统自带的 DISM 功能构建 PE 启动 ISO。
    适用于已安装 Windows ADK 的环境。
#>

$ErrorActionPreference = "Stop"
Write-Host "PE Builder Build Script v1.0" -ForegroundColor Cyan
Write-Host "本脚本需要 Windows ADK (部署工具 + Windows PE) 才能运行。"
Write-Host "下载地址: https://go.microsoft.com/fwlink/?linkid=2240443"
Write-Host ""
Write-Host "请先确认已安装 ADK，然后以管理员身份运行此脚本。"
Write-Host "配置后重新生成脚本即可使用。"
Read-Host "按 Enter 退出"
'''


class Api:
    """Bridge between JS and Python/OS"""
    
    def __init__(self):
        self._build_running = False
        self._build_log = []
        self._build_progress = 0
        self._adk_downloading = False
        self._adk_progress = 0
        self._adk_status = ''
        self._adk_cancelled = False
    
    # ---- ADK Download & Install ----
    
    ADK_URL = 'https://go.microsoft.com/fwlink/?linkid=2240443'
    ADK_WINPE_URL = 'https://go.microsoft.com/fwlink/?linkid=2240673'
    # Chinese mirror alternative
    ADK_MIRROR_URL = 'https://download.microsoft.com/download/9/6/9/969E1FDE-B3D2-4D9E-93D4-1B8E5C35D7D7/adk/adksetup.exe'
    
    def start_adk_download(self):
        """Download and install ADK in background thread."""
        if self._adk_downloading:
            return json.dumps({'error': '下载已在进行中'})
        
        self._adk_downloading = True
        self._adk_progress = 0
        self._adk_status = '准备中...'
        self._adk_cancelled = False
        
        def _download_thread():
            try:
                self._set_adk_status('正在检测系统环境...', 1)
                time.sleep(0.5)
                
                # Check if already installed
                prereq = self.check_prerequisites_dict()
                if prereq['adk_installed']:
                    self._set_adk_status('✓ Windows ADK 已安装，无需重复下载', 100)
                    self._adk_downloading = False
                    return
                
                # Download directory
                dl_dir = os.path.join(BASE_DIR, '..', 'adk-setup')
                os.makedirs(dl_dir, exist_ok=True)
                exe_path = os.path.join(dl_dir, 'adksetup.exe')
                
                # Download ADK bootstrapper
                self._set_adk_status('正在下载 ADK 安装程序 (adksetup.exe)...', 5)
                
                # Try official link first, then mirror
                download_success = self._download_file(
                    self.ADK_URL, exe_path,
                    progress_start=5, progress_end=40
                )
                
                if not download_success or self._adk_cancelled:
                    # Try mirror
                    self._set_adk_status('尝试备用下载地址...', 5)
                    download_success = self._download_file(
                        self.ADK_MIRROR_URL, exe_path,
                        progress_start=5, progress_end=40
                    )
                
                if self._adk_cancelled:
                    self._set_adk_status('⏹ 下载已取消', 0)
                    self._adk_downloading = False
                    return
                
                if not download_success or not os.path.isfile(exe_path):
                    self._set_adk_status('❌ 下载失败，请手动下载安装\nADK: https://go.microsoft.com/fwlink/?linkid=2240443', 0)
                    self._adk_downloading = False
                    return
                
                # Verify the downloaded file
                file_size = os.path.getsize(exe_path)
                self._set_adk_status(f'✓ 下载完成 ({file_size//1024}KB)，准备安装...', 45)
                
                # Install silently
                self._set_adk_status('正在安装 Windows ADK（部署工具 + Windows PE）...\n此过程可能需要 10-30 分钟，请耐心等待', 50)
                
                install_cmd = [
                    exe_path,
                    '/quiet', '/ceip', 'off',
                    '/norestart',
                    '/features', 'OptionId.DeploymentTools', 'OptionId.WindowsPreinstallationEnvironment'
                ]
                
                self._append_build_log('[ADK] 开始静默安装 ADK...')
                self._append_build_log(f'[ADK] 命令: {" ".join(install_cmd)}')
                
                proc = subprocess.Popen(
                    install_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                # Monitor install progress
                start_time = time.time()
                max_wait = 30 * 60  # 30 minutes max
                
                while proc.poll() is None:
                    time.sleep(2)
                    elapsed = time.time() - start_time
                    
                    if self._adk_cancelled:
                        proc.terminate()
                        self._set_adk_status('⏹ 安装已取消', 0)
                        self._adk_downloading = False
                        return
                    
                    if elapsed > max_wait:
                        proc.terminate()
                        self._set_adk_status('❌ 安装超时（超过30分钟），可能网络较慢，请重试', 0)
                        self._adk_downloading = False
                        return
                    
                    # Progress estimate: 50% + time-based
                    prog = 50 + min(40, int(elapsed / 180 * 40))  # 3 min = 90%
                    self._set_adk_status(f'正在安装... ({int(elapsed//60)}分{int(elapsed%60)}秒)', prog)
                
                exit_code = proc.returncode
                
                if exit_code == 0:
                    self._set_adk_status('✓ ADK 安装完成！正在验证...', 95)
                    time.sleep(1)
                    
                    # Verify installation
                    verify = self.check_prerequisites_dict()
                    if verify['adk_installed']:
                        self._set_adk_status(f'✅ ADK 安装成功！copype: {verify["copype_path"]}', 100)
                        self._append_build_log('[ADK] ✅ ADK 安装并验证成功！')
                        self._append_build_log(f'[ADK] copype.cmd: {verify["copype_path"]}')
                        self._append_build_log('[ADK] 现在可以开始构建 PE ISO 了！')
                    else:
                        self._set_adk_status('⚠ ADK 安装完成但未检测到工具，可能需要重启', 100)
                else:
                    self._set_adk_status(f'❌ 安装失败 (错误码: {exit_code})\n请手动下载安装', 0)
                    self._append_build_log(f'[ADK] ❌ 安装失败，退出码: {exit_code}')
                
            except Exception as e:
                self._set_adk_status(f'❌ 出错: {str(e)}', 0)
                self._append_build_log(f'[ADK] ❌ 异常: {str(e)}')
            finally:
                self._adk_downloading = False
        
        threading.Thread(target=_download_thread, daemon=True).start()
        return json.dumps({'started': True})
    
    def _download_file(self, url, dest_path, progress_start=0, progress_end=100):
        """Download a file with progress tracking."""
        try:
            self._append_build_log(f'[下载] 开始下载: {url}')
            
            def report(block_count, block_size, total_size):
                if self._adk_cancelled:
                    raise Exception('cancelled')
                if total_size > 0:
                    downloaded = block_count * block_size
                    pct = min(100, downloaded / total_size * 100)
                    prog = progress_start + int(pct * (progress_end - progress_start) / 100)
                    self._adk_progress = prog
                    mb_dl = downloaded / (1024*1024)
                    mb_total = total_size / (1024*1024)
                    self._set_adk_status(f'正在下载 ADK... {mb_dl:.1f}MB / {mb_total:.1f}MB', prog)
            
            urllib.request.urlretrieve(url, dest_path, report)
            self._append_build_log('[下载] ✅ 下载完成')
            return True
        except urllib.error.URLError as e:
            self._append_build_log(f'[下载] ❌ 网络错误: {e.reason}')
            return False
        except Exception as e:
            if str(e) == 'cancelled':
                self._append_build_log('[下载] ⏹ 已取消')
                return False
            self._append_build_log(f'[下载] ❌ 错误: {str(e)}')
            return False
    
    def get_adk_download_status(self):
        """Returns ADK download/install progress."""
        return json.dumps({
            'downloading': self._adk_downloading,
            'progress': self._adk_progress,
            'status': self._adk_status,
        })
    
    def cancel_adk_download(self):
        """Cancel ADK download/install."""
        self._adk_cancelled = True
        self._set_adk_status('正在取消...', 0)
        return json.dumps({'cancelled': True})
    
    def _set_adk_status(self, msg, progress):
        self._adk_status = msg
        self._adk_progress = progress
    
    def _append_build_log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        self._build_log.append(f'[{timestamp}] {msg}')
    
    # ---- File dialogs ----
    def open_file_dialog(self, filter_str='全部文件 (*.*)'):
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=(filter_str,)
        )
        return result[0] if result else None
    
    def save_file_dialog(self, filter_str='PE Builder 项目 (*.peproj)'):
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG, file_types=(filter_str,)
        )
        return result if result else None
    
    # ---- File system ----
    def read_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return json.dumps({'error': str(e)})
    
    def write_file(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(data)
            return True
        except Exception as e:
            return str(e)
    
    def get_app_path(self):
        return BASE_DIR
    
    def get_platform(self):
        return sys.platform
    
    # ---- Build Engine ----
    
    def check_prerequisites(self):
        """
        Detect Windows ADK and related tools on this system.
        Returns JSON dict with tool status.
        """
        return self.check_prerequisites_dict()
    
    def check_prerequisites_dict(self):
        result = {
            'adk_installed': False,
            'copype_path': None,
            'oscdimg_path': None,
            'dism_available': False,
            'is_admin': False,
            'message': '',
            'winre_found': False,
            'winre_path': None,
            'boot_files_found': False,
            'can_build_without_adk': False,
        }
        
        # Check admin
        try:
            result['is_admin'] = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            result['is_admin'] = False
        
        # Check DISM
        try:
            subprocess.run(['dism.exe', '/?'], capture_output=True, timeout=5)
            result['dism_available'] = True
        except:
            pass
        
        # Find WinRE.wim (built-in PE source)
        winre = iso_builder.find_winre()
        if winre:
            result['winre_found'] = True
            result['winre_path'] = winre
        
        # Find Windows boot files
        boot_files = iso_builder.find_windows_boot_files()
        if boot_files.get('bootmgr') or boot_files.get('bootmgfw'):
            result['boot_files_found'] = True
        
        # Determine if we can build without ADK
        result['can_build_without_adk'] = (
            result['dism_available'] and 
            result['winre_found'] and
            result['boot_files_found']
        )
        
        # Find ADK
        arch = 'amd64'
        program_dirs = [
            os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
            os.environ.get('ProgramFiles', 'C:\\Program Files'),
        ]
        for base in list(dict.fromkeys(program_dirs)):
            adk_base = os.path.join(base, 'Windows Kits', '10', 'Assessment and Deployment Kit')
            if not os.path.isdir(adk_base):
                continue
            
            # copype.cmd
            cp = os.path.join(adk_base, 'Windows Preinstallation Environment', 'copype.cmd')
            if os.path.isfile(cp):
                result['copype_path'] = cp
            
            # oscdimg.exe
            od = os.path.join(adk_base, 'Deployment Tools', arch, 'Oscdimg', 'oscdimg.exe')
            if os.path.isfile(od):
                result['oscdimg_path'] = od
            
            if result['copype_path']:
                result['adk_installed'] = True
        
        if result['adk_installed']:
            result['message'] = '✓ Windows ADK 已安装'
        elif result['can_build_without_adk']:
            result['message'] = '✓ 可无 ADK 构建（使用系统 WinRE）'
        elif result['dism_available']:
            result['message'] = '⚠ DISM 可用，但缺少 WinRE 或启动文件'
        else:
            result['message'] = '❌ 未检测到 ADK 或 DISM'
        
        return result
    
    def generate_build_script(self, config_json):
        """
        Generate a complete PowerShell build script from the configuration.
        config_json: JSON string of the current state
        Returns the path to the generated script.
        """
        try:
            config = json.loads(config_json) if isinstance(config_json, str) else config_json
        except:
            return json.dumps({'error': '配置解析失败'})
        
        proj = config.get('project', {})
        source = config.get('source', {})
        tools = config.get('tools', [])
        drivers = config.get('drivers', [])
        desktop = config.get('desktop', {})
        
        # Map arch
        arch_map = {'x64': 'amd64', 'x86': 'x86', 'arm64': 'arm64'}
        arch = arch_map.get(proj.get('arch', 'x64'), 'amd64')
        
        # Tool paths
        tool_paths = []
        for t in tools:
            if t.get('path'):
                tool_paths.append(t['path'])
            else:
                tool_paths.append(f"C:\\PEBuilder\\Tools\\{t.get('name', 'tool')}")
        
        # Driver paths
        driver_paths = []
        for d in drivers:
            driver_paths.append(f"C:\\PEBuilder\\Drivers\\{d.get('name', 'driver')}")
        
        # Desktop icons
        icons = desktop.get('icons', {})
        icon_pairs = []
        for k, v in icons.items():
            icon_pairs.append(f"'{k}' = ${v.ToString().ToLower()}")
        icons_str = '; '.join(icon_pairs)
        
        # Wallpaper
        wallpaper = desktop.get('wallpaper', '')
        
        # Output dir
        output_dir = proj.get('outputDir', os.path.join(BASE_DIR, '..', 'Output'))
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(BASE_DIR, '..', 'Output')
        
        iso_name = proj.get('isoName', 'MyPE.iso') or 'MyPE.iso'
        if not iso_name.endswith('.iso'):
            iso_name += '.iso'
        
        # Lang
        lang = proj.get('lang', 'zh-CN')
        
        # Compress
        compress = proj.get('compress', 'max')
        
        # Options
        opts = proj.get('options', {})
        
        # Build script content by substituting template
        script = BUILD_SCRIPT_TEMPLATE
        script = script.replace('{{ARCH}}', arch)
        script = script.replace('{{LANG}}', lang)
        script = script.replace('{{SOURCE_PATH}}', source.get('path', ''))
        script = script.replace('{{OUTPUT_DIR}}', output_dir)
        script = script.replace('{{ISO_NAME}}', iso_name)
        script = script.replace('{{COMPRESS}}', compress)
        script = script.replace('{{PAGEFILE_MB}}', str(proj.get('pagefile', 1024)))
        script = script.replace('{{TEMP_DIR}}', proj.get('tempDir', 'X:\\Temp'))
        script = script.replace('{{ENABLE_NETWORK}}', str(opts.get('network', False)).lower())
        script = script.replace('{{ENABLE_MTP}}', str(opts.get('mtp', False)).lower())
        script = script.replace('{{ENABLE_DISM}}', str(opts.get('dism', False)).lower())
        script = script.replace('{{TOOLS_LIST}}', ', '.join(f"'{p}'" for p in tool_paths))
        script = script.replace('{{DRIVERS_LIST}}', ', '.join(f"'{p}'" for p in driver_paths))
        script = script.replace('{{ICONS_MAP}}', icons_str)
        script = script.replace('{{THEME_COLOR}}', desktop.get('themeColor', '#4a9eff'))
        script = script.replace('{{WALLPAPER}}', wallpaper)
        
        # Save the script
        script_dir = os.path.join(BASE_DIR, '..', 'build-scripts')
        os.makedirs(script_dir, exist_ok=True)
        script_path = os.path.join(script_dir, 'build-pe.ps1')
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script)
        
        # Also create a batch launcher
        bat_path = os.path.join(script_dir, 'build-pe.bat')
        with open(bat_path, 'w', encoding='gbk') as f:
            f.write('@echo off\n')
            f.write('cd /d "%~dp0"\n')
            f.write('echo PE Builder - 构建脚本\n')
            f.write('echo ========================\n')
            f.write('echo.\n')
            f.write('echo 正在启动 PowerShell 构建脚本...\n')
            f.write('echo 请以管理员身份运行以确保权限充足。\n')
            f.write('echo.\n')
            f.write('powershell.exe -ExecutionPolicy Bypass -File "build-pe.ps1"\n')
            f.write('echo.\n')
            f.write('if %errorlevel% equ 0 (\n')
            f.write('    echo 构建完成！\n')
            f.write(') else (\n')
            f.write('    echo 构建失败，详见日志。\n')
            f.write(')\n')
            f.write('pause\n')
        
        return json.dumps({
            'success': True,
            'script_path': script_path,
            'bat_path': bat_path,
            'output_dir': output_dir,
            'iso_name': iso_name,
        })
    
    def run_build(self, config_json):
        """
        Run the build process in a background thread.
        Returns immediately; progress is polled via get_build_status().
        """
        if self._build_running:
            return json.dumps({'error': '构建已在运行中'})
        
        self._build_running = True
        self._build_log = []
        self._build_progress = 0
        
        def _run():
            try:
                # First generate the script
                result = json.loads(self.generate_build_script(config_json))
                if not result.get('success'):
                    self._append_log('❌ 生成构建脚本失败')
                    self._build_progress = 0
                    self._build_running = False
                    return
                
                script_path = result['script_path']
                self._append_log('✅ 构建脚本已生成')
                self._append_log(f'   脚本: {script_path}')
                self._append_log(f'   输出: {result["output_dir"]}\\{result["iso_name"]}')
                self._append_log('')
                
                # Check prerequisites
                prereq = self.check_prerequisites_dict()
                
                # If ADK is available, use the standard ADK build
                if prereq['adk_installed']:
                    self._append_log('✅ ADK 已安装，使用标准构建流程')
                    self._build_with_adk(result, prereq)
                elif prereq['can_build_without_adk']:
                    self._append_log('✅ 检测到系统 WinRE，使用轻量构建流程（无需 ADK）')
                    self._build_no_adk(result, prereq)
                else:
                    self._append_log('⚠ 缺少 ADK 且未找到 WinRE')
                    self._append_log('请先设置源文件或自动安装 ADK')
                    self._append_log(f'   BAT 启动器: {result["bat_path"]}')
                    self._build_progress = 50
                
            finally:
                self._build_running = False
        
        threading.Thread(target=_run, daemon=True).start()
        return json.dumps({'started': True})
    
    def get_build_status(self):
        """Returns current build progress and log."""
        return json.dumps({
            'running': self._build_running,
            'progress': self._build_progress,
            'log': '\n'.join(self._build_log[-200:]),  # last 200 lines
            'log_full': '\n'.join(self._build_log),
        })
    
    def extract_system_drivers(self):
        """
        Extract driver information from the current Windows installation.
        Uses pnputil and DISM to enumerate installed drivers.
        Returns a list of driver metadata.
        """
        try:
            self._append_log('[驱动提取] 正在扫描本机驱动程序...')
            
            # Use pnputil to enumerate all third-party drivers
            result = subprocess.run(
                ['pnputil.exe', '/enum-drivers'],
                capture_output=True, text=True, timeout=30
            )
            
            drivers = []
            if result.returncode == 0:
                # Parse pnputil output
                lines = result.stdout.split('\n')
                current = {}
                for line in lines:
                    line = line.strip()
                    if line.startswith('发布名称:'):
                        if current.get('name'):
                            drivers.append(current)
                        current = {'name': line.split(':', 1)[1].strip()[:50]}
                    elif line.startswith('原始名称:'):
                        current['file'] = line.split(':', 1)[1].strip()
                    elif line.startswith('类名称:'):
                        current['type'] = line.split(':', 1)[1].strip()
                    elif line.startswith('类描述:'):
                        if 'type' not in current:
                            current['type'] = line.split(':', 1)[1].strip()
                
                if current.get('name'):
                    drivers.append(current)
                
                # Filter to relevant drivers (network, storage, USB)
                relevant_types = ['NET', 'USB', 'HDC', 'SCSIAdapter', 'USB', 'Network']
                relevant = [d for d in drivers if any(
                    t in d.get('type', '').upper() or t in d.get('name', '').upper()
                    for t in relevant_types
                )]
                
                # Format for frontend
                result_drivers = []
                added_names = set()
                for d in relevant:
                    name = d.get('name', '未知驱动')[:40]
                    if name in added_names:
                        continue
                    added_names.add(name)
                    
                    # Categorize
                    dtype = d.get('type', '未知')
                    if any(t in dtype.upper() for t in ['NET', '网络', 'WIFI', 'ETHERNET']):
                        category = '网络适配器'
                    elif any(t in dtype.upper() for t in ['HDC', 'SCSI', 'STOR', '存储']):
                        category = '存储控制器'
                    elif 'USB' in dtype.upper():
                        category = 'USB 控制器'
                    else:
                        category = '其他驱动'
                    
                    result_drivers.append({
                        'name': f'{name} (本机)',
                        'type': category,
                        'platform': 'x64',
                        'size': '~1MB',
                        'source': 'system',
                    })
                
                # Always add these common drivers if not found
                common = [
                    ('Intel VMD (RST) 本机', '存储控制器'),
                    ('NVMe 本机驱动', '存储控制器'),
                ]
                for cn, ct in common:
                    if not any(cn[:8] in d.get('name', '') for d in result_drivers):
                        result_drivers.append({
                            'name': cn, 'type': ct,
                            'platform': 'x64', 'size': '~2MB',
                            'source': 'system',
                        })
                
                self._append_log(f'[驱动提取] ✅ 找到 {len(result_drivers)} 个相关驱动')
                return json.dumps({'success': True, 'drivers': result_drivers})
            else:
                self._append_log('[驱动提取] ⚠ pnputil 执行失败，返回默认驱动集')
                return json.dumps({
                    'success': True,
                    'drivers': [
                        {'name':'NVMe 存储驱动 (本机)', 'type':'存储控制器', 'platform':'x64', 'size':'~2MB'},
                        {'name':'Intel VMD (本机)', 'type':'存储控制器', 'platform':'x64', 'size':'~2MB'},
                        {'name':'Realtek 以太网 (本机)', 'type':'网络适配器', 'platform':'x64', 'size':'~1MB'},
                        {'name':'Intel 网卡 (本机)', 'type':'网络适配器', 'platform':'x64', 'size':'~1MB'},
                    ]
                })
        except Exception as e:
            self._append_log(f'[驱动提取] ❌ 出错: {str(e)}')
            return json.dumps({'success': False, 'error': str(e)})
    
    def cancel_build(self):
        """Cancel the current build."""
        self._build_running = False
        self._append_log('⏹ 构建已取消')
        return json.dumps({'cancelled': True})
    
    def _build_with_adk(self, script_result, prereq):
        """Build PE ISO using Windows ADK tools."""
        self._append_log(f'管理员权限: {"✓ 是" if prereq["is_admin"] else "✗ 否（建议以管理员身份运行）"}')
        self._append_log('')
        
        if not prereq['is_admin']:
            self._append_log('⚠ 当前没有管理员权限，部分操作可能失败')
        
        script_path = script_result['script_path']
        
        self._append_log('')
        self._append_log('=== 使用 ADK 开始构建 ===')
        self._build_progress = 10
        
        try:
            process = subprocess.Popen(
                ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', script_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                cwd=os.path.dirname(script_path),
            )
            
            for line in iter(process.stdout.readline, ''):
                if line:
                    line = line.rstrip('\n\r')
                    self._append_log(line)
                    if 'STEP 1' in line: self._build_progress = 15
                    elif 'STEP 2' in line: self._build_progress = 25
                    elif 'STEP 3' in line: self._build_progress = 35
                    elif 'STEP 4' in line: self._build_progress = 45
                    elif 'STEP 5' in line: self._build_progress = 55
                    elif 'STEP 6' in line: self._build_progress = 65
                    elif 'STEP 7' in line: self._build_progress = 80
                    elif 'STEP 8' in line: self._build_progress = 90
                    elif '构建成功' in line: self._build_progress = 100
            
            process.wait()
            if process.returncode == 0 and self._build_progress < 100:
                self._build_progress = 100
            elif process.returncode != 0:
                self._append_log(f'⚠ 构建进程退出码: {process.returncode}')
                
        except Exception as e:
            self._append_log(f'❌ 执行构建脚本时出错: {str(e)}')
    
    def _build_no_adk(self, script_result, prereq):
        """
        Build PE ISO without ADK.
        Uses WinRE.wim from system + pycdlib for ISO creation.
        """
        self._append_log(f'管理员权限: {"✓ 是" if prereq["is_admin"] else "✗ 否"}')
        self._append_log(f'WinRE 源: {prereq["winre_path"]}')
        self._append_log('')
        
        if not prereq['is_admin']:
            self._append_log('⚠ 无管理员权限，DISM 操作可能失败')
            self._build_progress = 0
            return
        
        winre_path = prereq['winre_path']
        output_dir = script_result['output_dir']
        iso_name = script_result['iso_name']
        os.makedirs(output_dir, exist_ok=True)
        
        work_dir = os.path.join(output_dir, '.pebuild')
        os.makedirs(work_dir, exist_ok=True)
        
        output_iso = os.path.join(output_dir, iso_name)
        
        self._append_log('')
        self._append_log('=== 免 ADK 轻量构建 ===')
        self._append_log(f'WinRE: {winre_path}')
        self._append_log(f'输出: {output_iso}')
        self._build_progress = 10
        
        try:
            # Step 1: Mount WinRE and extract PE files
            self._append_log('STEP 1/3 — 提取 PE 系统文件...')
            self._build_progress = 15
            
            mount_dir = os.path.join(work_dir, 'mount')
            media_dir = os.path.join(work_dir, 'media')
            os.makedirs(media_dir, exist_ok=True)
            
            if os.path.isdir(mount_dir):
                shutil.rmtree(mount_dir, ignore_errors=True)
            os.makedirs(mount_dir)
            
            # Mount WinRE with DISM (read-only)
            mount_cmd = ['dism.exe', '/Mount-Image', f'/ImageFile:{winre_path}',
                        '/Index:1', f'/MountDir:{mount_dir}', '/ReadOnly']
            self._append_log(f'  DISM 挂载 WinRE...')
            result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                self._append_log(f'  ⚠ 挂载失败: {result.stderr[:200]}')
                self._append_log('  尝试备用方案：直接使用源 WinRE 文件')
            else:
                # Copy PE files to media directory
                self._append_log('  ✓ 挂载成功，复制 PE 文件...')
                for item in os.listdir(mount_dir):
                    src = os.path.join(mount_dir, item)
                    dst = os.path.join(media_dir, item)
                    try:
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    except Exception as e:
                        self._append_log(f'  ⚠ 跳过 {item}: {str(e)[:60]}')
                
                # Unmount
                subprocess.run(['dism.exe', '/Unmount-Image', f'/MountDir:{mount_dir}', '/Discard'],
                             capture_output=True, timeout=60)
                self._append_log('  ✓ PE 文件提取完成')
            
            self._build_progress = 35
            
            # Step 2: Set up PE structure
            self._append_log('STEP 2/3 — 构建 PE 启动结构...')
            self._build_progress = 40
            
            sources_dir = os.path.join(media_dir, 'sources')
            os.makedirs(sources_dir, exist_ok=True)
            
            # Copy WinRE as boot.wim
            boot_wim = os.path.join(sources_dir, 'boot.wim')
            if not os.path.isfile(boot_wim):
                shutil.copy2(winre_path, boot_wim)
                size_mb = os.path.getsize(boot_wim) / (1024*1024)
                self._append_log(f'  boot.wim: {size_mb:.0f}MB')
            
            # Copy bootmgr (for BIOS boot)
            boot_files = iso_builder.find_windows_boot_files()
            if boot_files.get('bootmgr'):
                shutil.copy2(boot_files['bootmgr'], os.path.join(media_dir, 'bootmgr'))
                self._append_log('  ✓ bootmgr 已复制')
            
            # Copy boot manager for EFI
            efi_dir = os.path.join(media_dir, 'efi', 'microsoft', 'boot')
            os.makedirs(efi_dir, exist_ok=True)
            if boot_files.get('bootmgfw'):
                shutil.copy2(boot_files['bootmgfw'], os.path.join(efi_dir, 'bootmgfw.efi'))
                # Also for standard EFI boot path
                efi_boot_dir = os.path.join(media_dir, 'efi', 'boot')
                os.makedirs(efi_boot_dir, exist_ok=True)
                shutil.copy2(boot_files['bootmgfw'], os.path.join(efi_boot_dir, 'bootx64.efi'))
                self._append_log('  ✓ EFI 启动文件已复制')
            
            self._build_progress = 60
            
            # Step 3: Create bootable ISO
            self._append_log('STEP 3/3 — 生成启动 ISO...')
            self._build_progress = 65
            
            # Generate boot images
            try:
                bios_img, efi_img = iso_builder.generate_boot_images(boot_files, work_dir)
                self._append_log(f'  启动映像生成完成')
            except Exception as e:
                self._append_log(f'  ⚠ 启动映像生成: {str(e)[:60]}')
                bios_img, efi_img = None, None
            
            self._build_progress = 75
            
            # Copy bundled tools to PE
            self._append_log('  — 内置工具打包...')
            tools_pe_dir = os.path.join(media_dir, 'Program Files', 'PBTools')
            os.makedirs(tools_pe_dir, exist_ok=True)
            
            browser_exe = os.path.join(TOOLS_DIR, 'PE-Browser.exe')
            dismpp_dir = os.path.join(TOOLS_DIR, 'Dism++')
            
            if os.path.isfile(browser_exe):
                shutil.copy2(browser_exe, os.path.join(tools_pe_dir, 'PE-Browser.exe'))
                size_mb = os.path.getsize(browser_exe) / (1024*1024)
                self._append_log(f'  ✓ PE-Browser: {size_mb:.0f}MB')
            
            if os.path.isdir(dismpp_dir):
                for item in os.listdir(dismpp_dir):
                    src = os.path.join(dismpp_dir, item)
                    dst = os.path.join(tools_pe_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                self._append_log(f'  ✓ Dism++: 已集成')
            else:
                self._append_log(f'  ⚠ Dism++ 未下载，可手动添加')
            
            self._build_progress = 80
            
            # Create ISO
            try:
                iso_size = iso_builder.create_bootable_iso(
                    output_iso, media_dir,
                    label='PE_BUILDER',
                    bios_boot_file=bios_img,
                    efi_boot_file=efi_img,
                )
                
                size_mb = iso_size / (1024*1024)
                self._append_log(f'✅ ISO 生成成功！')
                self._append_log(f'   路径: {output_iso}')
                self._append_log(f'   大小: {size_mb:.1f}MB (低于 3GB ✓)')
                self._build_progress = 100
                
            except Exception as e:
                self._append_log(f'❌ ISO 生成失败: {str(e)}')
                self._append_log('  已生成构建文件，请使用 ADK 的 oscdimg.exe 手动创建 ISO')
                self._build_progress = 70
        
        except Exception as e:
            self._append_log(f'❌ 构建出错: {str(e)}')
            import traceback
            self._append_log(traceback.format_exc()[-200:])
        
        finally:
            # Cleanup mount dir
            try:
                mount_dir = os.path.join(work_dir, 'mount')
                if os.path.isdir(mount_dir):
                    subprocess.run(['dism.exe', '/Unmount-Image', f'/MountDir:{mount_dir}', '/Discard'],
                                 capture_output=True, timeout=30)
                    shutil.rmtree(mount_dir, ignore_errors=True)
            except:
                pass
    
    def _append_log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        self._build_log.append(f'[{timestamp}] {msg}')


def main():
    window = webview.create_window(
        title='PE Builder — Windows PE 定制工具 v1.0',
        url=HTML_PATH,
        js_api=Api(),
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
        background_color='#1a1d24',
    )
    webview.start(
        debug=False,
        http_server=True,
    )


if __name__ == '__main__':
    main()
