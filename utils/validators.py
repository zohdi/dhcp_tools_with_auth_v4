"""
Input validation utilities for DHCP Manager.
"""
import re
import ipaddress
from typing import Tuple

from exceptions import ValidationError


def validate_ip_address(ip: str) -> str:
    """
    Validate an IP address.
    
    Args:
        ip: IP address string
        
    Returns:
        Validated IP address string
        
    Raises:
        ValidationError: If IP is invalid
    """
    if not ip or not isinstance(ip, str):
        raise ValidationError("IP address cannot be empty")
    
    try:
        ipaddress.ip_address(ip.strip())
        return ip.strip()
    except ValueError:
        raise ValidationError(f"Invalid IP address: {ip}")


def validate_mac_address(mac: str) -> str:
    """
    Validate a MAC address.
    
    Args:
        mac: MAC address string
        
    Returns:
        Validated MAC address string in lowercase
        
    Raises:
        ValidationError: If MAC is invalid
    """
    if not mac or not isinstance(mac, str):
        raise ValidationError("MAC address cannot be empty")
    
    mac = mac.strip().lower()
    
    # Accept formats: aa:bb:cc:dd:ee:ff or aa-bb-cc-dd-ee-ff
    pattern = r'^([0-9a-f]{2}[:-]){5}([0-9a-f]{2})$'
    
    if not re.match(pattern, mac):
        raise ValidationError(f"Invalid MAC address format: {mac}")
    
    return mac


def validate_hostname(hostname: str) -> str:
    """
    Validate a hostname.
    
    Args:
        hostname: Hostname string
        
    Returns:
        Validated hostname string
        
    Raises:
        ValidationError: If hostname is invalid
    """
    if not hostname or not isinstance(hostname, str):
        raise ValidationError("Hostname cannot be empty")
    
    hostname = hostname.strip()
    
    # RFC 1123 hostname validation
    # - Length between 1 and 253 characters
    # - Each label 1-63 characters
    # - Labels contain only alphanumeric and hyphens
    # - Labels don't start or end with hyphen
    
    if len(hostname) > 253:
        raise ValidationError("Hostname too long (max 253 characters)")
    
    if not hostname:
        raise ValidationError("Hostname cannot be empty")
    
    # Check each label
    labels = hostname.split('.')
    
    for label in labels:
        if not label:
            raise ValidationError("Hostname labels cannot be empty")
        
        if len(label) > 63:
            raise ValidationError(f"Hostname label too long: {label}")
        
        if not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', label, re.IGNORECASE):
            raise ValidationError(f"Invalid hostname label: {label}")
    
    return hostname


def validate_dhcp_entry(hostname: str, mac: str, ip: str) -> Tuple[str, str, str]:
    """
    Validate a complete DHCP entry.
    
    Args:
        hostname: Hostname
        mac: MAC address
        ip: IP address
        
    Returns:
        Tuple of (validated_hostname, validated_mac, validated_ip)
        
    Raises:
        ValidationError: If any field is invalid
    """
    return (
        validate_hostname(hostname),
        validate_mac_address(mac),
        validate_ip_address(ip)
    )


def validate_boot_device(device: str) -> str:
    """
    Validate a boot device selection.
    
    Args:
        device: Boot device identifier
        
    Returns:
        Validated device string
        
    Raises:
        ValidationError: If device is invalid
    """
    valid_devices = {"default", "hd0", "hd1"}
    
    if device not in valid_devices:
        raise ValidationError(
            f"Invalid boot device: {device}. Must be one of: {', '.join(valid_devices)}"
        )
    
    return device
