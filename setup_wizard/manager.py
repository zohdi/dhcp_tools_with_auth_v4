"""First-run setup wizard for DHCP Manager.

This module intentionally keeps all bootstrap/install logic outside web.py.
It is conservative by design: validate, preview, backup, apply.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class InterfaceInfo:
    name: str
    ipv4: str = ""
    prefix: int = 0
    network: str = ""
    state: str = "unknown"


@dataclass
class SetupStatus:
    os_id: str
    os_like: str
    os_name: str
    supported: bool
    package_manager: str
    dhcp_package_installed: bool
    tftp_package_installed: bool
    syslinux_package_installed: bool
    dhcp_service_available: bool
    tftp_service_available: bool
    setup_completed: bool
    running_as_root: bool
    interfaces: List[InterfaceInfo]
    warnings: List[str]


class SetupValidationError(ValueError):
    """Raised when setup input validation fails."""


class SetupManager:
    STATE_PATH = Path(os.environ.get("DHCP_MANAGER_SETUP_STATE", "/var/lib/dhcp-manager/setup_state.json"))
    DHCP_DEFAULTS_PATH = Path("/etc/default/isc-dhcp-server")
    TFTPD_DEFAULTS_PATH = Path("/etc/default/tftpd-hpa")
    DHCP_CONF_PATH = Path("/etc/dhcp/dhcpd.conf")
    BACKUP_DIR = Path("/var/backups/dhcp-manager")

    DEBIAN_PACKAGES = ["isc-dhcp-server", "tftpd-hpa", "syslinux-common", "pxelinux"]
    RHEL_PACKAGES = ["dhcp-server", "tftp-server", "syslinux-tftpboot"]

    SAFE_BOOT_FILENAME_RE = re.compile(r"^[A-Za-z0-9._/:-]+$")
    IPXE_DISPATCHER_TFTP_PATH = "ipxe/ipxe.ipxe"
    IPXE_BIOS_BOOTLOADER = "undionly.kpxe"
    IPXE_UEFI_BOOTLOADER = "ipxe.efi"

    def __init__(self) -> None:
        self._last_apply_log: List[str] = []

    # ------------------------------------------------------------------
    # State / detection
    # ------------------------------------------------------------------
    def setup_completed(self) -> bool:
        if os.environ.get("DHCP_MANAGER_SKIP_SETUP") == "1":
            return True
        try:
            if self.STATE_PATH.exists():
                data = json.loads(self.STATE_PATH.read_text())
                return bool(data.get("setup_completed"))
        except Exception:
            return False
        return False

    def mark_completed(self, data: Dict[str, object]) -> None:
        payload = dict(data)
        payload["setup_completed"] = True
        payload["configured_at"] = datetime.now().isoformat(timespec="seconds")
        self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.STATE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def read_os_release(self) -> Dict[str, str]:
        path = Path("/etc/os-release")
        result: Dict[str, str] = {}
        if not path.exists():
            return result
        for raw in path.read_text(errors="ignore").splitlines():
            if "=" not in raw or raw.startswith("#"):
                continue
            key, value = raw.split("=", 1)
            result[key] = value.strip().strip('"')
        return result

    def get_package_manager(self, os_id: str, os_like: str) -> str:
        if shutil.which("apt") and (os_id in {"debian", "ubuntu", "linuxmint", "lubuntu"} or "debian" in os_like):
            return "apt"
        if shutil.which("dnf") and (os_id in {"rhel", "rocky", "almalinux", "centos", "fedora"} or "rhel" in os_like or "fedora" in os_like):
            return "dnf"
        if shutil.which("yum"):
            return "yum"
        return "unsupported"

    def is_package_installed(self, package_name: str, package_manager: str) -> bool:
        if package_manager == "apt":
            result = subprocess.run(["dpkg-query", "-W", "-f=${Status}", package_name], capture_output=True, text=True, check=False)
            return result.returncode == 0 and result.stdout.strip() == "install ok installed"
        if package_manager in {"dnf", "yum"}:
            return subprocess.run(["rpm", "-q", package_name], capture_output=True, text=True).returncode == 0
        return False

    def service_available(self, service: str) -> bool:
        if not shutil.which("systemctl"):
            return False
        return subprocess.run(["systemctl", "list-unit-files", f"{service}.service"], capture_output=True, text=True).returncode == 0

    def discover_interfaces(self) -> List[InterfaceInfo]:
        interfaces: List[InterfaceInfo] = []
        sys_class = Path("/sys/class/net")
        names = sorted(p.name for p in sys_class.iterdir()) if sys_class.exists() else []
        for name in names:
            if name == "lo":
                continue
            state_path = sys_class / name / "operstate"
            state = state_path.read_text().strip() if state_path.exists() else "unknown"
            ipv4, prefix, network = self._interface_ipv4(name)
            interfaces.append(InterfaceInfo(name=name, ipv4=ipv4, prefix=prefix, network=network, state=state))
        return interfaces

    def _interface_ipv4(self, name: str) -> Tuple[str, int, str]:
        if shutil.which("ip"):
            result = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", name], capture_output=True, text=True)
            if result.returncode == 0:
                # Format: 2: eth0    inet 192.168.1.5/24 brd ...
                for part in result.stdout.split():
                    if "/" not in part:
                        continue
                    try:
                        addr, prefix_raw = part.split("/", 1)
                        prefix = int(prefix_raw)
                        network = ip_network(f"{addr}/{prefix}", strict=False)
                        return addr, prefix, str(network)
                    except Exception:
                        continue
        return "", 0, ""

    def status(self) -> SetupStatus:
        os_release = self.read_os_release()
        os_id = os_release.get("ID", "unknown").lower()
        os_like = os_release.get("ID_LIKE", "").lower()
        os_name = os_release.get("PRETTY_NAME", os_id)
        package_manager = self.get_package_manager(os_id, os_like)
        supported = package_manager in {"apt", "dnf", "yum"}
        warnings: List[str] = []
        if package_manager in {"dnf", "yum"}:
            warnings.append("RHEL/Rocky/Fedora detection is included, but the wizard is safest/tested first on Debian/Ubuntu/Lubuntu.")
        if package_manager == "unsupported":
            warnings.append("Unsupported OS/package manager. Automatic package installation is disabled.")

        dhcp_pkg = "isc-dhcp-server" if package_manager == "apt" else "dhcp-server"
        tftp_pkg = "tftpd-hpa" if package_manager == "apt" else "tftp-server"
        syslinux_pkg = "syslinux-common" if package_manager == "apt" else "syslinux-tftpboot"
        dhcp_service = "isc-dhcp-server" if package_manager == "apt" else "dhcpd"
        tftp_service = "tftpd-hpa" if package_manager == "apt" else "tftp"

        return SetupStatus(
            os_id=os_id,
            os_like=os_like,
            os_name=os_name,
            supported=supported,
            package_manager=package_manager,
            dhcp_package_installed=self.is_package_installed(dhcp_pkg, package_manager),
            tftp_package_installed=self.is_package_installed(tftp_pkg, package_manager),
            syslinux_package_installed=self.is_package_installed(syslinux_pkg, package_manager),
            dhcp_service_available=self.service_available(dhcp_service),
            tftp_service_available=self.service_available(tftp_service),
            setup_completed=self.setup_completed(),
            running_as_root=(os.geteuid() == 0 if hasattr(os, "geteuid") else False),
            interfaces=self.discover_interfaces(),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Validation / rendering
    # ------------------------------------------------------------------
    def default_form_data(self) -> Dict[str, str]:
        interfaces = self.discover_interfaces()
        chosen = next((i for i in interfaces if i.ipv4), interfaces[0] if interfaces else InterfaceInfo(name=""))
        network = ip_network(chosen.network, strict=False) if chosen.network else ip_network("192.168.33.0/24")
        hosts = list(network.hosts()) if network.num_addresses <= 4096 else []
        range_start = str(hosts[99]) if len(hosts) > 150 else str(hosts[9] if len(hosts) > 20 else network.network_address + 10)
        range_end = str(hosts[-55]) if len(hosts) > 150 else str(hosts[-10] if len(hosts) > 20 else network.broadcast_address - 10)
        next_server = chosen.ipv4 or self._guess_primary_ip() or str(network.network_address + 1)
        return {
            "interface": chosen.name,
            "managed_subnet": str(network.network_address),
            "netmask": str(network.netmask),
            "range_start": range_start,
            "range_end": range_end,
            "router": str(network.network_address + 1),
            "dns_servers": "8.8.8.8, 1.1.1.1",
            "next_server": next_server,
            "boot_filename": "pxelinux.0",
            "tftp_root": "/var/lib/tftpboot",
            "install_packages": "yes",
        }

    def _guess_primary_ip(self) -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except Exception:
            return ""

    def validate_and_prepare(self, raw: Dict[str, str]) -> Dict[str, object]:
        interface = (raw.get("interface") or "").strip()
        if not interface or not re.match(r"^[A-Za-z0-9_.:-]+$", interface):
            raise SetupValidationError("Invalid or empty network interface name.")
        if interface == "lo":
            raise SetupValidationError("Do not run DHCP on loopback interface lo.")

        managed_subnet_ip = self._parse_ipv4(raw.get("managed_subnet"), "Managed subnet")
        netmask = (raw.get("netmask") or "").strip()
        try:
            if netmask.isdigit():
                managed_network = ip_network(f"{managed_subnet_ip}/{int(netmask)}", strict=False)
            else:
                managed_network = ip_network(f"{managed_subnet_ip}/{netmask}", strict=False)
        except Exception as exc:
            raise SetupValidationError(f"Invalid subnet/netmask: {exc}") from exc

        range_start = self._parse_ipv4(raw.get("range_start"), "Range start")
        range_end = self._parse_ipv4(raw.get("range_end"), "Range end")
        if range_start not in managed_network or range_end not in managed_network:
            raise SetupValidationError("DHCP range must be inside the managed subnet.")
        if int(range_start) >= int(range_end):
            raise SetupValidationError("DHCP range start must be lower than range end.")

        router_raw = (raw.get("router") or "").strip()
        router = self._parse_ipv4(router_raw, "Router/gateway") if router_raw else None
        warnings: List[str] = []
        if router and router not in managed_network:
            warnings.append("Router/gateway is outside the managed subnet. This can be valid for special routed/relay setups, but usually it is a mistake.")

        dns_servers = self._parse_dns_servers(raw.get("dns_servers") or "")
        next_server = self._parse_ipv4(raw.get("next_server"), "Next server")
        boot_filename = (raw.get("boot_filename") or "").strip()
        if not boot_filename or boot_filename.startswith("/") or ".." in boot_filename or not self.SAFE_BOOT_FILENAME_RE.match(boot_filename):
            raise SetupValidationError("Invalid boot filename. Use a safe relative TFTP path such as pxelinux.0 or ipxe/ipxe.ipxe.")

        tftp_root = Path((raw.get("tftp_root") or "").strip())
        if not tftp_root.is_absolute() or str(tftp_root) in {"/", "/etc", "/bin", "/usr", "/var"}:
            raise SetupValidationError("Invalid TFTP root. Use an absolute dedicated directory such as /var/lib/tftpboot.")

        interfaces = {iface.name: iface for iface in self.discover_interfaces()}
        selected = interfaces.get(interface)
        local_network = None
        empty_local_subnet_required = False
        if selected and selected.network:
            local_network = ip_network(selected.network, strict=False)
            if local_network != managed_network:
                empty_local_subnet_required = True
                warnings.append(
                    f"Selected interface {interface} is on {local_network}, but DHCP managed subnet is {managed_network}. "
                    "This is valid only with DHCP relay/VLAN/routing. Wizard will add an empty local subnet declaration so dhcpd can bind cleanly."
                )
        else:
            warnings.append("Selected interface has no detected IPv4 address. DHCP may fail unless the interface is configured before service start.")

        prepared = {
            "interface": interface,
            "managed_network": managed_network,
            "range_start": range_start,
            "range_end": range_end,
            "router": router,
            "dns_servers": dns_servers,
            "next_server": next_server,
            "boot_filename": boot_filename,
            "ipxe_dispatcher": self.IPXE_DISPATCHER_TFTP_PATH,
            "ipxe_bios_bootloader": self.IPXE_BIOS_BOOTLOADER,
            "ipxe_uefi_bootloader": self.IPXE_UEFI_BOOTLOADER,
            "tftp_root": tftp_root,
            "selected_interface": selected,
            "local_network": local_network,
            "empty_local_subnet_required": empty_local_subnet_required,
            "warnings": warnings,
            "install_packages": (raw.get("install_packages") == "yes"),
        }
        prepared["dhcp_conf"] = self.render_dhcp_config(prepared)
        prepared["dhcp_defaults"] = self.render_dhcp_defaults(prepared)
        prepared["tftpd_defaults"] = self.render_tftpd_defaults(prepared)
        return prepared

    def _parse_ipv4(self, value: Optional[str], label: str) -> IPv4Address:
        try:
            parsed = ip_address((value or "").strip())
            if parsed.version != 4:
                raise ValueError("IPv6 is not supported here")
            return parsed  # type: ignore[return-value]
        except Exception as exc:
            raise SetupValidationError(f"Invalid {label}: {value}") from exc

    def _parse_dns_servers(self, raw: str) -> List[IPv4Address]:
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        if not parts:
            raise SetupValidationError("At least one DNS server is required.")
        return [self._parse_ipv4(p, "DNS server") for p in parts]

    def render_dhcp_config(self, data: Dict[str, object]) -> str:
        managed_network: IPv4Network = data["managed_network"]  # type: ignore[assignment]
        lines = [
            "# Generated by DHCP Manager setup wizard.",
            "# Review before editing manually.",
            "authoritative;",
            "default-lease-time 600;",
            "max-lease-time 7200;",
            "ddns-update-style none;",
            "",
        ]
        local_network: Optional[IPv4Network] = data.get("local_network")  # type: ignore[assignment]
        if data.get("empty_local_subnet_required") and local_network:
            lines.extend([
                "# Local interface subnet declaration.",
                "# Required so isc-dhcp-server/dhcpd can bind to the selected interface.",
                f"subnet {local_network.network_address} netmask {local_network.netmask} {{",
                "}",
                "",
            ])
        lines.extend([
            "# Managed PXE subnet.",
            f"subnet {managed_network.network_address} netmask {managed_network.netmask} {{",
            f"    range {data['range_start']} {data['range_end']};",
        ])
        if data.get("router"):
            lines.append(f"    option routers {data['router']};")
        dns = ", ".join(str(x) for x in data["dns_servers"])  # type: ignore[index]
        lines.extend([
            f"    option domain-name-servers {dns};",
            f"    next-server {data['next_server']};",
            "",
            "    # iPXE support is inserted automatically by the setup wizard.",
            "    # Clients already running iPXE receive the dispatcher script.",
            "    # Regular PXE clients receive the selected default boot filename.",
            "    if exists user-class and option user-class = \"iPXE\" {",
            f"        filename \"{self.IPXE_DISPATCHER_TFTP_PATH}\";",
            "    } else {",
            f"        filename \"{data['boot_filename']}\";",
            "    }",
            "}",
            "",
            "# Static host reservations managed by DHCP Manager will be appended below.",
        ])
        return "\n".join(lines) + "\n"

    def render_dhcp_defaults(self, data: Dict[str, object]) -> str:
        return (
            "# Generated by DHCP Manager setup wizard.\n"
            f"INTERFACESv4=\"{data['interface']}\"\n"
            "INTERFACESv6=\"\"\n"
        )

    def render_tftpd_defaults(self, data: Dict[str, object]) -> str:
        return (
            "# Generated by DHCP Manager setup wizard.\n"
            "TFTP_USERNAME=\"tftp\"\n"
            f"TFTP_DIRECTORY=\"{data['tftp_root']}\"\n"
            "TFTP_ADDRESS=\":69\"\n"
            "TFTP_OPTIONS=\"--secure\"\n"
        )

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def apply(self, data: Dict[str, object]) -> List[str]:
        self._last_apply_log = []
        status = self.status()
        if not status.running_as_root:
            raise PermissionError("Setup must run as root because it installs packages and writes /etc service configs. Start with: sudo python3 web.py")
        if not status.supported:
            raise RuntimeError("Automatic setup is not supported on this OS/package manager.")

        if data.get("install_packages"):
            self.install_packages(status.package_manager)

        self.backup_paths([self.DHCP_CONF_PATH, self.DHCP_DEFAULTS_PATH, self.TFTPD_DEFAULTS_PATH])
        tftp_root: Path = data["tftp_root"]  # type: ignore[assignment]
        self.write_file(self.DHCP_CONF_PATH, str(data["dhcp_conf"]))
        self.write_file(self.DHCP_DEFAULTS_PATH, str(data["dhcp_defaults"]))
        self.write_file(self.TFTPD_DEFAULTS_PATH, str(data["tftpd_defaults"]))
        self.ensure_tftp_tree(tftp_root)
        copied, missing = self.copy_pxe_files(tftp_root)
        self.write_default_pxelinux_menu(tftp_root)
        self.write_default_ipxe_dispatcher(tftp_root)

        self.run(["dhcpd", "-t", "-cf", str(self.DHCP_CONF_PATH)], "Validate DHCP syntax", check=True)
        self.enable_restart_services(status.package_manager)

        self.mark_completed({
            "os": status.os_name,
            "package_manager": status.package_manager,
            "interface": data["interface"],
            "managed_network": str(data["managed_network"]),
            "tftp_root": str(tftp_root),
            "boot_filename": data["boot_filename"],
            "ipxe_dispatcher": self.IPXE_DISPATCHER_TFTP_PATH,
            "pxe_files_copied": copied,
            "pxe_files_missing": missing,
        })
        self._last_apply_log.append("Setup completed successfully.")
        return self._last_apply_log

    def install_packages(self, package_manager: str) -> None:
        if package_manager == "apt":
            self.run(["apt", "update"], "Update apt package index", check=True)
            self.run(["apt", "install", "-y"] + self.DEBIAN_PACKAGES, "Install DHCP/TFTP/PXE packages", check=True)
        elif package_manager in {"dnf", "yum"}:
            cmd = [package_manager, "install", "-y", "--releasever=9" ] + self.RHEL_PACKAGES
            self.run(cmd, "Install DHCP/TFTP/PXE packages", check=True)
        else:
            raise RuntimeError(f"Unsupported package manager: {package_manager}")

    def backup_paths(self, paths: List[Path]) -> None:
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for path in paths:
            if path.exists():
                target = self.BACKUP_DIR / f"{path.name}.{stamp}.bak"
                shutil.copy2(path, target)
                self._last_apply_log.append(f"Backed up {path} -> {target}")

    def write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self._last_apply_log.append(f"Wrote {path}")

    def ensure_tftp_tree(self, tftp_root: Path) -> None:
        (tftp_root / "pxelinux.cfg").mkdir(parents=True, exist_ok=True)
        (tftp_root / "ipxe" / "clients").mkdir(parents=True, exist_ok=True)
        try:
            shutil.chown(tftp_root, user="tftp", group="tftp")
        except Exception:
            self._last_apply_log.append("Could not chown TFTP root to tftp:tftp; continuing.")
        self._last_apply_log.append(f"Ensured TFTP tree under {tftp_root}")

    def copy_pxe_files(self, tftp_root: Path) -> Tuple[List[str], List[str]]:
        file_candidates = {
            "pxelinux.0": ["/usr/lib/PXELINUX/pxelinux.0", "/usr/share/syslinux/pxelinux.0", "/usr/lib/syslinux/pxelinux.0"],
            "ldlinux.c32": ["/usr/lib/syslinux/modules/bios/ldlinux.c32", "/usr/share/syslinux/ldlinux.c32"],
            "menu.c32": ["/usr/lib/syslinux/modules/bios/menu.c32", "/usr/share/syslinux/menu.c32"],
            "vesamenu.c32": ["/usr/lib/syslinux/modules/bios/vesamenu.c32", "/usr/share/syslinux/vesamenu.c32"],
            "libutil.c32": ["/usr/lib/syslinux/modules/bios/libutil.c32", "/usr/share/syslinux/libutil.c32"],
            "chain.c32": ["/usr/lib/syslinux/modules/bios/chain.c32", "/usr/share/syslinux/chain.c32"],
            "libcom32.c32": ["/usr/lib/syslinux/modules/bios/libcom32.c32", "/usr/share/syslinux/libcom32.c32"],
            "undionly.kpxe": ["/usr/lib/ipxe/undionly.kpxe", "/usr/share/ipxe/undionly.kpxe", "/usr/lib/ipxe/undionly.kkpxe"],
            "ipxe.efi": ["/usr/lib/ipxe/ipxe.efi", "/usr/share/ipxe/ipxe.efi", "/usr/share/ipxe/x86_64-efi/ipxe.efi", "/usr/share/ipxe/ipxe-x86_64.efi"],
            "snponly.efi": ["/usr/lib/ipxe/snponly.efi", "/usr/share/ipxe/snponly.efi", "/usr/share/ipxe/x86_64-efi/snponly.efi", "/usr/share/ipxe/snponly-x86_64.efi"],
        }
        copied: List[str] = []
        missing: List[str] = []
        for filename, candidates in file_candidates.items():
            source = next((Path(p) for p in candidates if Path(p).exists()), None)
            if source:
                shutil.copy2(source, tftp_root / filename)
                copied.append(filename)
                self._last_apply_log.append(f"Copied {filename} from {source}")
            else:
                missing.append(filename)
                self._last_apply_log.append(f"PXE file not found locally: {filename}")
        return copied, missing

    def write_default_pxelinux_menu(self, tftp_root: Path) -> None:
        default_path = tftp_root / "pxelinux.cfg" / "default"
        if default_path.exists():
            self._last_apply_log.append(f"PXELINUX default menu already exists: {default_path}")
            return
        default_path.write_text(
            "DEFAULT menu.c32\n"
            "PROMPT 0\n"
            "TIMEOUT 100\n"
            "ONTIMEOUT local\n\n"
            "MENU TITLE DHCP Manager PXE Boot Menu\n\n"
            "LABEL local\n"
            "    MENU LABEL Boot from local drive\n"
            "    LOCALBOOT 0\n"
        )
        self._last_apply_log.append(f"Created {default_path}")

    def write_default_ipxe_dispatcher(self, tftp_root: Path) -> None:
        dispatcher = tftp_root / "ipxe" / "ipxe.ipxe"
        if dispatcher.exists():
            self._last_apply_log.append(f"iPXE dispatcher already exists: {dispatcher}")
            return
        dispatcher.write_text(
            "#!ipxe\n"
            "# DHCP Manager iPXE dispatcher\n"
            "# Generated by DHCP Manager setup wizard - safe to regenerate.\n"
            "dhcp || goto failed\n"
            "set ipxe-base http://${next-server}:5000/ipxe\n"
            "echo DHCP Manager iPXE dispatcher\n"
            "echo MAC: ${net0/mac}  IP: ${ip}\n"
            "echo Trying IP-specific client script...\n"
            "chain --replace ${ipxe-base}/clients/${ip}.ipxe || goto try_default\n"
            "\n"
            ":try_default\n"
            "echo Trying default iPXE profile...\n"
            "chain --replace ${ipxe-base}/default.ipxe || goto local_disk\n"
            "\n"
            ":local_disk\n"
            "echo No dedicated iPXE file found. Booting first local disk...\n"
            "sanboot --no-describe --drive 0x80 || goto failed\n"
            "exit 0\n"
            "\n"
            ":failed\n"
            "echo iPXE boot failed. Returning to firmware shortly.\n"
            "sleep 10\n"
            "exit 1\n"
        )
        self._last_apply_log.append(f"Created {dispatcher}")

    def enable_restart_services(self, package_manager: str) -> None:
        if package_manager == "apt":
            services = ["tftpd-hpa", "isc-dhcp-server"]
        else:
            services = ["tftp", "dhcpd"]
        for service in services:
            self.run(["systemctl", "enable", "--now", service], f"Enable/start {service}", check=False)
            self.run(["systemctl", "restart", service], f"Restart {service}", check=True)

    def run(self, cmd: List[str], label: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        self._last_apply_log.append(f"$ {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.stdout.strip():
            self._last_apply_log.append(result.stdout.strip()[-4000:])
        if result.stderr.strip():
            self._last_apply_log.append(result.stderr.strip()[-4000:])
        if check and result.returncode != 0:
            raise RuntimeError(f"{label} failed: {result.stderr.strip() or result.stdout.strip()}")
        return result

    @staticmethod
    def serialize_for_session(data: Dict[str, object]) -> Dict[str, object]:
        serializable: Dict[str, object] = {}
        for key, value in data.items():
            if isinstance(value, (IPv4Address, IPv4Network, Path)):
                serializable[key] = str(value)
            elif isinstance(value, InterfaceInfo):
                serializable[key] = asdict(value)
            elif isinstance(value, list):
                serializable[key] = [str(v) for v in value]
            elif key in {"dhcp_conf", "dhcp_defaults", "tftpd_defaults", "interface", "boot_filename", "ipxe_dispatcher", "ipxe_bios_bootloader", "ipxe_uefi_bootloader", "warnings", "install_packages", "empty_local_subnet_required"}:
                serializable[key] = value
        return serializable

    def deserialize_from_session(self, data: Dict[str, object]) -> Dict[str, object]:
        raw = {
            "interface": str(data.get("interface", "")),
            "managed_subnet": str(data.get("managed_network", "192.168.33.0")).split("/", 1)[0],
            "netmask": str(ip_network(str(data.get("managed_network", "192.168.33.0/24")), strict=False).netmask),
            "range_start": str(data.get("range_start", "")),
            "range_end": str(data.get("range_end", "")),
            "router": str(data.get("router", "")) if data.get("router") else "",
            "dns_servers": ", ".join(data.get("dns_servers", [])) if isinstance(data.get("dns_servers"), list) else str(data.get("dns_servers", "")),
            "next_server": str(data.get("next_server", "")),
            "boot_filename": str(data.get("boot_filename", "pxelinux.0")),
            "tftp_root": str(data.get("tftp_root", "/var/lib/tftpboot")),
            "install_packages": "yes" if data.get("install_packages") else "no",
        }
        return self.validate_and_prepare(raw)
