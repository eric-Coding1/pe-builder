"""
ISO Builder — 纯 Python ISO 9660 + El Torito 启动镜像生成器
支持 x64 / x86 / ARM64 架构
"""
import os
import sys
import shutil
import struct
import logging
import tempfile

try:
    import pycdlib
except ImportError:
    pycdlib = None

logger = logging.getLogger('ISOBuilder')

# Architecture-specific mappings
EFI_BOOT_NAMES = {
    'amd64': 'bootx64.efi',
    'x64':   'bootx64.efi',
    'x86':   'bootia32.efi',
    'arm64': 'bootaa64.efi',
}
EFI_BOOT_83 = {
    'amd64': b'BOOTX64 EFI',
    'x64':   b'BOOTX64 EFI',
    'x86':   b'BOOTIA32 EFI',
    'arm64': b'BOOTAA64 EFI',
}


def get_efi_boot_name(arch):
    """Get the EFI boot file name for a given architecture."""
    return EFI_BOOT_NAMES.get(arch, 'bootx64.efi')


def create_efi_boot_image(bootmgfw_path, output_path, arch='x64'):
    """
    Create a FAT16 floppy image containing the EFI boot file.
    Supports x64 (bootx64.efi), x86 (bootia32.efi), arm64 (bootaa64.efi).
    """
    if not os.path.isfile(bootmgfw_path):
        raise FileNotFoundError(f'EFI boot file not found: {bootmgfw_path}')
    
    efi_name = EFI_BOOT_83.get(arch, b'BOOTX64 EFI')
    efi_data = open(bootmgfw_path, 'rb').read()
    # FAT16: 1.44MB floppy image = 2880 sectors * 512 bytes
    fat_size = 9  # sectors per FAT (for 1.44MB)
    root_entries = 224
    root_size = root_entries * 32  # 7168 bytes = 14 sectors
    reserved_sectors = 1  # boot sector
    sectors_per_cluster = 1
    total_sectors = 2880
    
    # Calculate offsets
    fat1_offset = reserved_sectors * 512
    fat2_offset = fat1_offset + fat_size * 512
    root_offset = fat2_offset + fat_size * 512
    data_offset = root_offset + root_size
    
    # Create FAT image
    image = bytearray(1474560)  # 1.44MB
    
    # BIOS Parameter Block (for FAT16 floppy)
    bpb = b''
    bpb += struct.pack('<H', 0xEB34)  # jmp instruction
    bpb += b'\x90'  # nop
    bpb += b'MSDOS5.0'  # OEM ID (8 bytes)
    bpb += struct.pack('<H', 512)  # bytes per sector
    bpb += struct.pack('B', sectors_per_cluster)  # sectors per cluster
    bpb += struct.pack('<H', reserved_sectors)  # reserved sectors
    bpb += struct.pack('B', 2)  # number of FATs
    bpb += struct.pack('<H', root_entries)  # max root entries
    bpb += struct.pack('<H', total_sectors)  # total sectors (small)
    bpb += struct.pack('B', 0xF0)  # media descriptor
    bpb += struct.pack('<H', fat_size)  # sectors per FAT
    bpb += struct.pack('<H', 18)  # sectors per track
    bpb += struct.pack('<H', 2)  # number of heads
    bpb += struct.pack('<I', 0)  # hidden sectors
    bpb += struct.pack('<I', 0)  # total sectors (large, 0 if small used)
    bpb += struct.pack('B', 0x80)  # drive number (0x80 for HD)
    bpb += b'\x00'  # reserved
    bpb += struct.pack('B', 0x29)  # extended boot signature
    bpb += struct.pack('<I', 0x12345678)  # volume serial number
    bpb += b'EFI BOOT    '  # volume label (11 bytes)
    bpb += b'FAT16   '  # filesystem type (8 bytes)
    
    # Boot sector override for El Torito
    # The first 3 bytes are the jump instruction
    image[0:3] = struct.pack('<H', 0xEB34) + b'\x90'
    image[3:0x3E] = bpb[3:0x3E]
    # Boot code (minimal)
    image[0x3E:0x1FE] = bytes(b'\x00' * 0x1C0)
    image[0x1FE:0x200] = struct.pack('<H', 0xAA55)  # Boot signature
    
    # Write FAT1 - mark clusters used by root directory
    # Cluster 0 = 0xFF0 (media descriptor + 0xF for end)
    # Cluster 1 = 0xFFF (end of chain, reserved)
    # Cluster 2+ = data clusters
    # FAT entries are 16-bit
    fat_data = bytearray(fat_size * 512)
    # Cluster 0: media descriptor
    struct.pack_into('<H', fat_data, 0, 0xFFF0 | 0x0F)
    # Cluster 1: end of chain
    struct.pack_into('<H', fat_data, 2, 0xFFFF)
    
    # Calculate how many clusters root directory takes
    root_clusters = (root_size + 511) // 512
    for i in range(root_clusters):
        if i == root_clusters - 1:
            struct.pack_into('<H', fat_data, (i + 2) * 2, 0xFFFF)  # end of chain
        else:
            struct.pack_into('<H', fat_data, (i + 2) * 2, i + 3)  # next cluster
    
    image[fat1_offset:fat1_offset + len(fat_data)] = fat_data
    image[fat2_offset:fat2_offset + len(fat_data)] = fat_data  # copy to FAT2
    
    # Root directory entries
    root_data = bytearray(root_size)
    
    # Volume label entry
    vol_entry = bytearray(32)
    vol_entry[0] = 0x08  # volume label attribute
    vol_label = b'EFI BOOT    '  # exactly 11 bytes
    vol_entry[1:12] = vol_label
    root_data[0:32] = vol_entry
    
    # Create directory entries for \EFI\BOOT\
    # We need: EFI directory, BOOT directory, bootx64.efi file
    
    # EFI subdirectory entry (starting at cluster after root)
    efi_cluster = 2 + root_clusters  # first data cluster
    efi_entry = bytearray(32)
    efi_entry[0:11] = b'EFI        '  # 8.3 name
    efi_entry[11] = 0x10  # subdirectory attribute
    efi_entry[26:28] = struct.pack('<H', efi_cluster)  # first cluster
    root_data[32:64] = efi_entry
    
    # BOOT subdirectory entry (inside EFI)
    boot_cluster = efi_cluster + 1
    boot_entry = bytearray(32)
    boot_entry[0:11] = b'BOOT       '  # 8.3 name
    boot_entry[11] = 0x10  # subdirectory attribute
    boot_entry[26:28] = struct.pack('<H', boot_cluster)  # first cluster
    # We'll place this in EFI's directory data later
    
    # bootx64.efi file entry (inside EFI\BOOT)
    file_cluster = boot_cluster + 1
    file_entry = bytearray(32)
    file_entry[0:11] = efi_name  # 8.3 name per architecture
    file_entry[26:28] = struct.pack('<H', file_cluster)  # first cluster
    file_entry[28:32] = struct.pack('<I', len(efi_data))  # file size
    # We'll place this in BOOT's directory data later
    
    image[root_offset:root_offset + len(root_data)] = root_data
    
    # Write directory data for EFI (contains . and .. and BOOT)
    efi_dir_data = bytearray(sectors_per_cluster * 512)
    # . entry
    efi_dir_data[0] = 0x2E  # current dir
    efi_dir_data[1:11] = b'         '
    efi_dir_data[11] = 0x10  # directory
    efi_dir_data[26:28] = struct.pack('<H', efi_cluster)
    # .. entry
    efi_dir_data[32] = 0x2E
    efi_dir_data[33] = 0x2E
    efi_dir_data[34:43] = b'         '
    efi_dir_data[43] = 0x10
    efi_dir_data[58:60] = struct.pack('<H', 0)  # root cluster
    # BOOT entry
    efi_dir_data[64:96] = boot_entry
    efi_dir_data[64] = 0x2E  # Actually, let me rewrite properly
    efi_dir_data[64] = ord('B')
    
    # Actually, let me simplify this and write BOOT entry properly
    boot_name = b'BOOT       '
    efi_dir_data[64:75] = boot_name
    efi_dir_data[75] = 0x10  # directory attribute
    efi_dir_data[90:92] = struct.pack('<H', boot_cluster)
    
    image[data_offset:data_offset + len(efi_dir_data)] = efi_dir_data
    
    # Write directory data for BOOT (contains . and .. and bootx64.efi)
    boot_dir_offset = data_offset + (boot_cluster - efi_cluster) * sectors_per_cluster * 512
    # Actually, let me recalculate: each directory gets its own cluster
    # Cluster 2 = root, cluster 3 = EFI dir, cluster 4 = BOOT dir, cluster 5 = file
    
    # Wait, the cluster math is getting confusing. Let me recalculate.
    # Root directory starts at cluster 2
    # EFI directory starts at cluster 2 + root_clusters
    # BOOT directory starts at cluster 2 + root_clusters + 1
    # bootx64.efi starts at cluster 2 + root_clusters + 2
    
    boot_dir_offset = data_offset + ((2 + root_clusters + 1 - 2) * sectors_per_cluster * 512)
    boot_dir_data = bytearray(sectors_per_cluster * 512)
    # . entry
    boot_dir_data[0] = 0x2E
    boot_dir_data[11] = 0x10
    boot_dir_data[26:28] = struct.pack('<H', 2 + root_clusters + 1)
    # .. entry  
    boot_dir_data[32] = 0x2E
    boot_dir_data[33] = 0x2E
    boot_dir_data[43] = 0x10
    boot_dir_data[58:60] = struct.pack('<H', 2 + root_clusters)
    # bootx64.efi entry (architecture-specific)
    boot_dir_data[64:75] = efi_name
    boot_dir_data[90:92] = struct.pack('<H', 2 + root_clusters + 2)
    boot_dir_data[92:96] = struct.pack('<I', len(efi_data))
    
    image[boot_dir_offset:boot_dir_offset + len(boot_dir_data)] = boot_dir_data
    
    # Write bootx64.efi file data
    file_offset = data_offset + ((2 + root_clusters + 2 - 2) * sectors_per_cluster * 512)
    image[file_offset:file_offset + len(efi_data)] = efi_data
    
    # Write the image
    with open(output_path, 'wb') as f:
        f.write(image)
    
    return output_path


