"""
PXE Boot Manager - Replaces convert.sh and manage_links_from_ip.py

Handles PXE boot configuration through symlink management in the TFTP directory.
"""
import os
from pathlib import Path
from typing import Optional, Dict, List

from config import config
from exceptions import PXEBootError, ValidationError
from utils.validators import validate_ip_address, validate_boot_device
from utils.logger import get_logger


class PXEBootManager:
    """
    Manages PXE boot configurations by creating and managing symlinks
    in the TFTP directory.
    """
    
    def __init__(self, tftp_dir: Optional[Path] = None):
        """
        Initialize PXE Boot Manager.
        
        Args:
            tftp_dir: TFTP configuration directory (uses config default if None)
        """
        self.tftp_dir = tftp_dir or config.TFTP_BASE_DIR
        self.logger = get_logger()
        
        # Boot device to menu template mapping
        self.device_menu_map: Dict[str, str] = {
            "default": config.PXE_DEFAULT_MENU,
            "hd0": config.PXE_DISK0_MENU,
            "hd1": config.PXE_DISK1_MENU,
        }
    
    @staticmethod
    def ip_to_hex(ip: str) -> str:
        """
        Convert IP address to hexadecimal format used by PXE.
        
        Args:
            ip: IP address (e.g., "192.168.1.10")
            
        Returns:
            Hexadecimal string (e.g., "C0A8010A")
            
        Raises:
            ValidationError: If IP is invalid
        """
        validated_ip = validate_ip_address(ip)
        octets = validated_ip.split('.')
        
        try:
            hex_parts = [f"{int(octet):02X}" for octet in octets]
            return ''.join(hex_parts)
        except ValueError as e:
            raise ValidationError(f"Failed to convert IP to hex: {e}")
    
    @staticmethod
    def hex_to_ip(hex_str: str) -> str:
        """
        Convert hexadecimal PXE filename to IP address.
        
        Args:
            hex_str: 8-character hexadecimal string (e.g., "C0A8010A")
            
        Returns:
            IP address string (e.g., "192.168.1.10")
            
        Raises:
            ValidationError: If hex string is invalid
        """
        if not hex_str or len(hex_str) != 8:
            raise ValidationError(f"Invalid hex string length: {hex_str}")
        
        try:
            octets = []
            for i in range(0, 8, 2):
                octet = int(hex_str[i:i+2], 16)
                octets.append(str(octet))
            
            ip = '.'.join(octets)
            # Validate the resulting IP
            validate_ip_address(ip)
            return ip
        except (ValueError, ValidationError) as e:
            raise ValidationError(f"Failed to convert hex to IP: {e}")
    
    def get_link_path(self, ip: str) -> Path:
        """
        Get the full path to the PXE configuration symlink for an IP.
        
        Args:
            ip: IP address
            
        Returns:
            Path to the symlink file
        """
        hex_name = self.ip_to_hex(ip)
        return self.tftp_dir / hex_name
    
    def create_boot_link(self, ip: str, boot_device: str) -> None:
        """
        Create or update a PXE boot symlink for an IP address.
        
        Args:
            ip: IP address
            boot_device: Boot device identifier ("default", "hd0", or "hd1")
            
        Raises:
            ValidationError: If inputs are invalid
            PXEBootError: If symlink creation fails
        """
        validate_ip_address(ip)
        validate_boot_device(boot_device)
        
        menu_template = self.device_menu_map[boot_device]
        link_path = self.get_link_path(ip)
        
        try:
            # Ensure TFTP directory exists
            self.tftp_dir.mkdir(parents=True, exist_ok=True)
            
            # Remove existing link if present
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
                self.logger.info(f"Removed existing PXE link for {ip}")
            
            # Create new symlink
            link_path.symlink_to(menu_template)
            
            self.logger.info(f"Created PXE link: {link_path.name} -> {menu_template}")
            
        except OSError as e:
            raise PXEBootError(f"Failed to create PXE boot link for {ip}: {e}")
    
    def delete_boot_link(self, ip: str) -> None:
        """
        Delete a PXE boot symlink for an IP address.
        
        Args:
            ip: IP address
            
        Raises:
            ValidationError: If IP is invalid
            PXEBootError: If deletion fails
        """
        validate_ip_address(ip)
        link_path = self.get_link_path(ip)
        
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
                self.logger.info(f"Deleted PXE link for {ip}: {link_path.name}")
            else:
                self.logger.warning(f"No PXE link found for {ip}")
                
        except OSError as e:
            raise PXEBootError(f"Failed to delete PXE boot link for {ip}: {e}")
    
    def get_boot_target(self, ip: str) -> Optional[str]:
        """
        Get the current boot menu target for an IP address.
        
        Args:
            ip: IP address
            
        Returns:
            Boot menu filename (e.g., "default_local_disk0") or None if no link exists
            
        Raises:
            ValidationError: If IP is invalid
        """
        validate_ip_address(ip)
        link_path = self.get_link_path(ip)
        
        try:
            if link_path.exists() and link_path.is_symlink():
                target = os.readlink(str(link_path))
                self.logger.debug(f"Boot target for {ip} ({link_path.name}): {target}")
                return target
            else:
                self.logger.debug(f"No PXE link found for {ip} at {link_path}")
                return None
        except OSError as e:
            self.logger.error(f"Failed to read PXE link for {ip}: {e}")
            return None
    
    def get_boot_device(self, ip: str) -> str:
        """
        Get the simplified boot device label for an IP.
        
        Args:
            ip: IP address
            
        Returns:
            Boot device label: "default", "hd0", or "hd1"
        """

        try:
            target = self.get_boot_target(ip)
            
            if not target:
                return "default"
            
            # Map menu template back to device label
            # Check exact matches first, then substring matches
            if target.endswith(config.PXE_DISK0_MENU):
                return "hd0"
            elif target.endswith(config.PXE_DISK1_MENU):
                return "hd1"
            elif target.endswith(config.PXE_DEFAULT_MENU):
                return "default"

            for device, menu in self.device_menu_map.items():
                if target == menu or menu in target:
                    self.logger.debug(f"Matched {ip} target '{target}' to device '{device}'")
                    return device
            
            # If no match found, log it for debugging
            self.logger.warning(f"Unknown boot target for {ip}: {target}")
            return "default"
            
        except Exception as e:
            self.logger.error(f"Error getting boot device for {ip}: {e}")
            return "default"
    
    def list_all_boot_configs(self) -> List[Dict[str, str]]:
        """
        List all PXE boot configurations in the TFTP directory.
        
        Returns:
            List of dicts with 'ip', 'hex', 'target', and 'device' keys
        """
        configs = []
        
        if not self.tftp_dir.exists():
            return configs
        
        try:
            for entry in self.tftp_dir.iterdir():
                # Check if it's a symlink with 8-char hex name
                if entry.is_symlink() and len(entry.name) == 8:
                    try:
                        ip = self.hex_to_ip(entry.name)
                        target = os.readlink(str(entry))
                        device = self.get_boot_device(ip)
                        
                        configs.append({
                            'ip': ip,
                            'hex': entry.name,
                            'target': target,
                            'device': device
                        })
                    except (ValidationError, OSError) as e:
                        self.logger.warning(f"Skipping invalid entry {entry.name}: {e}")
                        
        except OSError as e:
            self.logger.error(f"Failed to list TFTP directory: {e}")
        
        return sorted(configs, key=lambda x: x['ip'])
