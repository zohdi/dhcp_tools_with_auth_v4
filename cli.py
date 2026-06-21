#!/usr/bin/env python3
"""
DHCP Manager CLI - Command-line interface for DHCP management.
"""
import argparse
import sys
from typing import NoReturn

from managers.dhcp_manager import DHCPManager
from managers.pxe_manager import PXEBootManager
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


def handle_boot(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Handle per-client PXELINUX + iPXE boot profile changes."""
    pxe_mgr = PXEBootManager()
    if not pxe_mgr.boot_profile_exists(args.device):
        raise DHCPManagerError(f"Boot profile does not exist: {args.device}")
    pxe_mgr.create_boot_link(args.ip, args.device)
    if args.device == "default":
        pxe_mgr.delete_client_ipxe_script(args.ip)
        print(green(f"✓ PXELINUX boot profile for {args.ip} reset to default; iPXE override removed"))
    else:
        ipxe_path = pxe_mgr.write_client_ipxe_script(args.ip, args.device)
        print(green(f"✓ PXELINUX and iPXE boot profile for {args.ip} set to {args.device}"))
        print(f"  iPXE: {ipxe_path}")


def handle_ipxe_script(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Print the default iPXE dispatcher script."""
    pxe_mgr = PXEBootManager()
    print(pxe_mgr.generate_default_ipxe_script())


def handle_ipxe_install_default(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Install ipxe.ipxe into the TFTP root."""
    pxe_mgr = PXEBootManager()
    path = pxe_mgr.write_default_ipxe_script()
    print(green(f"✓ Installed default iPXE dispatcher: {path}"))


def handle_ipxe_set_client(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Create/update an IP-specific iPXE script."""
    pxe_mgr = PXEBootManager()
    if not pxe_mgr.boot_profile_exists(args.device):
        raise DHCPManagerError(f"Boot profile does not exist: {args.device}")
    path = pxe_mgr.write_client_ipxe_script(args.identifier, args.device)
    print(green(f"✓ Client iPXE script for {args.identifier} set to {args.device}: {path}"))
    print(f"  URL: {pxe_mgr.get_client_script_url(args.identifier)}")


def handle_ipxe_set_mac(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Deprecated MAC-specific iPXE helper."""
    raise DHCPManagerError("MAC-specific iPXE files are no longer generated. Use: ipxe set-client <IP> <profile>")


def handle_ipxe_delete_client(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Delete a MAC- or IP-specific iPXE script."""
    pxe_mgr = PXEBootManager()
    pxe_mgr.delete_client_ipxe_script(args.identifier)
    print(green(f"✓ Removed client iPXE script for {args.identifier}"))


def handle_ipxe_delete_mac(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Backward-compatible MAC-specific iPXE delete helper."""
    args.identifier = args.mac
    handle_ipxe_delete_client(mgr, args)


def handle_ipxe_list_clients(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """List generated iPXE client scripts."""
    pxe_mgr = PXEBootManager()
    scripts = pxe_mgr.list_client_ipxe_scripts()
    if not scripts:
        print(yellow("No generated iPXE client scripts found"))
        return
    print(f"\n{green('Generated iPXE client scripts')} ({len(scripts)} total):\n")
    for item in scripts:
        print(f"  {blue(item['identifier'])} ({item['type']})")
        print(f"    Path: {item['path']}")
        print(f"    URL:  {item['url']}")
        print()


def handle_ipxe_list_profiles(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """List dynamically discovered boot profiles."""
    pxe_mgr = PXEBootManager()
    profiles = pxe_mgr.discover_boot_profiles()
    print(f"\n{green('Discovered boot profiles')} ({len(profiles)} total):\n")
    for item in profiles:
        print(f"  {blue(item['key'])} [{item['source']}]")
        if item.get('path'):
            print(f"    Path: {item['path']}")
        if item.get('description'):
            print(f"    {item['description']}")
        print()


def handle_ipxe_translate(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Translate a PXELINUX profile into iPXE syntax."""
    pxe_mgr = PXEBootManager()
    script = pxe_mgr.translate_pxelinux_profile_to_ipxe(args.profile)
    if args.write:
        profile = pxe_mgr.validate_boot_profile(args.profile)
        path = pxe_mgr.ipxe_dir / f"{profile}.ipxe"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script, encoding="utf-8")
        print(green(f"✓ Wrote translated iPXE profile: {path}"))
    else:
        print(script)


def handle_ipxe_list_mac(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Backward-compatible list helper."""
    handle_ipxe_list_clients(mgr, args)


def handle_ipxe_snippet(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """Print the ISC DHCP iPXE chainloading snippet."""
    pxe_mgr = PXEBootManager()
    print(pxe_mgr.generate_isc_dhcp_ipxe_snippet())


def handle_pxe_list(mgr: DHCPManager, args: argparse.Namespace) -> None:
    """List legacy PXE symlink boot profiles."""
    pxe_mgr = PXEBootManager()
    configs = pxe_mgr.list_all_boot_configs()
    if not configs:
        print(yellow("No PXE boot links found"))
        return
    print(f"\n{green('PXE Boot Links')} ({len(configs)} total):\n")
    for cfg in configs:
        print(f"  {blue(cfg['ip'])} ({cfg['hex']})")
        print(f"    Device: {cfg['device']}")
        print(f"    Target: {cfg['target']}")
        print(f"    PXELINUX symlink target; iPXE dispatches by IP via {pxe_mgr.get_ipxe_script_tftp_filename()}")
        print()


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

    # -------------------- BOOT PROFILE --------------------
    boot_parser = subparsers.add_parser(
        "boot",
        help="Set a client's PXE/iPXE boot profile"
    )
    boot_parser.add_argument("ip", help="Client IP address")
    boot_parser.add_argument(
        "device",
        help="Boot profile/menu filename to assign. Use 'ipxe profiles' to list discovered choices."
    )
    boot_parser.set_defaults(func=handle_boot)

    # -------------------- PXE LIST --------------------
    pxe_list_parser = subparsers.add_parser(
        "pxe-list",
        aliases=["boot-list"],
        help="List existing legacy PXE symlink boot profiles"
    )
    pxe_list_parser.set_defaults(func=handle_pxe_list)

    # -------------------- iPXE --------------------
    ipxe_parser = subparsers.add_parser(
        "ipxe",
        help="Dynamic iPXE helpers"
    )
    ipxe_sub = ipxe_parser.add_subparsers(dest="ipxe_command", required=True)

    ipxe_script = ipxe_sub.add_parser("script", help="Print the default ipxe.ipxe dispatcher script")
    ipxe_script.set_defaults(func=handle_ipxe_script)

    ipxe_install = ipxe_sub.add_parser("install-default", help="Write ipxe.ipxe into the TFTP root")
    ipxe_install.set_defaults(func=handle_ipxe_install_default)

    ipxe_set_client = ipxe_sub.add_parser("set-client", help="Create/update an IP-specific iPXE script")
    ipxe_set_client.add_argument("identifier", help="Client IP address")
    ipxe_set_client.add_argument("device", help="Boot profile/menu filename")
    ipxe_set_client.set_defaults(func=handle_ipxe_set_client)

    ipxe_set_mac = ipxe_sub.add_parser("set-mac", help="Create/update a MAC-specific iPXE script")
    ipxe_set_mac.add_argument("mac", help="Client MAC address, e.g. aa:bb:cc:dd:ee:ff")
    ipxe_set_mac.add_argument("device", help="Boot profile/menu filename")
    ipxe_set_mac.set_defaults(func=handle_ipxe_set_mac)

    ipxe_delete_client = ipxe_sub.add_parser("delete-client", help="Delete an IP-specific iPXE script")
    ipxe_delete_client.add_argument("identifier", help="Client IP address")
    ipxe_delete_client.set_defaults(func=handle_ipxe_delete_client)

    ipxe_delete_mac = ipxe_sub.add_parser("delete-mac", help="Delete a MAC-specific iPXE script")
    ipxe_delete_mac.add_argument("mac", help="Client MAC address")
    ipxe_delete_mac.set_defaults(func=handle_ipxe_delete_mac)

    ipxe_list_clients = ipxe_sub.add_parser("list-clients", aliases=["list-mac"], help="List generated iPXE client scripts")
    ipxe_list_clients.set_defaults(func=handle_ipxe_list_clients)

    ipxe_profiles = ipxe_sub.add_parser("profiles", help="List discovered boot profiles for GUI/CLI drop-downs")
    ipxe_profiles.set_defaults(func=handle_ipxe_list_profiles)

    ipxe_translate = ipxe_sub.add_parser("translate", help="Translate a pxelinux.cfg profile into iPXE syntax")
    ipxe_translate.add_argument("profile", help="PXELINUX profile filename, e.g. centos-8.5")
    ipxe_translate.add_argument("--write", action="store_true", help="Write translated profile to <tftp-root>/ipxe/<profile>.ipxe")
    ipxe_translate.set_defaults(func=handle_ipxe_translate)

    ipxe_snippet = ipxe_sub.add_parser("snippet", help="Print ISC DHCP iPXE chainloading snippet")
    ipxe_snippet.set_defaults(func=handle_ipxe_snippet)
    
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
