"""
Terminal color utilities for CLI output.
"""


class Color:
    """ANSI color codes for terminal output."""
    
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def green(text: str) -> str:
    """Return text in green color."""
    return f"{Color.OKGREEN}{text}{Color.END}"


def red(text: str) -> str:
    """Return text in red color."""
    return f"{Color.FAIL}{text}{Color.END}"


def yellow(text: str) -> str:
    """Return text in yellow color."""
    return f"{Color.WARNING}{text}{Color.END}"


def blue(text: str) -> str:
    """Return text in blue color."""
    return f"{Color.OKBLUE}{text}{Color.END}"


def cyan(text: str) -> str:
    """Return text in cyan color."""
    return f"{Color.OKCYAN}{text}{Color.END}"


def bold(text: str) -> str:
    """Return text in bold."""
    return f"{Color.BOLD}{text}{Color.END}"
