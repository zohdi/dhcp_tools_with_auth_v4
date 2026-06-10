# DHCP Manager - Refactored Version

A professional, production-ready DHCP server management tool with PXE boot support.

## 🎯 Overview

This refactored version eliminates all external script dependencies and provides a clean, modular Python codebase for managing ISC DHCP server configurations and PXE boot settings.

## ✨ Key Improvements

### Eliminated External Dependencies
- ✅ **`convert.sh`** → Replaced with `PXEBootManager.ip_to_hex()` and `hex_to_ip()`
- ✅ **`manage_links_from_ip.py`** → Integrated into `PXEBootManager` class

### Code Quality Enhancements
- ✅ **Removed duplication** - Consolidated `colors.py` and `logger.py`
- ✅ **Type hints** - Added throughout for better IDE support
- ✅ **Custom exceptions** - Specific error types for better error handling
- ✅ **Validators module** - Centralized input validation
- ✅ **Configuration module** - Single source of truth for all settings
- ✅ **Comprehensive logging** - Better debugging and audit trail
- ✅ **Unit tests** - Comprehensive test coverage

### Architecture Improvements
- ✅ **Separation of concerns** - Clear module boundaries
- ✅ **Single Responsibility Principle** - Each class has one job
- ✅ **Dependency Injection** - Easier testing and configuration
- ✅ **Error handling** - Graceful degradation and rollback

## 📁 Project Structure

```
dhcp_manager/
├── config.py                    # Centralized configuration
├── exceptions.py                # Custom exception classes
│
├── utils/                       # Utility modules
│   ├── __init__.py
│   ├── colors.py               # Terminal colors
│   ├── logger.py               # Logging setup
│   └── validators.py           # Input validation
│
├── managers/                    # Core business logic
│   ├── __init__.py
│   ├── dhcp_manager.py         # DHCP configuration management
│   └── pxe_manager.py          # PXE boot management
│
├── cli.py                       # Command-line interface
├── web.py                       # Flask web interface
│
├── templates/                   # HTML templates
│   ├── layout.html
│   ├── index.html
│   └── add_edit.html
│
└── tests/                       # Unit tests
    ├── __init__.py
    └── test_dhcp_manager.py
```

## 🚀 Installation

### Prerequisites

```bash
# Install required packages
sudo apt-get update
sudo apt-get install -y isc-dhcp-server bind9 python3 python3-pip

# Install Python dependencies
pip3 install flask
```

### Setup

```bash
# Clone or copy the project
cd /opt
git clone <your-repo> dhcp_manager
cd dhcp_manager

# Make CLI executable
chmod +x cli.py web.py

# Optional: Create symlink for easy access
sudo ln -s /opt/dhcp_manager/cli.py /usr/local/bin/dhcp-manager
```

## 📖 Usage

### Command-Line Interface

```bash
# List all DHCP entries
./cli.py list

# Add a new entry
./cli.py add --hostname server1 --mac aa:bb:cc:dd:ee:ff --ip 192.168.1.10

# Query an entry
./cli.py query server1

# Modify an entry
./cli.py modify server1 --ip 192.168.1.20

# Remove an entry
./cli.py remove server1
```



## Dynamic PXE/iPXE boot profiles

The existing legacy PXELINUX feature remains the source of truth for classic PXE clients: selecting a Boot Device creates or updates a per-client symlink under `pxelinux.cfg/<IP_HEX>`.

The iPXE layer mirrors the same Boot Device choice using generated IP-specific scripts. One GUI selection updates both worlds because the tool cannot know in advance whether a machine will boot as legacy PXE or iPXE.

```text
/var/lib/tftpboot/pxelinux.cfg/default          # existing PXELINUX menu
/var/lib/tftpboot/pxelinux.cfg/centos-8.5      # auto-discovered GUI option
/var/lib/tftpboot/pxelinux.cfg/debian          # auto-discovered GUI option
/var/lib/tftpboot/pxelinux.cfg/hdd0            # auto-discovered once only
/var/lib/tftpboot/pxelinux.cfg/hdd1            # auto-discovered once only
/var/lib/tftpboot/pxelinux.cfg/C0A8010A -> centos-8.5

/var/lib/tftpboot/ipxe/ipxe.ipxe               # main dispatcher handed to iPXE clients
/var/lib/tftpboot/ipxe/default.ipxe            # optional default iPXE profile/menu
/var/lib/tftpboot/ipxe/rocky-9.ipxe            # optional native iPXE profile/menu
/var/lib/tftpboot/ipxe/clients/192.168.1.10.ipxe
```