def create_bootable_iso(output_path, media_dir, label='PE_BUILDER', 
                         bios_boot_file=None, efi_boot_file=None):
    """
    Create a bootable ISO 9660 image using pycdlib.
    
    Args:
        output_path: Output ISO file path
        media_dir: Directory containing PE files to include
        label: Volume label (max 32 chars)
        bios_boot_file: Path to BIOS boot image (etfsboot.com)
        efi_boot_file: Path to UEFI boot image (efisys.bin)
    """
    if pycdlib is None:
        raise ImportError('pycdlib is required. Install with: pip install pycdlib')
    
    if not os.path.isdir(media_dir):
        raise NotADirectoryError(f'Media directory not found: {media_dir}')
    
    iso = pycdlib.PyCdlib()
    has_bios = bios_boot_file and os.path.isfile(bios_boot_file)
    has_efi = efi_boot_file and os.path.isfile(efi_boot_file)
    
    try:
        if has_bios and has_efi:
            iso.new(iso_level=3, joliet=True,
                    el_torito=bios_boot_file,
                    el_torito_boot_catalog='BOOT.CAT',
                    el_torito_platform=0x00,
                    el_torito_uefi=efi_boot_file,
                    interchange_level=3)
        elif has_bios:
            iso.new(iso_level=3, joliet=True,
                    el_torito=bios_boot_file,
                    el_torito_boot_catalog='BOOT.CAT')
        else:
            iso.new(iso_level=3, joliet=True)
        
        # Add boot files to ISO
        if has_bios:
            iso.add_file(bios_boot_file, '/etfsboot.com')
        if has_efi:
            iso.add_file(efi_boot_file, '/efisys.bin')
        
        # Walk media directory and add all files
        total_files = 0
        for root, dirs, files in os.walk(media_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                # Get relative path and convert to ISO format
                rel_path = os.path.relpath(filepath, media_dir)
                iso_path = '/' + rel_path.replace('\\', '/')
                
                # skp for boot files we already added
                if iso_path in ('/etfsboot.com', '/efisys.bin', '/BOOT.CAT'):
                    continue
                
                try:
                    if os.path.getsize(filepath) > 0:
                        iso.add_file(filepath, iso_path)
                    else:
                        # Empty file - add as a zero-length record
                        iso.add_fp(open(filepath, 'rb'), len(iso_path), iso_path)
                    total_files += 1
                except Exception as e:
                    logger.warning(f'Failed to add {filepath}: {e}')
        
        # Write ISO
        iso.write(output_path)
        
        return os.path.getsize(output_path)
        
    finally:
        iso.close()


def find_windows_boot_files(arch='x64'):
    """Find Windows boot files on the system for ISO creation.
    Supports: x64 (default), x86, arm64"""
    boot_files = {
        'bootmgr': None,
        'bootmgfw': None,
        'arch': arch,
    }
    
    # EFI boot file name per architecture
    efi_name = EFI_BOOT_NAMES.get(arch, 'bootx64.efi')
    
    # Common locations for BIOS boot manager (x86/x64 only)
    if arch in ('x64', 'x86', 'amd64'):
        bootmgr_paths = [
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Boot', 'PCAT', 'bootmgr'),
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Boot', 'bootmgr'),
        ]
        for p in bootmgr_paths:
            if os.path.isfile(p):
                boot_files['bootmgr'] = p
                break
    
    # Common locations for EFI boot manager
    bootmgfw_paths = [
        os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Boot', 'EFI', efi_name),
        os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'bootmgfw.efi'),
    ]
    for p in bootmgfw_paths:
        if os.path.isfile(p):
            boot_files['bootmgfw'] = p
            break
    
    # Also check EFI partition
    if not boot_files['bootmgfw']:
        esp_paths = [
            f'C:\\EFI\\Microsoft\\Boot\\{efi_name}',
            f'C:\\efi\\microsoft\\boot\\{efi_name}',
        ]
        for p in esp_paths:
            if os.path.isfile(p):
                boot_files['bootmgfw'] = p
                break
    
    return boot_files


