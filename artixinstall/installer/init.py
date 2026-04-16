"""
artixinstall.installer.init — Init system selection and service management.

Handles the selection of one of the four supported init systems (OpenRC,
runit, s6, dinit) and provides service installation/enablement using the
service mapping from data/services.json.
"""

import json
import os
from pathlib import Path

from artixinstall.utils.shell import run
from artixinstall.utils.log import log_info, log_error
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_selection_menu

# Supported init systems and their base package sets
INIT_SYSTEMS = {
    "openrc": {
        "label": "OpenRC",
        "base_packages": ["base", "base-devel", "openrc", "elogind-openrc"],
    },
    "runit": {
        "label": "runit",
        "base_packages": ["base", "base-devel", "runit", "elogind-runit"],
    },
    "s6": {
        "label": "s6",
        "base_packages": ["base", "base-devel", "s6-base", "elogind-s6"],
    },
    "dinit": {
        "label": "dinit",
        "base_packages": ["base", "base-devel", "dinit", "elogind-dinit"],
    },
}

# Cache for loaded services data
_services_data: dict | None = None

SERVICE_ENABLE_ALIASES = {
    "cups": {"openrc": ["cupsd"]},
    "alsa": {"openrc": ["alsasound"]},
}


def _get_data_dir() -> Path:
    """Get the path to the data directory."""
    return Path(__file__).parent.parent / "data"


def load_services() -> dict:
    """
    Load the services mapping from data/services.json.

    Returns a dict: service_name -> { init_name -> { package, enable } }
    """
    global _services_data
    if _services_data is not None:
        return _services_data

    data_file = _get_data_dir() / "services.json"
    try:
        with open(data_file, "r") as f:
            _services_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log_error(f"Failed to load services.json: {e}")
        _services_data = {}

    return _services_data


def get_base_packages(init_system: str) -> list[str]:
    """Return the base package list for a given init system."""
    info = INIT_SYSTEMS.get(init_system)
    if info is None:
        log_error(f"Unknown init system: {init_system}")
        return ["base", "base-devel"]
    return list(info["base_packages"])


def get_service_package(service_name: str, init_system: str) -> str | None:
    """
    Get the package name for a service under a given init system.

    Returns the package name, or None if not found.
    """
    services = load_services()
    svc = services.get(service_name, {})
    init_info = svc.get(init_system, {})
    return init_info.get("package")


def get_service_enable_cmd(service_name: str, init_system: str) -> str | None:
    """
    Get the command to enable a service under a given init system.

    Returns the enable command, or None if not found.
    """
    services = load_services()
    svc = services.get(service_name, {})
    init_info = svc.get(init_system, {})
    return init_info.get("enable")


def get_all_service_packages(service_names: list[str],
                              init_system: str) -> list[str]:
    """
    Get all packages needed for a list of services under a given init.

    Returns a deduplicated list of package names.
    """
    packages = []
    seen = set()
    for svc in service_names:
        pkg = get_service_package(svc, init_system)
        if pkg and pkg not in seen:
            packages.append(pkg)
            seen.add(pkg)
    return packages


def enable_service(service_name: str, init_system: str) -> tuple[bool, str]:
    """
    Enable a service inside the chroot using the correct init-specific command.

    Returns (success, error_message).
    """
    cmd = get_service_enable_cmd(service_name, init_system)
    if cmd is None:
        msg = f"No enable command found for {service_name} on {init_system}"
        log_error(msg)
        return False, msg

    if init_system == "openrc":
        service_script = service_name
        aliases = SERVICE_ENABLE_ALIASES.get(service_name, {}).get(init_system, [])
        candidates = [service_name, *aliases]

        script_exists = False
        for candidate in candidates:
            rc_check, _, _ = run(["test", "-f", f"/etc/init.d/{candidate}"], chroot=True)
            rc_check2, _, _ = run(["rc-service", f"{candidate}", "status"], chroot=True)
            if rc_check == 0 or rc_check2 == 0:
                service_script = candidate
                script_exists = True
                break

        if not script_exists:
            pkg = get_service_package(service_name, init_system)
            if pkg:
                rc_pkg, _, stderr_pkg = run(
                    ["pacman", "-S", "--noconfirm", "--needed", pkg],
                    chroot=True,
                    timeout=1800,
                )
                if rc_pkg != 0:
                    return False, f"Failed to install {pkg} for {service_name}: {stderr_pkg}"

                for candidate in candidates:
                    rc_check, _, _ = run(["test", "-f", f"/etc/init.d/{candidate}"], chroot=True)
                    if rc_check == 0:
                        service_script = candidate
                        script_exists = True
                        break

        if script_exists and cmd.startswith("rc-update add "):
            cmd = f"rc-update add {service_script} default"

    rc, stdout, stderr = run(cmd, chroot=True)
    if rc != 0:
        aliases = SERVICE_ENABLE_ALIASES.get(service_name, {}).get(init_system, [])
        if init_system == "openrc" and cmd.startswith("rc-update add "):
            for alias in aliases:
                alias_cmd = f"rc-update add {alias} default"
                rc_alias, _, stderr_alias = run(alias_cmd, chroot=True)
                if rc_alias == 0:
                    log_info(f"Enabled service {service_name} via alias {alias} ({init_system})")
                    return True, ""
                stderr = stderr_alias or stderr

        return False, f"Failed to enable {service_name}: {stderr}"

    log_info(f"Enabled service {service_name} ({init_system})")
    return True, ""


def enable_services(service_names: list[str],
                    init_system: str) -> tuple[bool, str]:
    """
    Enable multiple services inside the chroot.

    Returns (True, "") if all succeeded, or (False, first_error) if any failed.
    """
    errors = []
    for svc in service_names:
        success, err = enable_service(svc, init_system)
        if not success:
            errors.append(err)

    if errors:
        return False, "; ".join(errors)
    return True, ""


def configure_init(screen: Screen) -> str | None:
    """
    Interactive init system selection.

    Returns the init system key (e.g. "openrc"), or None if cancelled.
    """
    options = [info["label"] for info in INIT_SYSTEMS.values()]
    keys = list(INIT_SYSTEMS.keys())

    selected = run_selection_menu(screen, "Select init system", options,
                                  footer="↑↓ Navigate  Enter Select  ESC Back")
    if selected is None:
        return None

    idx = options.index(selected)
    return keys[idx]