### iPXE flow

1. Normal PXE firmware receives `undionly.kpxe` for BIOS or `ipxe.efi` for UEFI.
2. Once iPXE starts and asks DHCP again, DHCP gives it `ipxe/ipxe.ipxe`.
3. `ipxe/ipxe.ipxe` runs `dhcp`, then tries the generated IP-specific script:

   ```ipxe
   chain --replace http://<dhcp-manager>:5000/ipxe/clients/${ip}.ipxe || goto try_default
   chain --replace http://<dhcp-manager>:5000/ipxe/default.ipxe || goto local_disk
   sanboot --no-describe --drive 0x80
   ```

4. If no IP/default iPXE file exists, the client boots local disk 0.

### Dynamic Boot Device drop-down

The web GUI discovers Boot Device choices dynamically from:

- regular non-symlink files under `pxelinux.cfg`, for example `default`, `centos-8.5`, `debian`, `hdd0`, `hdd1`, `rocky-9`
- regular top-level files under `ipxe`, for example `default.ipxe`, `rocky-9.ipxe`

Generated client files under `ipxe/clients/` and PXELINUX IP symlinks are intentionally hidden. Local disk aliases are de-duplicated, so `hdd0` and `hdd1` appear once.

### PXELINUX to iPXE translation

When a selected Boot Device exists only as `pxelinux.cfg/<profile>`, DHCP Manager parses common PXELINUX Linux entries and generates an iPXE equivalent for the client. It reuses the same `KERNEL`/`LINUX`, `INITRD`, and `APPEND initrd=...` paths, loading them by TFTP. Native top-level `ipxe/<profile>.ipxe` files take precedence when present.

Supported common PXELINUX shape:

```text
DEFAULT install
LABEL install
  KERNEL images/centos-8.5/vmlinuz
  APPEND initrd=images/centos-8.5/initrd.img inst.repo=http://mirror/centos/8.5 quiet
```

Useful translation commands:

```bash
# Preview generated iPXE syntax from pxelinux.cfg/centos-8.5
./cli.py ipxe translate centos-8.5

# Write a reusable native profile to /var/lib/tftpboot/ipxe/centos-8.5.ipxe
sudo ./cli.py ipxe translate centos-8.5 --write
```

### Configure iPXE support

Edit `config.py`:

```python
IPXE_HTTP_BASE_URL = "http://<dhcp-manager-ip>:5000"
```

Install the main dispatcher into the TFTP iPXE directory:

```bash
sudo ./cli.py ipxe install-default
```

Print the DHCP snippet and paste it inside the relevant ISC DHCP `subnet` or `shared-network` block:

```bash
./cli.py ipxe snippet
```

Validate and restart DHCP:

```bash
sudo dhcpd -t -cf /etc/dhcp/dhcpd.conf
sudo systemctl restart isc-dhcp-server
```

### Useful CLI commands

```bash
# Show dynamically discovered boot profiles
./cli.py ipxe profiles

# Set both legacy PXELINUX symlink and IP-specific iPXE override
sudo ./cli.py boot 192.168.1.10 rocky-9

# Create/update only the generated IP-specific iPXE file
sudo ./cli.py ipxe set-client 192.168.1.10 rocky-9

# List/remove generated iPXE client files
./cli.py ipxe list-clients
sudo ./cli.py ipxe delete-client 192.168.1.10
```

## 🔧 Configuration

Edit `config.py` to customize paths and settings:

```python
@dataclass
class DHCPConfig:
    # DHCP Configuration
    DHCP_CONF: Path = Path("/etc/dhcp/dhcpd.conf")
    DHCP_BACKUP: Path = Path("/etc/dhcp/dhcpd.conf.bak")
    
    # PXE Boot Configuration
    TFTP_BASE_DIR: Path = Path("/var/lib/tftpboot/pxelinux.cfg")
    
    # Flask Configuration
    FLASK_HOST: str = "0.0.0.0"
    FLASK_PORT: int = 5000
    FLASK_DEBUG: bool = False  # Set False in production!
```

## 🧪 Testing

```bash
# Run all tests
python3 -m unittest tests/test_dhcp_manager.py

# Run with verbose output
python3 tests/test_dhcp_manager.py
```

## 🔒 Security Considerations

1. **Change the Flask secret key** in production:
   ```python
   # config.py
   FLASK_SECRET_KEY: str = "your-secure-random-key-here"
   ```

2. **Disable debug mode** in production:
   ```python
   FLASK_DEBUG: bool = False
   ```

