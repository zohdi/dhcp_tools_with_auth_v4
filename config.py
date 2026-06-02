"""
Centralized configuration for DHCP Manager.
All paths and settings are defined here.
"""
from pathlib import Path
from dataclasses import dataclass


@dataclass
class DHCPConfig:
    """DHCP server configuration paths and settings."""
    
    # DHCP Configuration
    DHCP_CONF: Path = Path("/etc/dhcp/dhcpd.conf")
    DHCP_BACKUP: Path = Path("/etc/dhcp/dhcpd.conf.bak")
    DHCP_SERVICE: str = "isc-dhcp-server"
    
    # DNS/DDNS Configuration
    BIND_SERVICE: str = "bind9"
    
    # PXE Boot Configuration
    TFTP_BASE_DIR: Path = Path("/var/lib/tftpboot/pxelinux.cfg")
    PXE_DEFAULT_MENU: str = "default"
    PXE_DISK0_MENU: str = "default_local_disk0"
    PXE_DISK1_MENU: str = "default_local_disk1"

    # Dynamic iPXE Configuration
    # Set this to the URL clients can reach for this Flask app, for example:
    #   http://192.168.1.5:5000
    IPXE_HTTP_BASE_URL: str = "http://127.0.0.1:5000"
    # Optional default chain target used when a host profile is "default".
    # Examples: http://192.168.1.5/boot/menu.ipxe or http://192.168.1.5/winpe/boot.ipxe
    IPXE_DEFAULT_CHAIN_URL: str = ""
    # Static script handed to clients that are already running iPXE.
    # It is intentionally under the iPXE directory inside the TFTP root.
    IPXE_DIR: str = "ipxe"
    IPXE_SCRIPT_FILENAME: str = "ipxe/ipxe.ipxe"
    # Generated per-client scripts live under: <tftp-root>/ipxe/clients/<ip>.ipxe
    # and are served by Flask at: /ipxe/clients/<ip>.ipxe
    IPXE_CLIENTS_DIR: str = "clients"
    # Legacy compatibility alias for older code/tests. New generated files are IP-based.
    IPXE_MAC_SCRIPT_DIR: str = "ipxe/clients"
    IPXE_BIOS_BOOTLOADER: str = "undionly.kpxe"
    IPXE_UEFI_BOOTLOADER: str = "ipxe.efi"
    PXELINUX_BOOTLOADER: str = "pxelinux.0"
    IPXE_RETRY_SECONDS: int = 10
    
    # Logging
    LOG_FILE: Path = Path("/var/log/dhcp_manager.log")
    LOG_MAX_BYTES: int = 500000
    LOG_BACKUP_COUNT: int = 2
    
    # Flask Configuration
    FLASK_SECRET_KEY: str = "supersecretkey"  # Change in production
    FLASK_HOST: str = "0.0.0.0"
    FLASK_PORT: int = 5000
    FLASK_DEBUG: bool = True  # Set to False in production
    ADMIN_USERNAME: str = "Admin"
    ADMIN_PASSWORD_HASH: str = "$2b$12$D3Rhw47KU47/oK6OTreZIu9YL42O4ROVPEEsoHuWpJ4AmYq6bgHLG"
#    ADMIN_PASSWORD: str = "DHCPManager!"
# Authentication (simple built-in auth for the web UI)
# NOTE: Change these in production!

# Global configuration instance
config = DHCPConfig()
