#!/usr/bin/env python3
"""
DHCP Manager CLI - Command-line interface for DHCP management.
"""
import argparse
import sys
from typing import NoReturn

from managers.dhcp_manager import DHCPManager
from exceptions import DHCPManagerError
from utils.colors import green, red, yellow, blue


def handle_add(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Handle add command."""
    mgr.add_entry(args.hostname, args.mac, args.ip)


def handle_remove(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Handle remove command."""
    mgr.remove_entry(args.identifier)


def handle_modify(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Handle modify command."""
    # Check that at least one field is provided
    if not any([args.hostname, args.mac, args.ip]):
        print(yellow("⚠ You must provide at least one field to modify"))
        print("   Use --hostname, --mac, or --ip")
        sys.exit(1)
    
    mgr.modify_entry(
        identifier=args.identifier,
        new_hostname=args.hostname,
        new_mac=args.mac,
        new_ip=args.ip
    )


def handle_query(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Handle query command."""
    mgr.query_entry(args.identifier)


def handle_list(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Handle list command (shows all entries)."""
    mgr.query_entry(None)


def main() -> NoReturn:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DHCP Manager CLI - Manage DHCP host entries",
        epilog="Example: %(prog)s add --hostname server1 --mac aa:bb:cc:dd:ee:ff --ip 192.168.1.10"
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Available commands"
    )
    
    # -------------------- ADD --------------------
    add_parser = subparsers.add_parser(
        "add",
        help="Add a new DHCP host entry"
    )
    add_parser.add_argument(
        "--hostname",
        required=True,
        help="Hostname for the entry"
    )
    add_parser.add_argument(
        "--mac",
        required=True,
        help="MAC address (format: aa:bb:cc:dd:ee:ff)"
    )
    add_parser.add_argument(
        "--ip",
        required=True,
        help="IP address"
    )
    add_parser.set_defaults(func=handle_add)
    
    # -------------------- REMOVE --------------------
    rm_parser = subparsers.add_parser(
        "remove",
        aliases=["rm", "delete"],
        help="Remove a DHCP host entry"
    )
    rm_parser.add_argument(
        "identifier",
        help="IP address, MAC address, or hostname to remove"
    )
    rm_parser.set_defaults(func=handle_remove)
    
    # -------------------- MODIFY --------------------
    mod_parser = subparsers.add_parser(
        "modify",
        aliases=["mod", "edit"],
        help="Modify an existing DHCP host entry"
    )
    mod_parser.add_argument(
        "identifier",
        help="IP address, MAC address, or hostname to modify"
    )
    mod_parser.add_argument(
        "--hostname",
        help="New hostname"
    )
    mod_parser.add_argument(
        "--mac",
        help="New MAC address"
    )
    mod_parser.add_argument(
        "--ip",
        help="New IP address"
    )
    mod_parser.set_defaults(func=handle_modify)
    
    # -------------------- QUERY --------------------
    query_parser = subparsers.add_parser(
        "query",
        aliases=["find", "search"],
        help="Query a specific DHCP entry"
    )
    query_parser.add_argument(
        "identifier",
        help="IP address, MAC address, or hostname to query"
    )
    query_parser.set_defaults(func=handle_query)
    
    # -------------------- LIST --------------------
    list_parser = subparsers.add_parser(
        "list",
        aliases=["ls", "all"],
        help="List all DHCP entries"
    )
    list_parser.set_defaults(func=handle_list)
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create manager instance
    try:
        mgr = DHCPManager()
    except Exception as e:
        print(red(f"✗ Failed to initialize DHCP Manager: {e}"))
        sys.exit(1)
    
    # Execute command
    try:
        args.func(mgr, args)
        sys.exit(0)
        
    except DHCPManagerError as e:
        print(red(f"✗ Error: {e}"))
        sys.exit(1)
        
    except KeyboardInterrupt:
        print(yellow("\n⚠ Operation cancelled by user"))
        sys.exit(130)
        
    except Exception as e:
        print(red(f"✗ Unexpected error: {e}"))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