3. **Use HTTPS** with a reverse proxy (nginx/Apache)

4. **Restrict access** with firewall rules or authentication

5. **Run with appropriate permissions** - requires root for DHCP operations

## 📝 API Documentation

### DHCPManager

```python
from managers.dhcp_manager import DHCPManager

mgr = DHCPManager()

# Add entry
mgr.add_entry("server1", "aa:bb:cc:dd:ee:ff", "192.168.1.10")

# Get all entries
entries = mgr.get_all_entries()

# Find specific entry
entry = mgr.find_entry("192.168.1.10")

# Modify entry
mgr.modify_entry("server1", new_ip="192.168.1.20")

# Remove entry
mgr.remove_entry("server1")
```

### PXEBootManager

```python
from managers.pxe_manager import PXEBootManager

pxe = PXEBootManager()

# Set boot device
pxe.create_boot_link("192.168.1.10", "hd0")

# Get boot device
device = pxe.get_boot_device("192.168.1.10")

# Convert IP to hex
hex_name = PXEBootManager.ip_to_hex("192.168.1.10")  # "C0A8010A"

# Convert hex to IP
ip = PXEBootManager.hex_to_ip("C0A8010A")  # "192.168.1.10"

# Delete boot link
pxe.delete_boot_link("192.168.1.10")
```

## 🐛 Troubleshooting

### DHCP Service Won't Start

Check logs:
```bash
tail -f /var/log/dhcp_manager.log
journalctl -u isc-dhcp-server -f
```

Validate configuration manually:
```bash
dhcpd -t -cf /etc/dhcp/dhcpd.conf
```

### Permission Errors

Ensure the script runs with appropriate permissions:
```bash
sudo ./cli.py list
```

Or use sudo for web interface:
```bash
sudo python3 web.py
```

### PXE Boot Not Working

Check TFTP directory permissions:
```bash
ls -la /var/lib/tftpboot/pxelinux.cfg/
```

Verify symlinks:
```bash
cd /var/lib/tftpboot/pxelinux.cfg/
ls -l | grep -E '^l'
```

## 📚 Development

### Adding New Features

1. **Add validation** in `utils/validators.py`
2. **Add exceptions** in `exceptions.py` if needed
3. **Implement logic** in appropriate manager class
4. **Add tests** in `tests/`
5. **Update CLI/Web** interfaces

### Code Style

- Follow PEP 8
- Use type hints
- Document with docstrings
- Keep functions focused (Single Responsibility)
- Handle errors explicitly

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

[Your License Here]

## 👥 Authors

- Original: [Original Author]
- Refactored: [Your Name]

## 🙏 Acknowledgments

- ISC DHCP Server project
- Flask framework
- Python community

---

## Migration Guide (From Old Version)

### What Changed

1. **File Structure**
   - `dhcp_manager.py` → Split into `managers/dhcp_manager.py` and `managers/pxe_manager.py`
   - `colors.py` → Moved to `utils/colors.py`
   - `logger.py` → Moved to `utils/logger.py`
   - Added: `config.py`, `exceptions.py`, `utils/validators.py`

2. **Imports**
   ```python
   # Old
   from dhcp_manager import DHCPManager
   from colors import green, red
   
   # New
   from managers.dhcp_manager import DHCPManager
   from utils.colors import green, red
   ```

3. **External Scripts**
   - `convert.sh` functionality → `PXEBootManager.ip_to_hex()` / `hex_to_ip()`
   - `manage_links_from_ip.py` → `PXEBootManager.create_boot_link()` / `delete_boot_link()`

### Migration Steps

1. **Backup your data**
   ```bash
   sudo cp /etc/dhcp/dhcpd.conf /etc/dhcp/dhcpd.conf.backup
   ```

2. **Update imports** in any custom scripts

3. **Replace external script calls** with new Python methods

4. **Test thoroughly** in a development environment first

5. **Update systemd services** if applicable

---

**For questions or issues, please open a GitHub issue or contact the maintainers.**

## First-run Setup Wizard

This package includes a first-run setup wizard for fresh installations. On a new host, run:

```bash
sudo python3 web.py
```

Then open the web UI on port `5000`. If DHCP/TFTP/PXE setup is not completed, the app redirects to `/setup/checks` instead of the login page. The wizard can install required packages, configure the DHCP interface, generate DHCP/TFTP config, copy PXELINUX files, and create the default TFTP tree.

For development without system setup redirection:

```bash
DHCP_MANAGER_SKIP_SETUP=1 python3 web.py
```

See `SETUP_WIZARD.md` for details.
