# First-run Setup Wizard

This branch/package adds a first-run bootstrap wizard to the Flask web UI.

## What changed

When `python3 web.py` starts, the app checks whether first-run setup is completed. If not, it redirects to:

```text
/setup/checks
```

The normal login page is shown only after setup succeeds or when setup is skipped explicitly.

## Main features

- Detect OS and package manager.
- Detect DHCP/TFTP/PXELINUX related packages.
- Detect non-loopback network interfaces and IPv4 networks.
- Let the user choose or type the DHCP interface.
- Validate DHCP subnet, range, gateway, DNS, `next-server`, boot filename, and TFTP root.
- Warn when the selected interface network differs from the managed DHCP subnet.
- Generate an empty local subnet declaration when needed so `isc-dhcp-server`/`dhcpd` can bind cleanly.
- Preview generated config before applying.
- Back up existing configs to `/var/backups/dhcp-manager`.
- Install packages, configure DHCP/TFTP, create TFTP tree, copy PXELINUX files, create default menus, validate DHCP syntax, and restart services.
- Mark setup as complete in `/var/lib/dhcp-manager/setup_state.json`.

## First run

Run as root for the first setup:

```bash
sudo python3 web.py
```

Open:

```text
http://SERVER_IP:5000
```

You will be redirected to the setup wizard.

## Skip setup during development

For local development or tests where you do not want first-run setup redirection:

```bash
DHCP_MANAGER_SKIP_SETUP=1 python3 web.py
```

## Supported systems

The wizard is designed first for Debian/Ubuntu/Lubuntu using:

```bash
isc-dhcp-server
 tftpd-hpa
syslinux-common
pxelinux
```

RHEL/Rocky/Fedora detection exists, but should be tested carefully before using on production.

## Files added

```text
setup_wizard/__init__.py
setup_wizard/manager.py
templates/setup_checks.html
templates/setup_config.html
templates/setup_review.html
templates/setup_done.html
```

## Files modified

```text
web.py
```

## Important notes

This wizard writes system files. Always review the preview page before applying.
The wizard intentionally does not remove existing DHCP host reservations after setup; existing `/etc/dhcp/dhcpd.conf` is backed up before replacement.


## iPXE first-run setup

The setup wizard automatically inserts an ISC DHCP user-class condition so clients already running iPXE receive `ipxe/ipxe.ipxe`, while normal PXE clients continue to receive the selected boot filename such as `pxelinux.0`. The wizard also creates the `ipxe/ipxe.ipxe` dispatcher under the selected TFTP root.