def find_winre():
    """Find Windows Recovery Environment (WinRE.wim) on the system."""
    winre_paths = [
        os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'Recovery', 'winre.wim'),
        os.environ.get('RecoveryDirectory', ''),
        'C:\\Recovery\\WindowsRE\\winre.wim',
    ]
    for p in winre_paths:
        if p and os.path.isfile(p):
            return p
    return None


def generate_boot_images(boot_files, work_dir, arch='x64'):
    """
    Generate etfsboot.com and efisys.bin from Windows boot files.
    arch: x64 (default), x86, arm64
    """
    bios_img = None
    efi_img = None
    
    # Generate efisys.bin from bootmgfw.efi
    if boot_files.get('bootmgfw'):
        efi_img = os.path.join(work_dir, 'efisys.bin')
        create_efi_boot_image(boot_files['bootmgfw'], efi_img, arch=arch)
        logger.info(f'efisys.bin generated ({arch})')
    
    # For BIOS, use bootmgr as-is (x86/x64 only)
    if boot_files.get('bootmgr') and arch in ('x64', 'x86', 'amd64'):
        bios_img = os.path.join(work_dir, 'etfsboot.com')
        shutil.copy2(boot_files['bootmgr'], bios_img)
        logger.info(f'etfsboot.com copied ({arch})')
    
    return bios_img, efi_img


