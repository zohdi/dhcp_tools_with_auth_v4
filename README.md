# DHCP Manager

A Python-based DHCP reservation manager with a Flask web UI, first-run setup wizard, and PXE/iPXE boot profile support.

The project manages ISC DHCP configuration, DHCP host reservations, classic PXELINUX profiles, and generated iPXE client scripts from one place.

---

## Features

- Web interface for managing DHCP reservations
- CLI for listing, adding, modifying, querying, and removing reservations
- First-run setup wizard for DHCP, TFTP, and PXE bootstrap configuration
- PXELINUX support using per-client `pxelinux.cfg/<IP_HEX>` links
- iPXE dispatcher support using per-client scripts under `ipxe/clients/`
- Dynamic Boot Device discovery from PXELINUX and iPXE profiles
- PXELINUX-to-iPXE translation for common Linux installer entries
- Centralized configuration in `config.py`
- Input validation, custom exceptions, structured logging, and unit tests

---

## Project Structure

```text
dhcp_manager/
├── config.py                    # Centralized configuration
├── exceptions.py                # Custom exception classes
├── cli.py                       # Command-line interface
├── web.py                       # Flask web interface
│
├── setup_wizard/                # First-run DHCP/TFTP/PXE setup wizard
│   ├── __init__.py
│   ├── files/
│   └── manager.py
│
├── managers/
│   ├── __init__.py
│   ├── dhcp_manager.py          # DHCP configuration management
│   └── pxe_manager.py           # PXE/iPXE boot management
│
├── utils/
│   ├── __init__.py
│   ├── colors.py
│   ├── logger.py
│   └── validators.py
│
├── templates/
│   ├── layout.html
│   ├── index.html
│   └── add_edit.html
│
└── tests/
    ├── __init__.py
    └── test_dhcp_manager.py
```

---

## Installation

### 1. Install system packages

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y isc-dhcp-server tftpd-hpa syslinux-common pxelinux python3 python3-pip
```

Rocky/RHEL/Fedora:

```bash
sudo dnf install -y dhcp-server --releasever=9 # If using higher version since dhcp-server is deprecated 
sudo dnf install tftp-server syslinux-tftpboot python3 python3-pip
```

> Note: `syslinux-tftpboot` provides PXELINUX/Syslinux files such as `pxelinux.0`, `menu.c32`, `ldlinux.c32`, and related `.c32` modules. It does not provide iPXE binaries such as `undionly.kpxe`, `ipxe.efi`, or `snponly.efi`.

### 2. Clone the project

Main branch:

```bash
cd /opt
sudo git clone https://github.com/zohdi/dhcp_tools_with_auth_v4.git dhcp_manager
cd /opt/dhcp_manager
```

Autodeploy branch:

```bash
cd /opt
sudo git clone -b autodeploy_web_dhcp https://github.com/zohdi/dhcp_tools_with_auth_v4.git dhcp_manager
cd /opt/dhcp_manager
```

### 3. Install Python dependencies

```bash
sudo pip3 install flask bcrypt
```

### 4. Make scripts executable

```bash
sudo chmod +x cli.py web.py
```

Optional CLI symlink:

```bash
sudo ln -s /opt/dhcp_manager/cli.py /usr/local/bin/dhcp-manager
```

---

## First-Run Setup Wizard

Start the web app:

```bash
sudo python3 web.py
```

Open:

```text
http://<dhcp-manager-ip>:5000
```

On a fresh host, the app redirects to:

```text
/setup/checks
```

The wizard can:

- install required DHCP/TFTP/PXE packages
- select and configure the DHCP interface
- generate DHCP configuration
- configure TFTP
- copy required PXELINUX/Syslinux files
- create the default TFTP/PXE directory structure
- install iPXE dispatcher support where configured

For development without setup redirection:

```bash
DHCP_MANAGER_SKIP_SETUP=1 python3 web.py
```

---

## Default Login

```text
Username: Admin
Password: DHCPManager!
```

Change the default credentials and Flask secret key in `config.py` before production use.

---

## Web Usage

Start the web interface:

```bash
sudo python3 web.py
```

Then open:

```text
http://<dhcp-manager-ip>:5000
```

Use the UI to:

- add DHCP reservations
- edit existing reservations
- remove reservations
- assign PXE/iPXE Boot Device profiles
- initialize DHCP/TFTP/PXE setup through the wizard

---

## CLI Usage

```bash
# List all DHCP entries
sudo ./cli.py list

