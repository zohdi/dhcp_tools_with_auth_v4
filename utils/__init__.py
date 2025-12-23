"""
Utilities package for DHCP Manager.
Provides colors, logging, and validation utilities.
"""

from .colors import Color, green, red, yellow, blue, cyan, bold
from .logger import setup_logger, get_logger
from .validators import (
    validate_ip_address,
    validate_mac_address,
    validate_hostname,
    validate_dhcp_entry,
    validate_boot_device
)

__all__ = [
    # Colors
    'Color', 'green', 'red', 'yellow', 'blue', 'cyan', 'bold',
    # Logger
    'setup_logger', 'get_logger',
    # Validators
    'validate_ip_address',
    'validate_mac_address',
    'validate_hostname',
    'validate_dhcp_entry',
    'validate_boot_device',
]
