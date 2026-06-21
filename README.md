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
- Centralized, environment-variable-driven configuration in `config.py`
- Input validation, custom exceptions, structured logging, and unit tests

---

## Project Structure

```text
dhcp_manager/
├── config.py                    # Centralized configuration (env-var overridable)
├── exceptions.py                # Custom exception classes
├── cli.py                       # Command-line interface
├── web.py                       # Flask web interface
├── debug_boot_devices.py        # Standalone troubleshooting script
├── requirements.txt             # Python dependencies
│
├── setup_wizard/                # First-run DHCP/TFTP/PXE setup wizard
│   ├── __init__.py
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
│   ├── login.html
│   ├── index.html
│   ├── add_edit.html
│   ├── setup_checks.html
│   ├── setup_config.html
│   ├── setup_review.html
│   └── setup_done.html
│
└── tests/
    ├── __init__.py
    ├── test_dhcp_manager.py
    └── test_pxe_manager.py
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
sudo dnf install -y dhcp-server --releasever=9 # If using a higher version since dhcp-server is deprecated
sudo dnf install -y tftp-server syslinux-tftpboot python3 python3-pip
```

> Note: `syslinux-tftpboot` provides PXELINUX/Syslinux files such as `pxelinux.0`, `menu.c32`, `ldlinux.c32`, and related `.c32` modules. It does not provide iPXE binaries such as `undionly.kpxe`, `ipxe.efi`, or `snponly.efi`.

### 2. Clone the project

```bash
cd /opt
sudo git clone https://github.com/zohdi/dhcp_pxe_web_manager.git dhcp_manager
cd /opt/dhcp_manager
```

To use a specific branch:

```bash
sudo git clone -b <branch-name> https://github.com/zohdi/dhcp_pxe_web_manager.git dhcp_manager
```

### 3. Install Python dependencies

```bash
sudo pip3 install -r requirements.txt
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

## Configuration

All settings live in `config.py` and can be overridden with environment variables — no need to edit the file directly in most deployments.

| Setting | Environment variable | Default |
|---|---|---|
| DHCP config path | `DHCP_CONF` | `/etc/dhcp/dhcpd.conf` |
| DHCP backup path | `DHCP_BACKUP` | `/etc/dhcp/dhcpd.conf.bak` |
| DHCP service name | `DHCP_SERVICE` | `isc-dhcp-server` |
| DNS service name | `BIND_SERVICE` | `bind9` |
| TFTP/PXELINUX dir | `TFTP_BASE_DIR` | `/var/lib/tftpboot/pxelinux.cfg` |
| iPXE base URL | `IPXE_HTTP_BASE_URL` | `http://127.0.0.1:5000` |
| Flask bind host | `FLASK_HOST` | `0.0.0.0` |
| Flask bind port | `FLASK_PORT` | `5000` |
| Flask debug mode | `FLASK_DEBUG` | `false` |
| Flask secret key | `FLASK_SECRET_KEY` | **must be changed** |
| Admin username | `ADMIN_USERNAME` | `Admin` |
| Admin password hash | `ADMIN_PASSWORD_HASH` | **must be changed** |

### Setting a real admin password

Generate a bcrypt hash for your chosen password:

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your-new-password', bcrypt.gensalt()).decode())"
```

Then export it (or put it in a systemd unit / `.env` file your process manager loads):

```bash
export ADMIN_PASSWORD_HASH='$2b$12$...'
export FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

**Never commit real credentials, secret keys, or API keys to the repository.** See [Security Notes](#security-notes) below.

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

See [SETUP_WIZARD.md](SETUP_WIZARD.md) for full wizard details.

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

Set the base URL clients will use to reach this app:

```bash
export IPXE_HTTP_BASE_URL="http://<dhcp-manager-ip>:5000"
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

## Testing

This project uses `pytest`:

```bash
pip3 install pytest
pytest tests/
```

---

## Security Notes

Before production use:

1. **Set `ADMIN_PASSWORD_HASH` and `FLASK_SECRET_KEY` via environment variables** — do not leave the repository defaults in place, and never commit real values to source control.
2. Keep `FLASK_DEBUG` unset or `false`.
3. Restrict access to the web UI using firewall rules or a reverse proxy.
4. Use HTTPS if exposing the UI outside a trusted management network.
5. Run with the minimum permissions possible, but note that DHCP/TFTP operations usually require root.
6. **Rotate any credentials or API keys that were ever committed to this repository's history**, even after deleting the file — git history retains old blobs unless it is rewritten (see below).

### Note on repository history

An earlier commit in this repository included a plaintext file (`mailgun_api`) containing what appears to be a live API key. That file has been removed from this cleaned snapshot, but **removing a file does not remove it from git history**. If this repository has ever been pushed publicly:

1. Treat that key as compromised and rotate/revoke it with the provider immediately.
2. Scrub it from history with `git filter-repo` or BFG Repo-Cleaner before any further public push.
3. Add a pre-commit secret scanner (e.g. `gitleaks`, `trufflehog`) going forward — `.gitignore` only prevents *new* commits, it does nothing for files already tracked.

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

## Author

Original project by Zohdi Mahameed.

## Acknowledgments

- ISC DHCP Server
- Syslinux / PXELINUX
- iPXE
- Flask
- Python community
