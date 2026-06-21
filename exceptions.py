"""
Custom exceptions for DHCP Manager.

Provides clear, specific error types so callers (CLI and web) can
distinguish failure modes without parsing error strings.
"""


class DHCPManagerError(Exception):
    """Base exception for all DHCP Manager errors."""


class ValidationError(DHCPManagerError):
    """Raised when input validation fails."""


class EntryNotFoundError(DHCPManagerError):
    """Raised when a DHCP entry is not found."""


class EntryExistsError(DHCPManagerError):
    """Raised when attempting to create a duplicate entry."""


class SyntaxValidationError(DHCPManagerError):
    """Raised when DHCP configuration syntax is invalid."""


class ServiceError(DHCPManagerError):
    """Raised when a system service operation fails."""


class PXEBootError(DHCPManagerError):
    """Raised when PXE boot operations fail."""


class FileOperationError(DHCPManagerError):
    """Raised when file operations fail."""