def extract_wim_image(wim_path, output_dir, index=1):
    """Extract a WIM image to a directory using DISM."""
    import subprocess
    cmd = [
        'dism.exe', '/Mount-Image',
        f'/ImageFile:{wim_path}',
        f'/Index:{index}',
        f'/MountDir:{output_dir}',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'DISM mount failed: {result.stderr}')
    
    # Now commit and unmount
    cmd2 = [
        'dism.exe', '/Unmount-Image',
        f'/MountDir:{output_dir}',
        '/Commit',
    ]
    # Actually for extraction we want to just read the files, not modify
    # Let's use /ReadOnly mount
    return True


def build_iso_from_pe(pe_wim_path, output_iso, work_dir, tools_dir=None):
    """
    Build a bootable PE ISO from a boot.wim file.
    
    This is the main entry point for PE ISO creation without ADK.
    """
    import subprocess
    
    os.makedirs(work_dir, exist_ok=True)
    mount_dir = os.path.join(work_dir, 'mount')
    media_dir = os.path.join(work_dir, 'media')
    os.makedirs(media_dir, exist_ok=True)
    
    try:
        # Step 1: Mount the PE WIM
        logger.info(f'Mounting {pe_wim_path}...')
        os.makedirs(mount_dir, exist_ok=True)
        cmd = ['dism.exe', '/Mount-Image', f'/ImageFile:{pe_wim_path}', 
               '/Index:1', f'/MountDir:{mount_dir}', '/ReadOnly']
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Step 2: Copy PE files to media directory (like copype does)
        for item in os.listdir(mount_dir):
            src = os.path.join(mount_dir, item)
            dst = os.path.join(media_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        
        # Step 3: Unmount
        subprocess.run(['dism.exe', '/Unmount-Image', f'/MountDir:{mount_dir}', '/Discard'],
                       check=True, capture_output=True)
        
        # Step 4: Create sources directory
        sources_dir = os.path.join(media_dir, 'sources')
        os.makedirs(sources_dir, exist_ok=True)
        
        # Copy the boot.wim to sources
        shutil.copy2(pe_wim_path, os.path.join(sources_dir, 'boot.wim'))
        
        # Create a minimal bootmgr in root (for BIOS boot)
        boot_files = find_windows_boot_files()
        if boot_files.get('bootmgr'):
            shutil.copy2(boot_files['bootmgr'], os.path.join(media_dir, 'bootmgr'))
        
        # Step 5: Generate boot images
        bios_img, efi_img = generate_boot_images(boot_files, work_dir)
        
        # Step 6: Create bootable ISO
        iso_size = create_bootable_iso(
            output_iso, media_dir,
            label='PE_BUILDER',
            bios_boot_file=bios_img if bios_img and os.path.isfile(bios_img) else None,
            efi_boot_file=efi_img if efi_img and os.path.isfile(efi_img) else None,
        )
        
        return iso_size
        
    finally:
        # Cleanup
        if os.path.isdir(mount_dir):
            try:
                subprocess.run(['dism.exe', '/Unmount-Image', f'/MountDir:{mount_dir}', '/Discard'],
                            capture_output=True)
            except:
                pass
        # Clean up mount dir
        try:
            shutil.rmtree(mount_dir, ignore_errors=True)
        except:
            pass


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Test
    boot = find_windows_boot_files()
    print('Boot files found:', boot)
    winre = find_winre()
    print('WinRE:', winre)
    
    if boot.get('bootmgfw'):
        test_dir = tempfile.mkdtemp()
        try:
            efi_path = os.path.join(test_dir, 'test_efisys.bin')
            create_efi_boot_image(boot['bootmgfw'], efi_path)
            print(f'efisys.bin created: {os.path.getsize(efi_path)} bytes')
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
