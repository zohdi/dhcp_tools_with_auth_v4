from pathlib import Path

from managers.pxe_manager import PXEBootManager


def test_ip_to_hex_and_back():
    assert PXEBootManager.ip_to_hex("192.168.1.10") == "C0A8010A"
    assert PXEBootManager.hex_to_ip("C0A8010A") == "192.168.1.10"


def test_legacy_boot_link_roundtrip(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    pxe_dir.mkdir()
    (pxe_dir / "default_local_disk0").write_text("menu")
    mgr = PXEBootManager(tftp_dir=pxe_dir)
    mgr.create_boot_link("192.168.1.10", "hd0")
    assert mgr.get_boot_device("192.168.1.10") == "hdd0"
    configs = mgr.list_all_boot_configs()
    assert configs == [
        {
            "ip": "192.168.1.10",
            "hex": "C0A8010A",
            "target": "default_local_disk0",
            "device": "hdd0",
        }
    ]


def test_dynamic_profile_discovery_from_pxelinux_and_ipxe(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    ipxe_dir = tmp_path / "ipxe"
    pxe_dir.mkdir()
    ipxe_dir.mkdir()
    (pxe_dir / "default").write_text("default menu")
    (pxe_dir / "rocky-9").write_text("rocky menu")
    (pxe_dir / "C0A8010A").symlink_to("rocky-9")
    (ipxe_dir / "debian.ipxe").write_text("#!ipxe\n")
    (ipxe_dir / "ipxe.ipxe").write_text("#!ipxe dispatcher\n")
    (ipxe_dir / "clients").mkdir()
    (ipxe_dir / "clients" / "aa:bb:cc:dd:ee:ff.ipxe").write_text("#!ipxe\n")

    mgr = PXEBootManager(tftp_dir=pxe_dir)
    profiles = {p["key"]: p for p in mgr.discover_boot_profiles()}

    assert "default" in profiles
    assert profiles["rocky-9"]["source"] == "pxelinux"
    assert profiles["debian"]["source"] == "ipxe"
    assert "C0A8010A" not in profiles
    assert "aa:bb:cc:dd:ee:ff" not in profiles


def test_dynamic_legacy_profile_link_uses_menu_filename(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    pxe_dir.mkdir()
    (pxe_dir / "rocky-9").write_text("menu")
    mgr = PXEBootManager(tftp_dir=pxe_dir)
    mgr.create_boot_link("192.168.1.10", "rocky-9")
    assert (pxe_dir / "C0A8010A").is_symlink()
    assert (pxe_dir / "C0A8010A").readlink() == Path("rocky-9")
    assert mgr.get_boot_device("192.168.1.10") == "rocky-9"


def test_default_ipxe_dispatcher_checks_ip_default_then_local_disk(tmp_path: Path):
    mgr = PXEBootManager(tftp_dir=tmp_path / "pxelinux.cfg")
    script = mgr.generate_default_ipxe_script()
    assert script.startswith("#!ipxe")
    assert "/clients/${net0/mac}.ipxe" not in script
    assert "/clients/${ip}.ipxe" in script
    assert "/default.ipxe" in script
    assert "sanboot --no-describe --drive 0x80" in script


def test_write_default_ipxe_script_to_ipxe_directory(tmp_path: Path):
    mgr = PXEBootManager(tftp_dir=tmp_path / "pxelinux.cfg")
    path = mgr.write_default_ipxe_script()
    assert path == tmp_path / "ipxe" / "ipxe.ipxe"
    assert path.exists()
    assert "DHCP Manager iPXE dispatcher" in path.read_text()


def test_client_specific_script_roundtrip_for_ip_only(tmp_path: Path):
    mgr = PXEBootManager(tftp_dir=tmp_path / "pxelinux.cfg")
    ip_path = mgr.write_client_ipxe_script("192.168.1.10", "hdd0")
    assert ip_path == tmp_path / "ipxe" / "clients" / "192.168.1.10.ipxe"
    assert "sanboot --no-describe --drive 0x80" in ip_path.read_text()

    scripts = mgr.list_client_ipxe_scripts()
    assert {item["identifier"] for item in scripts} == {"192.168.1.10"}
    assert {item["type"] for item in scripts} == {"ip"}
    mgr.delete_client_ipxe_script("192.168.1.10")
    assert not ip_path.exists()


def test_generated_client_script_can_chain_ipxe_profile(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    ipxe_dir = tmp_path / "ipxe"
    pxe_dir.mkdir()
    ipxe_dir.mkdir()
    (ipxe_dir / "rocky-9.ipxe").write_text("#!ipxe\n")
    mgr = PXEBootManager(tftp_dir=pxe_dir)
    script = mgr.generate_profile_ipxe_script("rocky-9")
    assert "/ipxe/rocky-9.ipxe" in script
    assert "chain --replace" in script


def test_generated_client_script_translates_pxelinux_linux_menu(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    pxe_dir.mkdir()
    (pxe_dir / "rocky-9").write_text(
        """DEFAULT install
LABEL install
  KERNEL images/rocky-9/vmlinuz
  APPEND initrd=images/rocky-9/initrd.img inst.repo=http://mirror/rocky/9 quiet
"""
    )
    mgr = PXEBootManager(tftp_dir=pxe_dir)
    script = mgr.generate_profile_ipxe_script("rocky-9")
    assert "initrd tftp://${next-server}/images/rocky-9/initrd.img" in script
    assert "kernel tftp://${next-server}/images/rocky-9/vmlinuz" in script
    assert "inst.repo=http://mirror/rocky/9 quiet" in script
    assert "pxelinux.0" not in script


def test_isc_dhcp_snippet_contains_static_dispatcher_logic():
    mgr = PXEBootManager()
    snippet = mgr.generate_isc_dhcp_ipxe_snippet()
    assert 'option user-class = "iPXE"' in snippet
    assert "undionly.kpxe" in snippet
    assert "ipxe.efi" in snippet
    assert 'filename "ipxe/ipxe.ipxe"' in snippet


def test_discovery_does_not_duplicate_local_disk_aliases(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    pxe_dir.mkdir()
    (pxe_dir / "hdd0").write_text("local disk menu")
    (pxe_dir / "hdd1").write_text("local disk menu")
    mgr = PXEBootManager(tftp_dir=pxe_dir)
    keys = [p["key"] for p in mgr.discover_boot_profiles()]
    assert keys.count("hdd0") == 1
    assert keys.count("hdd1") == 1
    assert "hd0" not in keys
    assert "hd1" not in keys


def test_local_boot_pxelinux_profiles_generate_ipxe_without_translation_error(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    pxe_dir.mkdir()
    (pxe_dir / "boot_local_hdd0").write_text("LOCALBOOT 0\n")
    (pxe_dir / "boot_local_hdd1").write_text("LOCALBOOT 1\n")
    (pxe_dir / "boot_local_usb").write_text("LOCALBOOT 0\n")

    mgr = PXEBootManager(tftp_dir=pxe_dir)

    hdd0_script = mgr.write_client_ipxe_script("192.168.1.10", "boot_local_hdd0").read_text()
    assert "sanboot --no-describe --drive 0x80" in hdd0_script

    hdd1_script = mgr.write_client_ipxe_script("192.168.1.10", "boot_local_hdd1").read_text()
    assert "sanboot --no-describe --drive 0x81" in hdd1_script

    usb_script = mgr.write_client_ipxe_script("192.168.1.10", "boot_local_usb").read_text()
    assert "Returning to firmware boot order" in usb_script
    assert "sanboot --no-describe --drive" not in usb_script


def test_translator_handles_named_local_boot_profiles(tmp_path: Path):
    pxe_dir = tmp_path / "pxelinux.cfg"
    pxe_dir.mkdir()
    (pxe_dir / "boot_local_hdd0").write_text("LOCALBOOT 0\n")
    (pxe_dir / "boot_local_hdd1").write_text("LOCALBOOT 1\n")
    (pxe_dir / "boot_local_usb").write_text("LOCALBOOT 0\n")

    mgr = PXEBootManager(tftp_dir=pxe_dir)

    assert "sanboot --no-describe --drive 0x80" in mgr.translate_pxelinux_profile_to_ipxe("boot_local_hdd0")
    assert "sanboot --no-describe --drive 0x81" in mgr.translate_pxelinux_profile_to_ipxe("boot_local_hdd1")
    assert "Returning to firmware boot order" in mgr.translate_pxelinux_profile_to_ipxe("boot_local_usb")
