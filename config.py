"""
Centralized configuration for DHCP Manager.

Production deployment: override any value using environment variables.
All sensitive defaults (secret key, password hash) MUST be changed before
exposing the web UI outside a trusted network.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    """Return environment variable value or the provided default."""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes")


@dataclass
class DHCPConfig:
    """DHCP server configuration paths and settings."""

    # ------------------------------------------------------------------
    # DHCP
    # ------------------------------------------------------------------
    DHCP_CONF: Path = field(
        default_factory=lambda: Path(_env("DHCP_CONF", "/etc/dhcp/dhcpd.conf"))
    )
    DHCP_BACKUP: Path = field(
        default_factory=lambda: Path(_env("DHCP_BACKUP", "/etc/dhcp/dhcpd.conf.bak"))
    )
    DHCP_SERVICE: str = field(default_factory=lambda: _env("DHCP_SERVICE", "isc-dhcp-server"))

    # ------------------------------------------------------------------
    # DNS / DDNS
    # ------------------------------------------------------------------
    BIND_SERVICE: str = field(default_factory=lambda: _env("BIND_SERVICE", "bind9"))

    # ------------------------------------------------------------------
    # PXE / TFTP (legacy PXELINUX)
    # ------------------------------------------------------------------
    TFTP_BASE_DIR: Path = field(
        default_factory=lambda: Path(
            _env("TFTP_BASE_DIR", "/var/lib/tftpboot/pxelinux.cfg")
        )
    )
    PXE_DEFAULT_MENU: str = field(default_factory=lambda: _env("PXE_DEFAULT_MENU", "default"))
    PXE_DISK0_MENU: str = field(
        default_factory=lambda: _env("PXE_DISK0_MENU", "default_local_disk0")
    )
    PXE_DISK1_MENU: str = field(
        default_factory=lambda: _env("PXE_DISK1_MENU", "default_local_disk1")
    )

    # ------------------------------------------------------------------
    # iPXE
    # Set IPXE_HTTP_BASE_URL to the URL clients can reach this Flask app:
    #   http://192.168.1.5:5000
    # ------------------------------------------------------------------
    IPXE_HTTP_BASE_URL: str = field(
        default_factory=lambda: _env("IPXE_HTTP_BASE_URL", "http://127.0.0.1:5000")
    )
    # Optional default chain target when a host profile is "default".
    # e.g. http://192.168.1.5/boot/menu.ipxe
    IPXE_DEFAULT_CHAIN_URL: str = field(
        default_factory=lambda: _env("IPXE_DEFAULT_CHAIN_URL", "")
    )
    IPXE_DIR: str = field(default_factory=lambda: _env("IPXE_DIR", "ipxe"))
    IPXE_SCRIPT_FILENAME: str = field(
        default_factory=lambda: _env("IPXE_SCRIPT_FILENAME", "ipxe/ipxe.ipxe")
    )
    # Per-client scripts: <tftp-root>/ipxe/clients/<ip>.ipxe
    IPXE_CLIENTS_DIR: str = field(
        default_factory=lambda: _env("IPXE_CLIENTS_DIR", "clients")
    )
    # Legacy alias kept for older tests.
    IPXE_MAC_SCRIPT_DIR: str = field(
        default_factory=lambda: _env("IPXE_MAC_SCRIPT_DIR", "ipxe/clients")
    )
    IPXE_BIOS_BOOTLOADER: str = field(
        default_factory=lambda: _env("IPXE_BIOS_BOOTLOADER", "undionly.kpxe")
    )
    IPXE_UEFI_BOOTLOADER: str = field(
        default_factory=lambda: _env("IPXE_UEFI_BOOTLOADER", "ipxe.efi")
    )
    PXELINUX_BOOTLOADER: str = field(
        default_factory=lambda: _env("PXELINUX_BOOTLOADER", "pxelinux.0")
    )
    IPXE_RETRY_SECONDS: int = field(
        default_factory=lambda: _env_int("IPXE_RETRY_SECONDS", 10)
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_FILE: Path = field(
        default_factory=lambda: Path(_env("LOG_FILE", "/var/log/dhcp_manager.log"))
    )
    LOG_MAX_BYTES: int = field(default_factory=lambda: _env_int("LOG_MAX_BYTES", 500_000))
    LOG_BACKUP_COUNT: int = field(default_factory=lambda: _env_int("LOG_BACKUP_COUNT", 2))

    # ------------------------------------------------------------------
    # Flask / Auth
    # Change FLASK_SECRET_KEY and ADMIN_PASSWORD_HASH before production use.
    # Generate a new hash:  python3 -c "import bcrypt; print(bcrypt.hashpw(b'yourpass', bcrypt.gensalt()).decode())"
    # ------------------------------------------------------------------
    FLASK_SECRET_KEY: str = field(
        default_factory=lambda: _env("FLASK_SECRET_KEY", "change-this-in-production")
    )
    FLASK_HOST: str = field(default_factory=lambda: _env("FLASK_HOST", "0.0.0.0"))
    FLASK_PORT: int = field(default_factory=lambda: _env_int("FLASK_PORT", 5000))
    FLASK_DEBUG: bool = field(
        default_factory=lambda: _env_bool("FLASK_DEBUG", False)
    )
    ADMIN_USERNAME: str = field(
        default_factory=lambda: _env("ADMIN_USERNAME", "Admin")
    )
    # Default hash corresponds to "DHCPManager!" — change before production use.
    ADMIN_PASSWORD_HASH: str = field(
        default_factory=lambda: _env(
            "ADMIN_PASSWORD_HASH",
            "$2b$12$D3Rhw47KU47/oK6OTreZIu9YL42O4ROVPEEsoHuWpJ4AmYq6bgHLG",
        )
    )


# Global configuration instance
config = DHCPConfig()