# Add a reservation
sudo ./cli.py add --hostname server1 --mac aa:bb:cc:dd:ee:ff --ip 192.168.1.10

# Query an entry
sudo ./cli.py query server1

# Modify an entry
sudo ./cli.py modify server1 --ip 192.168.1.20

# Remove an entry
sudo ./cli.py remove server1
```

---

## PXE and iPXE Boot Profiles

The legacy PXELINUX layer remains the source of truth for classic BIOS PXE clients. Selecting a Boot Device creates or updates a per-client symlink under:

```text
/var/lib/tftpboot/pxelinux.cfg/<IP_HEX>
```

The iPXE layer mirrors the same Boot Device choice by generating IP-specific scripts under:

```text
/var/lib/tftpboot/ipxe/clients/
```

This allows one GUI selection to support both legacy PXE and iPXE clients.

Example layout:

```text
/var/lib/tftpboot/pxelinux.cfg/default
/var/lib/tftpboot/pxelinux.cfg/rocky-9
/var/lib/tftpboot/pxelinux.cfg/debian
/var/lib/tftpboot/pxelinux.cfg/hdd0
/var/lib/tftpboot/pxelinux.cfg/C0A8010A -> rocky-9

/var/lib/tftpboot/ipxe/ipxe.ipxe
/var/lib/tftpboot/ipxe/default.ipxe
/var/lib/tftpboot/ipxe/rocky-9.ipxe
/var/lib/tftpboot/ipxe/clients/192.168.1.10.ipxe
```

---

## iPXE Flow

1. PXE firmware receives an iPXE binary:
   - BIOS: `undionly.kpxe`
   - UEFI: `ipxe.efi` or `snponly.efi`

2. iPXE starts and asks DHCP again.

3. DHCP detects iPXE and serves:

   ```text
   ipxe/ipxe.ipxe
   ```

4. The dispatcher tries the client-specific script first:

   ```ipxe
   chain --replace http://<dhcp-manager>:5000/ipxe/clients/${ip}.ipxe || goto try_default
   ```

5. If no client script exists, it tries the default iPXE profile:

   ```ipxe
   chain --replace http://<dhcp-manager>:5000/ipxe/default.ipxe || goto local_disk
   ```

6. If no iPXE profile exists, it boots local disk.

---

## Dynamic Boot Device Discovery

The web UI discovers Boot Device options from:

- regular non-symlink files under `pxelinux.cfg/`
- regular top-level `.ipxe` files under `ipxe/`

Generated client files are hidden:

```text
ipxe/clients/*.ipxe
pxelinux.cfg/<IP_HEX> symlinks
```

Local disk aliases such as `hdd0` and `hdd1` are de-duplicated in the UI.

---

## PXELINUX-to-iPXE Translation

If a selected Boot Device exists only as a PXELINUX profile, DHCP Manager parses common Linux boot entries and generates an iPXE equivalent for that client.

Supported common PXELINUX shape:

```text
DEFAULT install
LABEL install
  KERNEL images/rocky/vmlinuz
  INITRD images/rocky/initrd.img
  APPEND inst.repo=http://mirror/rocky quiet
```

Preview generated iPXE syntax:

```bash
./cli.py ipxe translate rocky-9
```

Write a reusable native iPXE profile:

```bash
sudo ./cli.py ipxe translate rocky-9 --write
```

Native files under `ipxe/<profile>.ipxe` take precedence over translated PXELINUX profiles.

---

## Configure iPXE Support

Edit `config.py`:

```python
IPXE_HTTP_BASE_URL = "http://<dhcp-manager-ip>:5000"
```

Install the main iPXE dispatcher:

```bash
sudo ./cli.py ipxe install-default
```

Show the DHCP snippet:

```bash
./cli.py ipxe snippet
```

Paste the snippet into the relevant ISC DHCP `subnet` or `shared-network` block, then validate and restart DHCP.

Ubuntu/Debian:

```bash
sudo dhcpd -t -cf /etc/dhcp/dhcpd.conf
sudo systemctl restart isc-dhcp-server
```

Rocky/RHEL/Fedora:

```bash
sudo dhcpd -t -cf /etc/dhcp/dhcpd.conf
sudo systemctl restart dhcpd
```

---

## Useful iPXE CLI Commands

```bash
# Show discovered boot profiles
./cli.py ipxe profiles

# Set both PXELINUX symlink and iPXE client override
sudo ./cli.py boot 192.168.1.10 rocky-9

# Create/update only the generated iPXE client file
sudo ./cli.py ipxe set-client 192.168.1.10 rocky-9

# List generated iPXE client files
./cli.py ipxe list-clients

# Remove a generated iPXE client file
sudo ./cli.py ipxe delete-client 192.168.1.10
```

---

## Configuration

Main settings are in:

```text
config.py
```

Common values to review:

```python
DHCP_CONF = Path("/etc/dhcp/dhcpd.conf")
DHCP_BACKUP = Path("/etc/dhcp/dhcpd.conf.bak")

TFTP_BASE_DIR = Path("/var/lib/tftpboot/pxelinux.cfg")

FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = False

FLASK_SECRET_KEY = "change-this-in-production"

IPXE_HTTP_BASE_URL = "http://<dhcp-manager-ip>:5000"
```

---

## Testing

```bash
python3 -m unittest tests/test_dhcp_manager.py
```

Verbose:

```bash
python3 tests/test_dhcp_manager.py
```

---

## Security Notes

Before production use:

1. Change the default admin credentials.
2. Change `FLASK_SECRET_KEY`.
3. Keep `FLASK_DEBUG = False`.
4. Restrict access to the web UI using firewall rules or a reverse proxy.
5. Use HTTPS if exposing the UI outside a trusted management network.
6. Run with the minimum permissions possible, but note that DHCP/TFTP operations usually require root.

---

## Troubleshooting

### DHCP service does not start

Validate the DHCP config:

```bash
sudo dhcpd -t -cf /etc/dhcp/dhcpd.conf
```

Check logs:

```bash
sudo journalctl -u isc-dhcp-server -f
```

Rocky/RHEL/Fedora:

```bash
sudo journalctl -u dhcpd -f
```

### Permission errors

Run CLI or web operations with sudo:

```bash
sudo ./cli.py list
sudo python3 web.py
```

### PXE boot fails

Check TFTP files:

```bash
ls -la /var/lib/tftpboot/
ls -la /var/lib/tftpboot/pxelinux.cfg/
```

Check PXELINUX symlinks:

```bash
find /var/lib/tftpboot/pxelinux.cfg -type l -ls
```

Check iPXE client scripts:

```bash
ls -la /var/lib/tftpboot/ipxe/
ls -la /var/lib/tftpboot/ipxe/clients/
```

### Rocky/RHEL Syslinux files are under `/tftpboot`

On Rocky/RHEL/Fedora, `syslinux-tftpboot` may install PXELINUX files under:

```text
/tftpboot/
```

Your managed TFTP root can still remain:

```text
/var/lib/tftpboot/
```

The setup wizard can copy the required files from `/tftpboot/` into the managed TFTP root.

### iPXE binaries are missing

This is expected if only Syslinux packages were installed.

These files are iPXE binaries, not Syslinux files:

```text
undionly.kpxe
ipxe.efi
snponly.efi
```

Install or build iPXE separately, or let the project installer/dispatcher workflow place them where expected.

---

## Development Notes

When adding features:

1. Add validation in `utils/validators.py`.
2. Add custom exceptions in `exceptions.py` when needed.
3. Implement logic in the relevant manager class.
4. Update CLI and/or Web interfaces.
5. Add or update tests.
6. Update this README.

Code style:

- follow PEP 8
- use type hints
- keep functions focused
- handle errors explicitly
- document public methods with docstrings

---

## Migration Notes

This refactored version replaces older script-based behavior with Python manager classes.

Main changes:

- `dhcp_manager.py` was split into:
  - `managers/dhcp_manager.py`
  - `managers/pxe_manager.py`
- `colors.py` moved to `utils/colors.py`
- `logger.py` moved to `utils/logger.py`
- `convert.sh` was replaced by:
  - `PXEBootManager.ip_to_hex()`
  - `PXEBootManager.hex_to_ip()`
- `manage_links_from_ip.py` was replaced by:
  - `PXEBootManager.create_boot_link()`
  - `PXEBootManager.delete_boot_link()`

Before migrating an existing host:

```bash
sudo cp /etc/dhcp/dhcpd.conf /etc/dhcp/dhcpd.conf.backup
```

Then test in a development environment before replacing a working DHCP server.

---

## Author

Original project by Zohdi Mahameed.

---

## Acknowledgments

- ISC DHCP Server
- Syslinux / PXELINUX
- iPXE
- Flask
- Python community
