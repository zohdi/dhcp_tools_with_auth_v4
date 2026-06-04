#!/usr/bin/env python3
"""
DHCP Manager Web Interface - Flask web application for DHCP management.
"""
import traceback
from typing import Tuple, Any
from functools import wraps
import bcrypt
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response, send_file

from config import config
from managers.dhcp_manager import DHCPManager
from managers.pxe_manager import PXEBootManager
from exceptions import DHCPManagerError, PXEBootError
from utils.logger import get_logger


# Initialize Flask app
app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# Initialize managers
dhcp_mgr = DHCPManager()
pxe_mgr = PXEBootManager()
logger = get_logger("dhcp-web")


# ============================================================
#                   UTILITY FUNCTIONS
# ============================================================
def check_admin_password(plain: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            config.ADMIN_PASSWORD_HASH.encode("utf-8")
        )
    except Exception:
        return False

def safe_execute(func, *args, **kwargs) -> Tuple[bool, Any]:
    """
    Safely execute a function and handle exceptions.
    
    Args:
        func: Function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Tuple of (success: bool, result_or_error_message)
    """
    try:
        result = func(*args, **kwargs)
        return True, result
    except DHCPManagerError as e:
        logger.error(f"DHCP Manager error: {e}")
        return False, str(e)
    except PXEBootError as e:
        logger.error(f"PXE Boot error: {e}")
        return False, str(e)
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Unexpected error:\n{tb}")
        return False, str(e)




# ============================================================
#                   AUTH (ADMIN / READ-ONLY)
# ============================================================

