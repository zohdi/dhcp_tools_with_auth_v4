"""
Custom exceptions for DHCP Manager.
Provides clear, specific error types for better error handling.
"""


class DHCPManagerError(Exception):
    """Base exception for all DHCP Manager errors."""
    pass


class ValidationError(DHCPManagerError):
    """Raised when input validation fails."""
    pass


class EntryNotFoundError(DHCPManagerError):
    """Raised when a DHCP entry is not found."""
    pass


class EntryExistsError(DHCPManagerError):
    """Raised when attempting to create a duplicate entry."""
    pass


class SyntaxValidationError(DHCPManagerError):
    """Raised when DHCP configuration syntax is invalid."""
    pass


class ServiceError(DHCPManagerError):
    """Raised when a system service operation fails."""
    pass


class PXEBootError(DHCPManagerError):
    """Raised when PXE boot operations fail."""
    pass


class FileOperationError(DHCPManagerError):
    """Raised when file operations fail."""
    pass
