"""
PXE/iPXE Boot Manager.

Keeps the original PXELINUX workflow working while adding a static iPXE
launcher that can dispatch to per-client scripts by MAC address or IP address.

Directory model, assuming TFTP_BASE_DIR=/var/lib/tftpboot/pxelinux.cfg:

  /var/lib/tftpboot/pxelinux.cfg/default        # existing PXELINUX menu file
  /var/lib/tftpboot/pxelinux.cfg/rocky-9        # existing PXELINUX menu file
  /var/lib/tftpboot/pxelinux.cfg/C0A8010A -> rocky-9

  /var/lib/tftpboot/ipxe/ipxe.ipxe             # default iPXE dispatcher
  /var/lib/tftpboot/ipxe/default.ipxe          # optional default iPXE menu/profile
  /var/lib/tftpboot/ipxe/rocky-9.ipxe          # optional iPXE profile
  /var/lib/tftpboot/ipxe/clients/<ip>.ipxe     # generated client override
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from config import config
from exceptions import PXEBootError, ValidationError
from utils.logger import get_logger
from utils.validators import validate_ip_address, validate_mac_address


@dataclass(frozen=True)
class BootProfile:
    """User-facing boot profile metadata."""

    key: str
    label: str
    source: str
    path: str = ""
    description: str = ""


class PXEBootManager:
    """Manage legacy PXELINUX links and iPXE per-client overrides."""

    SAFE_PROFILE_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
    CLIENT_MAC_RE = re.compile(r"^[0-9a-f]{12}\.ipxe$", re.IGNORECASE)
    CLIENT_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}\.ipxe$")

    BUILTIN_LOCAL_PROFILES: Dict[str, BootProfile] = {
        "default": BootProfile(
            key="default",
            label="Default",
            source="builtin",
            description="No client override; dispatcher uses ipxe/default.ipxe if present, otherwise local disk.",
        ),
        "hdd0": BootProfile(key="hdd0", label="Local disk 0", source="builtin", description="Boot first local disk."),
        "hdd1": BootProfile(key="hdd1", label="Local disk 1", source="builtin", description="Boot second local disk."),
        "boot_local_hdd0": BootProfile(
            key="boot_local_hdd0",
            label="Boot local HDD 0",
            source="builtin",
            description="Boot first local disk using iPXE sanboot drive 0x80.",
        ),
        "boot_local_hdd1": BootProfile(
            key="boot_local_hdd1",
            label="Boot local HDD 1",
            source="builtin",
            description="Boot second local disk using iPXE sanboot drive 0x81.",
        ),
        "boot_local_usb": BootProfile(
            key="boot_local_usb",
            label="Boot local USB / next firmware device",
            source="builtin",
            description="Exit iPXE and return to firmware boot order, useful for USB/local fallback.",
        ),
    }

    LEGACY_ALIAS_TARGETS: Dict[str, str] = {
        "default": config.PXE_DEFAULT_MENU,
        "hd0": config.PXE_DISK0_MENU,
        "hd1": config.PXE_DISK1_MENU,
        "hdd0": config.PXE_DISK0_MENU,
        "hdd1": config.PXE_DISK1_MENU,
    }

    IPXE_LOCAL_BOOT_PROFILES: Dict[str, str] = {
        "hd0": "hdd0",
        "hdd0": "hdd0",
        "boot_local_hdd0": "hdd0",
        "hd1": "hdd1",
        "hdd1": "hdd1",
        "boot_local_hdd1": "hdd1",
        "boot_local_usb": "usb",
    }

    def __init__(self, tftp_dir: Optional[Path] = None):
        self.tftp_dir = Path(tftp_dir or config.TFTP_BASE_DIR)
        self.logger = get_logger()

    # ============================================================
    #                   PATH HELPERS
    # ============================================================

    @property
    def tftp_root(self) -> Path:
        """Return the TFTP root directory."""
        if self.tftp_dir.name == "pxelinux.cfg":
            return self.tftp_dir.parent
        return self.tftp_dir

    @property
    def pxelinux_cfg_dir(self) -> Path:
        """Return the pxelinux.cfg directory used for legacy menu files."""
        if self.tftp_dir.name == "pxelinux.cfg":
            return self.tftp_dir
        return self.tftp_root / "pxelinux.cfg"

    @property
    def ipxe_dir(self) -> Path:
        return self.tftp_root / config.IPXE_DIR

    @property
    def ipxe_clients_dir(self) -> Path:
        return self.ipxe_dir / config.IPXE_CLIENTS_DIR

    def get_ipxe_script_path(self) -> Path:
        """Return the TFTP path of the main iPXE dispatcher."""
        filename = Path(config.IPXE_SCRIPT_FILENAME)
        if filename.is_absolute():
            return filename
        return self.tftp_root / filename

    def get_ipxe_script_tftp_filename(self) -> str:
        """Return the TFTP filename DHCP should hand to clients already running iPXE."""
        return str(config.IPXE_SCRIPT_FILENAME)

    def get_client_script_path(self, identifier: str) -> Path:
        """Return generated per-client iPXE script path.

        iPXE client overrides are intentionally keyed by IPv4 address only.
        After the dispatcher runs `dhcp`, iPXE can reliably expand `${ip}`,
        and IP filenames such as `192.168.1.10.ipxe` are much easier to
        inspect and manage than MAC filenames containing separators.
        """
        ident = self.normalize_ipxe_client_identifier(identifier)
        return self.ipxe_clients_dir / f"{ident}.ipxe"

    def get_profile_ipxe_path(self, boot_profile: str) -> Optional[Path]:
        """Return an iPXE profile path if it exists for the supplied profile name."""
        profile = self.validate_boot_profile(boot_profile)
        candidates = [self.ipxe_dir / profile]
        if not profile.endswith(".ipxe"):
            candidates.append(self.ipxe_dir / f"{profile}.ipxe")
        for path in candidates:
            if path.exists() and path.is_file() and not path.is_symlink():
                return path
        return None

    def get_pxelinux_profile_path(self, boot_profile: str) -> Optional[Path]:
        """Return a PXELINUX menu file path if it exists and is a real file."""
        profile = self.validate_boot_profile(boot_profile)
        path = self.pxelinux_cfg_dir / profile
        if path.exists() and path.is_file() and not path.is_symlink():
            return path
        alias_target = self.LEGACY_ALIAS_TARGETS.get(profile)
        if alias_target:
            alias_path = self.pxelinux_cfg_dir / alias_target
            if alias_path.exists() and alias_path.is_file() and not alias_path.is_symlink():
                return alias_path
        return None

    # ============================================================
    #                   VALIDATION / NORMALIZATION
    # ============================================================

    @classmethod
    def validate_boot_profile(cls, profile: str) -> str:
        """Validate a dynamic boot profile/menu filename."""
        if not profile or not isinstance(profile, str):
            raise ValidationError("Boot profile cannot be empty")
        profile = profile.strip()
        if "/" in profile or "\\" in profile or profile in {".", ".."} or ".." in profile:
            raise ValidationError(f"Invalid boot profile path: {profile}")
        if not cls.SAFE_PROFILE_RE.match(profile):
            raise ValidationError(
                f"Invalid boot profile name: {profile}. Use only letters, numbers, dot, underscore, dash or colon."
            )
        return profile

    @staticmethod
    def normalize_mac(mac: Optional[str]) -> str:
        """Normalize a MAC address to aa:bb:cc:dd:ee:ff."""
        return validate_mac_address(mac or "").replace("-", ":")

    @classmethod
    def normalize_client_identifier(cls, identifier: str) -> str:
        """Normalize a client identifier that may be a MAC address or IPv4 address.

        Kept for backward compatibility with older CLI helpers. New generated
        iPXE client files use `normalize_ipxe_client_identifier()` and therefore
        accept IPv4 addresses only.
        """
        if not identifier or not isinstance(identifier, str):
            raise ValidationError("Client identifier cannot be empty")
        ident = identifier.strip().lower()
        try:
            return cls.normalize_mac(ident)
        except ValidationError:
            return validate_ip_address(ident)

    @staticmethod
    def normalize_ipxe_client_identifier(identifier: str) -> str:
        """Normalize an iPXE generated client filename identifier.

        We use only the IPv4 address for generated iPXE files because the
        default dispatcher can chain `/ipxe/clients/${ip}.ipxe`.
        """
        if not identifier or not isinstance(identifier, str):
            raise ValidationError("iPXE client identifier must be an IPv4 address")
        return validate_ip_address(identifier.strip())

    @staticmethod
    def ip_to_hex(ip: str) -> str:
        """Convert an IPv4 address to the uppercase PXELINUX hex filename."""
        validated_ip = validate_ip_address(ip)
        try:
            return "".join(f"{int(octet):02X}" for octet in validated_ip.split("."))
        except ValueError as exc:
            raise ValidationError(f"Failed to convert IP to hex: {exc}") from exc

    @staticmethod
    def hex_to_ip(hex_str: str) -> str:
        """Convert an 8-character PXELINUX hex filename to IPv4 dotted decimal."""
        if not hex_str or len(hex_str) != 8:
            raise ValidationError(f"Invalid hex string length: {hex_str}")
        try:
            ip = ".".join(str(int(hex_str[i : i + 2], 16)) for i in range(0, 8, 2))
            validate_ip_address(ip)
            return ip
        except (ValueError, ValidationError) as exc:
            raise ValidationError(f"Failed to convert hex to IP: {exc}") from exc

    # ============================================================
    #                   DISCOVERY
    # ============================================================

    @staticmethod
    def _is_hidden_or_generated(path: Path) -> bool:
        return path.name.startswith(".") or path.name.endswith("~")

    def _profile_sort_key(self, item: BootProfile) -> tuple:
        priority = {
            "default": 0,
            "hdd0": 1,
            "hd0": 1,
            "hdd1": 2,
            "hd1": 2,
            "boot_local_hdd0": 3,
            "boot_local_hdd1": 4,
            "boot_local_usb": 5,
        }.get(item.key, 10)
        return (priority, item.key.lower())

    def discover_boot_profiles(self) -> List[Dict[str, str]]:
        """Discover boot choices for the GUI/CLI.

        Sources:
          * Built-in default/hdd0/hdd1 local boot aliases.
          * Regular non-symlink files under pxelinux.cfg.
          * Regular non-generated .ipxe files under the top-level ipxe directory.

        This means adding pxelinux.cfg/rocky-9 or ipxe/rocky-9.ipxe is enough
        for the web GUI Boot Device drop-down to show it automatically.
        """
        profiles: Dict[str, BootProfile] = dict(self.BUILTIN_LOCAL_PROFILES)

        if self.pxelinux_cfg_dir.exists():
            for path in sorted(self.pxelinux_cfg_dir.iterdir()):
                if self._is_hidden_or_generated(path) or path.is_symlink() or not path.is_file():
                    continue
                try:
                    key = self.validate_boot_profile(path.name)
                except ValidationError:
                    self.logger.warning("Skipping unsafe PXELINUX menu filename: %s", path.name)
                    continue
                profiles[key] = BootProfile(key=key, label=key, source="pxelinux", path=str(path))

        if self.ipxe_dir.exists():
            dispatcher_name = self.get_ipxe_script_path().name
            for path in sorted(self.ipxe_dir.iterdir()):
                if self._is_hidden_or_generated(path) or path.is_symlink() or not path.is_file():
                    continue
                if path.name == dispatcher_name:
                    continue
                if self.CLIENT_MAC_RE.match(path.name) or self.CLIENT_IP_RE.match(path.name):
                    continue
                key = path.name[:-5] if path.name.endswith(".ipxe") else path.name
                try:
                    key = self.validate_boot_profile(key)
                except ValidationError:
                    self.logger.warning("Skipping unsafe iPXE profile filename: %s", path.name)
                    continue
                existing = profiles.get(key)
                source = "ipxe+pxelinux" if existing and existing.source == "pxelinux" else "ipxe"
                profiles[key] = BootProfile(key=key, label=key, source=source, path=str(path))

        return [profile.__dict__ for profile in sorted(profiles.values(), key=self._profile_sort_key)]

    def boot_profile_exists(self, boot_profile: str) -> bool:
        """Return True if a boot profile is built-in or discovered on disk."""
        profile = self.validate_boot_profile(boot_profile)
        if profile in self.BUILTIN_LOCAL_PROFILES:
            return True
        return self.get_pxelinux_profile_path(profile) is not None or self.get_profile_ipxe_path(profile) is not None

    # ============================================================
    #                   LEGACY PXELINUX HELPERS
    # ============================================================

    def get_link_path(self, ip: str) -> Path:
        """Return pxelinux.cfg symlink path for a client IP."""
        return self.pxelinux_cfg_dir / self.ip_to_hex(ip)

    def resolve_legacy_menu_target(self, boot_profile: str) -> str:
        """Return the symlink target for a legacy PXELINUX boot profile."""
        profile = self.validate_boot_profile(boot_profile)
        if profile in self.LEGACY_ALIAS_TARGETS:
            alias_target = self.LEGACY_ALIAS_TARGETS[profile]
            if (self.pxelinux_cfg_dir / alias_target).exists():
                return alias_target
            if (self.pxelinux_cfg_dir / profile).exists():
                return profile
            return alias_target
        if self.get_pxelinux_profile_path(profile):
            return profile
        # Allow setting an iPXE-only profile without breaking legacy clients:
        # legacy PXE falls back to the default menu while iPXE gets the exact profile.
        return config.PXE_DEFAULT_MENU

    def create_boot_link(self, ip: str, boot_profile: str) -> None:
        """Create/update pxelinux.cfg/<IP_HEX> symlink for legacy PXE clients."""
        validate_ip_address(ip)
        profile = self.validate_boot_profile(boot_profile)
        target = self.resolve_legacy_menu_target(profile)
        link_path = self.get_link_path(ip)

        try:
            self.pxelinux_cfg_dir.mkdir(parents=True, exist_ok=True)
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
                self.logger.info("Removed existing PXE link for %s", ip)
            link_path.symlink_to(target)
            self.logger.info("Created PXE link: %s -> %s", link_path.name, target)
        except OSError as exc:
            raise PXEBootError(f"Failed to create PXE boot link for {ip}: {exc}") from exc

    def delete_boot_link(self, ip: str) -> None:
        """Delete pxelinux.cfg/<IP_HEX> symlink for a client IP."""
        validate_ip_address(ip)
        link_path = self.get_link_path(ip)
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
                self.logger.info("Deleted PXE link for %s: %s", ip, link_path.name)
            else:
                self.logger.warning("No PXE link found for %s", ip)
        except OSError as exc:
            raise PXEBootError(f"Failed to delete PXE boot link for {ip}: {exc}") from exc

    def get_boot_target(self, ip: str) -> Optional[str]:
        """Return the current legacy PXE symlink target for a client IP."""
        validate_ip_address(ip)
        link_path = self.get_link_path(ip)
        try:
            if link_path.is_symlink():
                return os.readlink(str(link_path))
            return None
        except OSError as exc:
            self.logger.error("Failed to read PXE link for %s: %s", ip, exc)
            return None

    def get_boot_device(self, ip: str) -> str:
        """Return normalized boot profile key for a client IP."""
        try:
            target = self.get_boot_target(ip)
            if not target:
                return "default"
            reverse_alias = {v: k for k, v in self.LEGACY_ALIAS_TARGETS.items()}
            if target in reverse_alias:
                return reverse_alias[target]
            return target
        except Exception as exc:
            self.logger.error("Error getting boot device for %s: %s", ip, exc)
            return "default"

    def list_all_boot_configs(self) -> List[Dict[str, str]]:
        """List all legacy PXE symlink boot configurations."""
        configs: List[Dict[str, str]] = []
        if not self.pxelinux_cfg_dir.exists():
            return configs
        try:
            for entry in self.pxelinux_cfg_dir.iterdir():
                if entry.is_symlink() and len(entry.name) == 8:
                    try:
                        ip = self.hex_to_ip(entry.name)
                        configs.append(
                            {
                                "ip": ip,
                                "hex": entry.name,
                                "target": os.readlink(str(entry)),
                                "device": self.get_boot_device(ip),
                            }
                        )
                    except (ValidationError, OSError) as exc:
                        self.logger.warning("Skipping invalid PXE entry %s: %s", entry.name, exc)
        except OSError as exc:
            self.logger.error("Failed to list PXELINUX directory: %s", exc)
        return sorted(configs, key=lambda item: tuple(int(part) for part in item["ip"].split(".")))

    # ============================================================
    #                   iPXE URLS / SCRIPTS
    # ============================================================

    def get_ipxe_base_url(self) -> str:
        return f"{str(config.IPXE_HTTP_BASE_URL).rstrip('/')}/ipxe"

    def get_client_script_url(self, identifier: Optional[str] = None) -> str:
        base = f"{self.get_ipxe_base_url()}/clients"
        if identifier:
            ident = self.normalize_ipxe_client_identifier(identifier)
            return f"{base}/{ident}.ipxe"
        return base

    def get_dynamic_boot_url(self, ip: str) -> str:
        """Backward-compatible helper used by the existing web query modal."""
        return self.get_client_script_url(validate_ip_address(ip))

    def get_profile_ipxe_url(self, boot_profile: str) -> Optional[str]:
        path = self.get_profile_ipxe_path(boot_profile)
        if not path:
            return None
        return f"{self.get_ipxe_base_url()}/{path.name}"

    def generate_default_ipxe_script(self) -> str:
        """Generate the static iPXE dispatcher.

        Lookup order:
          1) /ipxe/clients/<ip>.ipxe
          2) /ipxe/default.ipxe if it exists
          3) local disk 0
        """
        base_url = self.get_ipxe_base_url()
        retry_seconds = int(config.IPXE_RETRY_SECONDS)
        return "\n".join(
            [
                "#!ipxe",
                "# DHCP Manager iPXE dispatcher",
                "# Generated by DHCP Manager - safe to regenerate",
                f"set ipxe-base {base_url}",
                "dhcp || goto failed",
                "echo DHCP Manager iPXE dispatcher",
                "echo MAC: ${net0/mac}  IP: ${ip}",
                "echo Trying IP-specific client script...",
                "chain --replace ${ipxe-base}/clients/${ip}.ipxe || goto try_default",
                "",
                ":try_default",
                "echo Trying default iPXE profile...",
                "chain --replace ${ipxe-base}/default.ipxe || goto local_disk",
                "",
                ":local_disk",
                "echo No dedicated iPXE file found. Booting first local disk...",
                "sanboot --no-describe --drive 0x80 || goto failed",
                "exit 0",
                "",
                ":failed",
                "echo iPXE boot failed. Returning to firmware shortly.",
                f"sleep {retry_seconds}",
                "exit 1",
                "",
            ]
        )

    def write_default_ipxe_script(self) -> Path:
        """Write the main ipxe.ipxe dispatcher under the TFTP iPXE directory."""
        path = self.get_ipxe_script_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.generate_default_ipxe_script(), encoding="utf-8")
            self.logger.info("Wrote default iPXE dispatcher: %s", path)
            return path
        except OSError as exc:
            raise PXEBootError(f"Failed to write default iPXE script {path}: {exc}") from exc


    # ============================================================
    #                   PXELINUX -> iPXE TRANSLATION
    # ============================================================

    @staticmethod
    def _strip_pxelinux_value(value: str) -> str:
        """Remove PXELINUX/iPXE whitespace and common quoting from a value."""
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        return value

    @staticmethod
    def _tftp_url(path: str) -> str:
        """Return a TFTP URL usable by iPXE for a PXELINUX-relative path."""
        clean = path.strip()
        if clean.startswith(("http://", "https://", "tftp://", "ftp://")):
            return clean
        return f"tftp://${{next-server}}/{clean.lstrip('/')}"

    def parse_pxelinux_menu(self, boot_profile: str) -> Dict[str, str]:
        """Parse a PXELINUX menu file into a minimal boot entry.

        The parser intentionally focuses on common Linux installer/live entries:
        DEFAULT/LABEL, KERNEL, INITRD and APPEND. It ignores presentation-only
        lines such as MENU LABEL. If the file has multiple LABEL blocks, the
        DEFAULT label is preferred; otherwise the first bootable block is used.
        """
        path = self.get_pxelinux_profile_path(boot_profile)
        if not path:
            raise PXEBootError(f"PXELINUX profile not found: {boot_profile}")

        global_default = ""
        global_kernel = ""
        global_initrd = ""
        global_append = ""
        labels: List[Dict[str, str]] = []
        current: Optional[Dict[str, str]] = None

        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            directive = parts[0].upper()
            value = self._strip_pxelinux_value(parts[1] if len(parts) > 1 else "")

            if directive == "DEFAULT":
                global_default = value.split()[0] if value else ""
                continue

            if directive == "LABEL":
                current = {"label": value, "kernel": "", "initrd": "", "append": "", "localboot": ""}
                labels.append(current)
                continue

            target = current if current is not None else None
            if directive in {"KERNEL", "LINUX"}:
                if target is not None:
                    target["kernel"] = value
                else:
                    global_kernel = value
            elif directive == "INITRD":
                if target is not None:
                    target["initrd"] = value
                else:
                    global_initrd = value
            elif directive == "APPEND":
                if target is not None:
                    target["append"] = value
                else:
                    global_append = value
            elif directive == "LOCALBOOT":
                if target is not None:
                    target["localboot"] = value or "0"

        selected: Dict[str, str]
        if labels:
            selected = labels[0]
            if global_default:
                for item in labels:
                    if item.get("label") == global_default:
                        selected = item
                        break
        else:
            selected = {"label": global_default or boot_profile, "kernel": global_kernel, "initrd": global_initrd, "append": global_append, "localboot": ""}

        # Inherit global values when a LABEL block omits them.
        selected = dict(selected)
        selected["kernel"] = selected.get("kernel") or global_kernel
        selected["initrd"] = selected.get("initrd") or global_initrd
        selected["append"] = selected.get("append") or global_append
        return selected

    def translate_pxelinux_profile_to_ipxe(self, boot_profile: str) -> str:
        """Translate a PXELINUX menu/profile into an iPXE client script.

        This supports the common OS profile model where `pxelinux.cfg/<profile>`
        contains the authoritative kernel/initrd paths and kernel arguments. The
        generated iPXE file uses the same vmlinuz/initrd/image directories via
        TFTP. If a profile uses PXELINUX-only COM32 modules or complex includes,
        the generated script fails clearly instead of silently booting the wrong
        thing.
        """
        profile = self.validate_boot_profile(boot_profile)
        entry = self.parse_pxelinux_menu(profile)
        kernel = (entry.get("kernel") or "").strip()
        initrd = (entry.get("initrd") or "").strip()
        append = (entry.get("append") or "").strip()
        localboot = (entry.get("localboot") or "").strip()
        retry_seconds = int(config.IPXE_RETRY_SECONDS)

        lines = [
            "#!ipxe",
            "# DHCP Manager generated from PXELINUX profile",
            f"# Source PXELINUX profile: {profile}",
            f"set boot-profile {profile}",
            "echo DHCP Manager translated PXELINUX profile: ${boot-profile}",
            "",
        ]

        local_boot_target = self.IPXE_LOCAL_BOOT_PROFILES.get(profile)

        if local_boot_target == "hdd0":
            lines.extend(["sanboot --no-describe --drive 0x80 || goto failed", "exit 0"])
        elif local_boot_target == "hdd1":
            lines.extend(["sanboot --no-describe --drive 0x81 || goto failed", "exit 0"])
        elif local_boot_target == "usb":
            lines.extend(["echo Returning to firmware boot order...", "exit 0"])
        elif localboot or kernel.lower() in {"localboot", "localboot.c32", "chain.c32"}:
            drive = "0x81" if localboot == "1" else "0x80"
            lines.extend([f"sanboot --no-describe --drive {drive} || goto failed", "exit 0"])
        elif not kernel:
            raise PXEBootError(f"Cannot translate PXELINUX profile {profile}: no KERNEL/LINUX directive found")
        elif kernel.lower().endswith(".c32"):
            raise PXEBootError(
                f"Cannot translate PXELINUX profile {profile}: COM32 module {kernel} is PXELINUX-specific"
            )
        else:
            initrd_from_append = ""
            append_tokens = []
            for token in append.split():
                if token.startswith("initrd="):
                    initrd_from_append = token.split("=", 1)[1].split(",", 1)[0]
                else:
                    append_tokens.append(token)
            initrd = initrd or initrd_from_append
            append_without_initrd = " ".join(append_tokens)

            if initrd:
                lines.append(f"initrd {self._tftp_url(initrd)} || goto failed")
                kernel_args = f"initrd={Path(initrd).name} {append_without_initrd}".strip()
            else:
                kernel_args = append_without_initrd
            lines.append(f"kernel {self._tftp_url(kernel)} {kernel_args}".rstrip() + " || goto failed")
            lines.extend(["boot || goto failed", "exit 0"])

        lines.extend(["", ":failed", "echo Translated PXELINUX profile failed.", f"sleep {retry_seconds}", "exit 1", ""])
        return "\n".join(lines)

    def generate_profile_ipxe_script(self, boot_profile: str) -> str:
        """Generate a per-client iPXE script pointing to a chosen boot profile."""
        profile = self.validate_boot_profile(boot_profile)
        retry_seconds = int(config.IPXE_RETRY_SECONDS)
        lines = [
            "#!ipxe",
            "# DHCP Manager generated client iPXE override",
            f"set boot-profile {profile}",
            "echo DHCP Manager client boot profile: ${boot-profile}",
            "",
        ]

        local_boot_target = self.IPXE_LOCAL_BOOT_PROFILES.get(profile)

        if local_boot_target == "hdd0":
            lines.extend([
                "echo Booting first local disk...",
                "sanboot --no-describe --drive 0x80 || goto failed",
                "exit 0",
            ])
        elif local_boot_target == "hdd1":
            lines.extend([
                "echo Booting second local disk...",
                "sanboot --no-describe --drive 0x81 || goto failed",
                "exit 0",
            ])
        elif local_boot_target == "usb":
            lines.extend([
                "echo Returning to firmware boot order for USB/local boot...",
                "exit 0",
            ])
        elif profile == "default":
            lines.extend(
                [
                    "echo Using default dispatcher behavior...",
                    f"chain --replace {self.get_ipxe_base_url()}/default.ipxe || goto local_disk",
                    "",
                    ":local_disk",
                    "sanboot --no-describe --drive 0x80 || goto failed",
                    "exit 0",
                ]
            )
        elif self.get_profile_ipxe_path(profile):
            lines.extend([f"chain --replace {self.get_profile_ipxe_url(profile)} || goto failed", "exit 0"])
        elif self.get_pxelinux_profile_path(profile):
            return self.translate_pxelinux_profile_to_ipxe(profile)
        else:
            raise PXEBootError(f"Boot profile not found: {profile}")

        lines.extend(["", ":failed", "echo Client boot profile failed.", f"sleep {retry_seconds}", "exit 1", ""])
        return "\n".join(lines)

    def write_client_ipxe_script(self, identifier: str, boot_profile: str) -> Path:
        """Create/update an IP-specific iPXE override."""
        ident = self.normalize_ipxe_client_identifier(identifier)
        path = self.get_client_script_path(ident)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.generate_profile_ipxe_script(boot_profile), encoding="utf-8")
            self.logger.info("Wrote client iPXE script: %s -> %s", path.name, boot_profile)
            return path
        except OSError as exc:
            raise PXEBootError(f"Failed to write client iPXE script {path}: {exc}") from exc

    def write_client_ipxe_scripts(self, boot_profile: str, mac: Optional[str] = None, ip: Optional[str] = None) -> List[Path]:
        """Create/update generated iPXE override.

        The `mac` argument is accepted for API compatibility but ignored.
        Generated iPXE client files are keyed by IP only.
        """
        if not ip:
            raise ValidationError("IP is required to create an iPXE client script")
        return [self.write_client_ipxe_script(ip, boot_profile)]

    # Backward-compatible aliases from the earlier patch.
    def get_mac_script_dir(self) -> Path:
        return self.ipxe_clients_dir

    def get_mac_script_path(self, mac: str) -> Path:
        raise ValidationError("MAC-specific iPXE files are no longer generated; use an IP address instead")

    def get_mac_script_url(self, mac: Optional[str] = None) -> str:
        return self.get_client_script_url()

    def write_mac_ipxe_script(self, mac: str, boot_profile: str) -> Path:
        raise ValidationError("MAC-specific iPXE files are no longer generated; use an IP address instead")

    def delete_client_ipxe_script(self, identifier: str) -> None:
        """Delete a generated per-client iPXE override if it exists."""
        path = self.get_client_script_path(identifier)
        try:
            if path.exists():
                path.unlink()
                self.logger.info("Deleted client iPXE script: %s", path)
        except OSError as exc:
            raise PXEBootError(f"Failed to delete client iPXE script {path}: {exc}") from exc

    def delete_mac_ipxe_script(self, mac: str) -> None:
        # Backward-compatible no-op: generated iPXE client files are IP-based now.
        self.logger.info("Ignoring MAC-specific iPXE delete request for %s; iPXE overrides are IP-based", mac)

    def list_client_ipxe_scripts(self) -> List[Dict[str, str]]:
        """List generated per-client iPXE overrides."""
        scripts: List[Dict[str, str]] = []
        directory = self.ipxe_clients_dir
        if not directory.exists():
            return scripts
        try:
            for path in sorted(directory.glob("*.ipxe")):
                ident = path.name[:-5]
                try:
                    normalized = self.normalize_ipxe_client_identifier(ident)
                except ValidationError:
                    self.logger.warning("Skipping invalid client script filename: %s", path.name)
                    continue
                identifier_type = "ip"
                scripts.append(
                    {
                        "identifier": normalized,
                        "type": identifier_type,
                        "path": str(path),
                        "url": self.get_client_script_url(normalized),
                    }
                )
        except OSError as exc:
            raise PXEBootError(f"Failed to list iPXE client scripts in {directory}: {exc}") from exc
        return scripts

    def list_mac_ipxe_scripts(self) -> List[Dict[str, str]]:
        """Backward-compatible list of MAC-specific scripts only."""
        return [item for item in self.list_client_ipxe_scripts() if item["type"] == "mac"]

    def generate_isc_dhcp_ipxe_snippet(self) -> str:
        """Return an ISC DHCP snippet for iPXE chainloading."""
        return f"""# DHCP Manager iPXE support
# Paste inside the relevant subnet/shared-network block in dhcpd.conf.
# 1) Non-iPXE clients receive an architecture-appropriate iPXE loader via TFTP.
# 2) iPXE clients receive the static dispatcher script: {self.get_ipxe_script_tftp_filename()}
# 3) The dispatcher tries /ipxe/clients/<ip>.ipxe, /ipxe/default.ipxe,
#    then local disk 0.

option client-arch code 93 = unsigned integer 16;

if exists user-class and option user-class = \"iPXE\" {{
    filename \"{self.get_ipxe_script_tftp_filename()}\";
}} elsif option client-arch = 00:07 or option client-arch = 00:09 {{
    filename \"{config.IPXE_UEFI_BOOTLOADER}\";
}} else {{
    filename \"{config.IPXE_BIOS_BOOTLOADER}\";
}}
"""
