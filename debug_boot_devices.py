#!/usr/bin/env python3
"""
Debug script to troubleshoot PXE boot device detection.
Shows detailed information about boot links and their detection.

Usage: sudo python3 debug_boot_devices.py [ip_address]
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from managers.pxe_manager import PXEBootManager
from managers.dhcp_manager import DHCPManager
from utils.colors import green, red, yellow, blue, cyan
from config import config


def check_tftp_directory():
    """Check if TFTP directory exists and is accessible."""
    print(blue("=" * 60))
    print(blue("Checking TFTP Directory"))
    print(blue("=" * 60))
    
    tftp_dir = config.TFTP_BASE_DIR
    print(f"\nTFTP Directory: {tftp_dir}")
    
    if not tftp_dir.exists():
        print(red(f"✗ Directory does not exist!"))
        print(yellow(f"  Please create it: sudo mkdir -p {tftp_dir}"))
        return False
    
    print(green("✓ Directory exists"))
    
    # Check permissions
    if not tftp_dir.is_dir():
        print(red("✗ Path exists but is not a directory!"))
        return False
    
    print(green("✓ Is a directory"))
    
    try:
        # List contents
        entries = list(tftp_dir.iterdir())
        print(f"\n{cyan('Contents:')} {len(entries)} items")
        
        # Count symlinks
        symlinks = [e for e in entries if e.is_symlink()]
        print(f"  Symlinks: {len(symlinks)}")
        
        # Show some examples
        if symlinks:
            print(f"\n{cyan('Example symlinks:')}")
            for link in symlinks[:5]:
                try:
                    target = link.readlink()
                    print(f"    {link.name} → {target}")
                except:
                    print(f"    {link.name} → (broken link)")
        
        return True
        
    except PermissionError:
        print(red("✗ Permission denied reading directory"))
        print(yellow("  Run with: sudo python3 debug_boot_devices.py"))
        return False


def check_single_ip(ip: str):
    """Check boot device configuration for a single IP."""
    print(blue("=" * 60))
    print(blue(f"Checking IP: {ip}"))
    print(blue("=" * 60))
    
    pxe = PXEBootManager()
    
    # Step 1: IP to Hex conversion
    try:
        hex_name = pxe.ip_to_hex(ip)
        print(f"\n{cyan('Step 1: IP to Hex Conversion')}")
        print(f"  IP:  {ip}")
        print(f"  Hex: {green(hex_name)}")
    except Exception as e:
        print(red(f"✗ Failed to convert IP: {e}"))
        return
    
    # Step 2: Link path
    link_path = pxe.get_link_path(ip)
    print(f"\n{cyan('Step 2: Link Path')}")
    print(f"  Path: {link_path}")
    print(f"  Exists: {green('Yes') if link_path.exists() else red('No')}")
    
    if link_path.exists():
        print(f"  Is symlink: {green('Yes') if link_path.is_symlink() else red('No')}")
    
    # Step 3: Boot target
    print(f"\n{cyan('Step 3: Boot Target')}")
    try:
        target = pxe.get_boot_target(ip)
        if target:
            print(f"  Target: {green(target)}")
        else:
            print(f"  Target: {yellow('None (no link configured)')}")
    except Exception as e:
        print(red(f"✗ Error reading target: {e}"))
        target = None
    
    # Step 4: Boot device detection
    print(f"\n{cyan('Step 4: Device Detection')}")
    try:
        device = pxe.get_boot_device(ip)
        
        # Show color-coded device
        if device == "hd0":
            device_display = blue(device)
        elif device == "hd1":
            device_display = green(device)
        else:
            device_display = yellow(device)
        
        print(f"  Detected: {device_display}")
        
        # Show mapping
        print(f"\n{cyan('Device Mapping:')}")
        for dev, menu in pxe.device_menu_map.items():
            match = "✓" if (target and menu in target) else " "
            print(f"    [{match}] {dev:8} → {menu}")
        
    except Exception as e:
        print(red(f"✗ Error detecting device: {e}"))
    
    print()


def check_all_ips():
    """Check boot devices for all DHCP entries."""
    print(blue("=" * 60))
    print(blue("Checking All DHCP Entries"))
    print(blue("=" * 60))
    print()
    
    dhcp = DHCPManager()
    pxe = PXEBootManager()
    
    try:
        entries = dhcp.get_all_entries()
        print(f"Found {len(entries)} DHCP entries\n")
        
        # Table header
        print(f"{'Hostname':<20} {'IP':<15} {'Device':<10} {'Target'}")
        print("-" * 70)
        
        for entry in entries:
            ip = entry['ip']
            hostname = entry['hostname']
            
            try:
                device = pxe.get_boot_device(ip)
                target = pxe.get_boot_target(ip) or "no link"
                
                # Color code device
                if device == "hd0":
                    device_display = blue(device)
                elif device == "hd1":
                    device_display = green(device)
                else:
                    device_display = yellow(device)
                
                print(f"{hostname:<20} {ip:<15} {device_display:<20} {target}")
                
            except Exception as e:
                print(f"{hostname:<20} {ip:<15} {red('ERROR'):<20} {str(e)}")
        
        print()
        
    except Exception as e:
        print(red(f"✗ Failed to read DHCP entries: {e}"))


def list_all_pxe_links():
    """List all PXE boot links in the TFTP directory."""
    print(blue("=" * 60))
    print(blue("All PXE Boot Links"))
    print(blue("=" * 60))
    print()
    
    pxe = PXEBootManager()
    configs = pxe.list_all_boot_configs()
    
    if not configs:
        print(yellow("No PXE boot links found"))
        return
    
    print(f"{'Hex':<10} {'IP':<15} {'Device':<10} {'Target'}")
    print("-" * 70)
    
    for cfg in configs:
        device = cfg['device']
        
        # Color code device
        if device == "hd0":
            device_display = blue(device)
        elif device == "hd1":
            device_display = green(device)
        else:
            device_display = yellow(device)
        
        print(f"{cfg['hex']:<10} {cfg['ip']:<15} {device_display:<20} {cfg['target']}")
    
    print()


def main():
    """Main debug function."""
    print()
    print(green("=" * 60))
    print(green("  PXE Boot Device Debug Tool"))
    print(green("=" * 60))
    print()
    
    # Check TFTP directory first
    if not check_tftp_directory():
        print()
        print(red("Cannot proceed - TFTP directory issue"))
        return 1
    
    print()
    
    # Check if specific IP provided
    if len(sys.argv) > 1:
        ip = sys.argv[1]
        check_single_ip(ip)
    else:
        # Show all
        check_all_ips()
        print()
        list_all_pxe_links()
    
    print(blue("=" * 60))
    print()
    print(cyan("Troubleshooting Tips:"))
    print("  • If 'No link' shown, create one via web interface")
    print("  • If wrong device detected, check symlink target matches expected pattern")
    print("  • Run with specific IP for detailed analysis: sudo python3 debug_boot_devices.py 192.168.1.10")
    print()
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(yellow("\n\nInterrupted by user"))
        sys.exit(130)
    except Exception as e:
        print(red(f"\n✗ Unexpected error: {e}"))
        import traceback
        traceback.print_exc()
        sys.exit(1)