def require_login(view_func):
    """Require any authenticated session (admin or readonly)."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("admin", "readonly"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper


def require_admin(view_func):
    """Require admin session."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("🔒 Admin privileges required for that action.", "warning")
            return redirect(url_for("index"))
        return view_func(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page. Supports Admin login + Read-Only login."""
    if request.method == "POST":
        mode = (request.form.get("mode") or "").strip().lower()

        # Read-only login: no password required
        if mode == "readonly":
            session.clear()
            session["role"] = "readonly"
            session["username"] = "ReadOnly"
            flash("👀 Logged in with read-only access.", "info")
            return redirect(url_for("index"))

        # Admin login: requires username + password
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if username == config.ADMIN_USERNAME and check_admin_password(password): #password == config.ADMIN_PASSWORD:
            session.clear()
            session["role"] = "admin"
            session["username"] = username
            flash("✅ Logged in as Admin.", "success")
            return redirect(url_for("index"))

        flash("❌ Invalid username or password.", "danger")

    return render_template("login.html", admin_username=config.ADMIN_USERNAME)


@app.route("/logout")
def logout():
    """Clear session and return to login."""
    session.clear()
    flash("👋 Logged out.", "info")
    return redirect(url_for("login"))

# ============================================================
#                   ROUTES - MAIN PAGES
# ============================================================

@app.route("/")
@require_login
def index():
    """Main page: Display all DHCP entries with boot device info."""
    success, result = safe_execute(dhcp_mgr.get_all_entries)
    
    if not success:
        flash(f"⚠️ Failed to load DHCP entries: {result}", "danger")
        entries = []
    else:
        entries = result
        
        # Add boot device information to each entry
        for entry in entries:
            try:
                # Get the actual boot device
                boot_device = pxe_mgr.get_boot_device(entry["ip"])
                entry["boot_device"] = boot_device
                
                # Also get the raw target for debugging
                boot_target = pxe_mgr.get_boot_target(entry["ip"])
                entry["boot_target"] = boot_target if boot_target else "No link configured"
                entry["ipxe_url"] = pxe_mgr.get_dynamic_boot_url(entry["ip"])
                entry["ipxe_mac_url"] = ""
                
                logger.debug(f"Entry {entry['hostname']} ({entry['ip']}): device={boot_device}, target={boot_target}")
                
            except Exception as e:
                logger.error(f"Failed to get boot device for {entry['ip']}: {e}")
                entry["boot_device"] = "default"
                entry["boot_target"] = "Error reading boot config"
                entry["ipxe_url"] = ""
                entry["ipxe_mac_url"] = ""

    boot_profiles = pxe_mgr.discover_boot_profiles()
    return render_template("index.html", entries=entries, boot_profiles=boot_profiles, role=session.get("role"), username=session.get("username"))


@app.route("/add", methods=["GET", "POST"])
@require_admin
def add_entry():
    """Add a new DHCP entry."""
    if request.method == "POST":
        hostname = request.form.get("hostname", "").strip()
        mac = request.form.get("mac", "").strip()
        ip = request.form.get("ip", "").strip()
        
        success, result = safe_execute(
            dhcp_mgr.add_entry,
            hostname, mac, ip
        )
        
        if success:
            flash(f"✅ Successfully added entry: {hostname}", "success")
            return redirect(url_for("index"))
        else:
            flash(f"❌ Failed to add entry: {result}", "danger")
    
    return render_template("add_edit.html", action="Add", entry=None, role=session.get("role"), username=session.get("username"))


@app.route("/edit/<identifier>", methods=["GET", "POST"])
@require_admin
def edit_entry(identifier: str):
    """Edit an existing DHCP entry."""
    # Get current entry
    success, entry = safe_execute(dhcp_mgr.find_entry, identifier)
    
    if not success or entry is None:
        flash(f"⚠️ Entry not found: {identifier}", "warning")
        return redirect(url_for("index"))
    
    if request.method == "POST":
        # Get form data
        new_hostname = request.form.get("hostname", "").strip() or None
        new_mac = request.form.get("mac", "").strip() or None
        new_ip = request.form.get("ip", "").strip() or None
        
        success, result = safe_execute(
            dhcp_mgr.modify_entry,
            identifier,
            new_hostname=new_hostname,
            new_mac=new_mac,
            new_ip=new_ip
        )
        
        if success:
            flash("✅ Entry updated successfully", "success")
            return redirect(url_for("index"))
        else:
            flash(f"❌ Failed to update entry: {result}", "danger")
    
    return render_template("add_edit.html", action="Edit", entry=entry, role=session.get("role"), username=session.get("username"))


@app.route("/delete/<identifier>", methods=["POST"])
@require_admin
def delete_entry(identifier: str):
    """Delete a DHCP entry."""
    success, result = safe_execute(dhcp_mgr.remove_entry, identifier)
    
    if success:
        flash(f"🗑️ Successfully deleted entry: {identifier}", "success")
    else:
        flash(f"❌ Failed to delete entry: {result}", "danger")
    
    return redirect(url_for("index"))


# ============================================================
#                   ROUTES - PXE BOOT
# ============================================================

@app.route("/bootdevice/<ip>", methods=["POST"])
@require_admin
def set_boot_device(ip: str):
    """Set PXELINUX and iPXE boot profile for a client IP."""
    boot_device = request.form.get("boot_device", "").strip()

    if not boot_device:
        flash("❌ Boot device not specified", "danger")
        return redirect(url_for("index"))

    if not pxe_mgr.boot_profile_exists(boot_device):
        flash(f"❌ Boot profile does not exist: {boot_device}", "danger")
        return redirect(url_for("index"))

    # Keep current feature working: update the legacy PXELINUX per-IP symlink.
    success, result = safe_execute(pxe_mgr.create_boot_link, ip, boot_device)
    if not success:
        flash(f"❌ Failed to update PXELINUX boot device: {result}", "danger")
        return redirect(url_for("index"))

    # New feature: create generated iPXE file for this client by IP.
    # Even `default` gets a generated client file, so the iPXE status stays
    # explicit and the selected GUI profile applies to both PXELINUX and iPXE.
    script_success, script_result = safe_execute(
        pxe_mgr.write_client_ipxe_scripts,
        boot_device,
        ip=ip,
    )
    if not script_success:
        flash(f"⚠️ PXELINUX link was updated, but iPXE override creation failed: {script_result}", "warning")
        return redirect(url_for("index"))

    flash(f"✅ Boot profile updated for {ip} → {boot_device}", "success")
    return redirect(url_for("index"))


@app.route("/query/<ip>")
@require_login
def query_boot(ip: str):
    """Query the PXE boot configuration for an IP (AJAX endpoint)."""
    try:
        target = pxe_mgr.get_boot_target(ip)
        device = pxe_mgr.get_boot_device(ip)
        hex_name = pxe_mgr.ip_to_hex(ip)
        link_path = pxe_mgr.get_link_path(ip)
        ipxe_url = pxe_mgr.get_dynamic_boot_url(ip)
        client_script_path = pxe_mgr.get_client_script_path(ip)
        dispatcher_path = pxe_mgr.get_ipxe_script_path()
        
        if not target:
            target = "default (no assigned link file)"
        
        return jsonify({
            "ip": ip,
            "hex_filename": hex_name,
            "link_path": str(link_path),
            "target": target,
            "device": device,
            "ipxe_url": ipxe_url,
            "ipxe_ip_script_path": str(client_script_path),
            "ipxe_ip_script_exists": client_script_path.exists(),
            "ipxe_dispatcher_path": str(dispatcher_path),
            "ipxe_dispatcher_tftp": pxe_mgr.get_ipxe_script_tftp_filename(),
            "link_exists": link_path.exists(),
            "success": True
        })
        
    except Exception as e:
        logger.error(f"Failed to query boot config for {ip}: {e}")
        return jsonify({
            "ip": ip,
            "target": "Error retrieving boot configuration",
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
#                   ROUTES - iPXE DISPATCHER
# ============================================================

@app.route("/ipxe/boot")
def ipxe_boot_auto():
    """Backward-compatible endpoint: return the default dispatcher script."""
    return Response(pxe_mgr.generate_default_ipxe_script(), mimetype="text/plain")


@app.route("/ipxe/install-default", methods=["POST"])
@require_admin
def ipxe_install_default():
    """Generate/install ipxe/ipxe.ipxe into the TFTP root."""
    success, result = safe_execute(pxe_mgr.write_default_ipxe_script)
    if success:
        flash(f"✅ Installed iPXE dispatcher: {result}", "success")
    else:
        flash(f"❌ Failed to install iPXE dispatcher: {result}", "danger")
    return redirect(url_for("index"))


@app.route("/ipxe/<path:filename>")
def ipxe_static_script(filename: str):
    """Serve iPXE scripts from <tftp-root>/ipxe.

    Missing per-client scripts intentionally return 404 so ipxe.ipxe can try the
    next lookup target and eventually boot local disk.
    """
    if not filename.endswith(".ipxe"):
        return Response("Not found\n", mimetype="text/plain", status=404)

    # Safe path resolution inside the configured iPXE directory.
    try:
        requested = (pxe_mgr.ipxe_dir / filename).resolve()
        root = pxe_mgr.ipxe_dir.resolve()
        if root not in requested.parents and requested != root:
            return Response("Not found\n", mimetype="text/plain", status=404)
    except Exception:
        return Response("Not found\n", mimetype="text/plain", status=404)

    if not requested.exists() or not requested.is_file():
        return Response("Not found\n", mimetype="text/plain", status=404)
    return send_file(requested, mimetype="text/plain")


@app.route("/ipxe/snippet")
@require_admin
def ipxe_dhcp_snippet():
    """Display the ISC DHCP snippet needed to enable iPXE dispatching."""
    return Response(pxe_mgr.generate_isc_dhcp_ipxe_snippet(), mimetype="text/plain")


# ============================================================
#                   ROUTES - SERVICE MANAGEMENT
# ============================================================

@app.route("/restart", methods=["POST"])
@require_admin
def restart_dhcp_service():
    """Manually restart the DHCP service."""
    success, result = safe_execute(
        dhcp_mgr.restart_service,
        config.DHCP_SERVICE
    )
    
    if success:
        flash("🔄 DHCP service restarted successfully", "success")
    else:
        flash(f"❌ Failed to restart DHCP service: {result}", "danger")
    
    return redirect(url_for("index"))


# ============================================================
#                   ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    flash("⚠️ Page not found", "warning")
    return redirect(url_for("index"))


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    tb = traceback.format_exc()
    logger.error(f"Internal server error:\n{tb}")
    flash("❌ A critical server error occurred. Please check the logs.", "danger")
    return redirect(url_for("index"))


# ============================================================
#                   APPLICATION STARTUP
# ============================================================

def main():
    """Run the Flask application."""
    logger.info(f"Starting DHCP Manager Web Interface on {config.FLASK_HOST}:{config.FLASK_PORT}")
    
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG
    )


if __name__ == "__main__":
    main()
