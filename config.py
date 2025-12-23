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
