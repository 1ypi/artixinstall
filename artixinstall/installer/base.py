"""
artixinstall.installer.base — Base system installation (basestrap) and fstab generation.

Handles installing the base Artix system into the target mount point and
generating/verifying the fstab file.
"""

import os
import shutil

from artixinstall.utils.shell import run, run_live_result, command_exists, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.installer.init import get_base_packages, get_all_service_packages


def install_base_system(init_system: str,
                        extra_packages: list[str] | None = None,
                        kernel: str = "linux",
                        live_output: bool = False) -> tuple[bool, str]:
    """
    Install the base Artix system using basestrap.

    Parameters
    ----------
    init_system : str
        The chosen init system (openrc, runit, s6, dinit).
    extra_packages : list[str] or None
        Additional packages to install alongside the base set.
    kernel : str
        Kernel package name (default: linux).

    Returns
    -------
    tuple[bool, str]
        (success, error_message)
    """
    packages = get_base_packages(init_system)

    # Add kernel, headers, and firmware
    packages.extend([kernel, f"{kernel}-headers", "linux-firmware"])

    # Add essential tools
    packages.extend([
        "grub",
        "efibootmgr",
        "sudo",
        "nano",
        "vim",
        "mkinitcpio",
    ])

    # Add extra packages
    if extra_packages:
        packages.extend(extra_packages)

    # Deduplicate while preserving order
    seen = set()
    unique_packages = []
    for pkg in packages:
        if pkg not in seen:
            unique_packages.append(pkg)
            seen.add(pkg)

    success, err = _validate_package_list(unique_packages)
    if not success:
        return False, err

    pkg_str = " ".join(unique_packages)
    log_info(f"Installing base system: basestrap {MOUNT_POINT} {pkg_str}")

    if live_output:
        rc, err = run_live_result(
            ["basestrap", MOUNT_POINT, *unique_packages],
            timeout=3600,
        )
        if rc != 0:
            return False, f"basestrap failed: {err}"
        log_info("Base system installed successfully")
        return True, ""

    rc, stdout, stderr = run(
        ["basestrap", MOUNT_POINT, *unique_packages],
        timeout=3600,  # 60 minute timeout for large package sets
    )

    if rc != 0:
        return False, f"basestrap failed: {stderr}"

    log_info("Base system installed successfully")
    return True, ""


def _validate_package_list(packages: list[str]) -> tuple[bool, str]:
    """
    Check that requested packages exist in the configured pacman repositories.
    """
    missing = []

    for pkg in packages:
        rc, _, stderr = run(["pacman", "-Si", pkg], timeout=30)
        if rc != 0:
            missing.append(pkg)
            if stderr.strip():
                log_error(f"Package lookup failed for {pkg}: {stderr.strip()}")

    if missing:
        return False, "These packages were not found in the current repositories: " + ", ".join(missing)

    return True, ""


def install_extra_packages(packages: list[str]) -> tuple[bool, str]:
    """
    Install additional packages inside the chroot using pacman.

    Used for packages that need to be installed after basestrap
    (e.g., AUR helpers, packages with complex dependencies).
    """
    if not packages:
        return True, ""

    # Deduplicate
    seen = set()
    unique = []
    for p in packages:
        if p not in seen:
            unique.append(p)
            seen.add(p)

    pkg_str = " ".join(unique)
    log_info(f"Installing extra packages: {pkg_str}")

    rc, _, stderr = run(
        ["pacman", "-S", "--noconfirm", *unique],
        chroot=True,
        timeout=1800,
    )

    if rc != 0:
        return False, f"Failed to install extra packages: {stderr}"

    return True, ""


def generate_fstab() -> tuple[bool, str]:
    """
    Generate /etc/fstab for the installed system.

    Tries fstabgen/genfstab first; falls back to manual generation using blkid
    if neither is available.

    Returns (success, error_message).
    """
    fstab_path = os.path.join(MOUNT_POINT, "etc", "fstab")

    # Ensure /etc exists
    os.makedirs(os.path.join(MOUNT_POINT, "etc"), exist_ok=True)

    # Try fstabgen (Artix) first, then genfstab (Arch compat)
    for cmd in ["fstabgen", "genfstab"]:
        if not command_exists(cmd):
            continue
        rc, stdout, stderr = run([cmd, "-U", MOUNT_POINT])
        if rc == 0 and stdout.strip():
            try:
                with open(fstab_path, "w") as f:
                    f.write(stdout)
                log_info(f"Generated fstab with {cmd}")
                return _verify_fstab(fstab_path)
            except OSError as e:
                return False, f"Failed to write fstab: {e}"

    # Fallback: generate manually using blkid and current mounts
    log_info("genfstab/fstabgen not available, generating fstab manually")
    return _generate_fstab_manual(fstab_path)


def _generate_fstab_manual(fstab_path: str) -> tuple[bool, str]:
    """
    Manually generate fstab by reading current mounts and resolving UUIDs.
    """
    lines = [
        "# /etc/fstab: static file system information.",
        "# Generated by artixinstall",
        "#",
        "# <file system>  <mount point>  <type>  <options>  <dump>  <pass>",
        "",
    ]

    # Read current mounts for /mnt
    rc, stdout, _ = run("findmnt -rn -o SOURCE,TARGET,FSTYPE,OPTIONS")
    if rc != 0:
        return False, "Failed to read mount table"

    for line in stdout.strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue

        source, target, fstype, options = parts[0], parts[1], parts[2], parts[3]

        # Only include mounts under /mnt
        if not target.startswith(MOUNT_POINT):
            continue

        # Get UUID for this device
        rc2, uuid_out, _ = run(["blkid", "-s", "UUID", "-o", "value", source])
        if rc2 == 0 and uuid_out.strip():
            fs_spec = f"UUID={uuid_out.strip()}"
        else:
            fs_spec = source

        # Determine mount point relative to target system
        mount_point = target.replace(MOUNT_POINT, "", 1)
        if not mount_point:
            mount_point = "/"

        # Determine dump and pass values
        dump = "0"
        if mount_point == "/":
            passno = "1"
        elif mount_point == "/boot":
            passno = "2"
        else:
            passno = "2"

        # Clean up options - use reasonable defaults per fs type
        if fstype == "vfat":
            clean_opts = "defaults,umask=0077"
        elif fstype == "btrfs":
            clean_opts = "defaults,compress=zstd,noatime"
        elif fstype in ("ext4", "ext2"):
            clean_opts = "defaults,relatime"
        elif fstype == "xfs":
            clean_opts = "defaults,relatime"
        elif fstype == "f2fs":
            clean_opts = "defaults,noatime"
        else:
            clean_opts = "defaults"

        lines.append(f"{fs_spec}\t{mount_point}\t{fstype}\t{clean_opts}\t{dump}\t{passno}")

    # Check for swap
    rc, stdout, _ = run("swapon --show=NAME --noheadings")
    if rc == 0 and stdout.strip():
        for swap_dev in stdout.strip().splitlines():
            swap_dev = swap_dev.strip()
            if swap_dev:
                rc2, uuid_out, _ = run(["blkid", "-s", "UUID", "-o", "value", swap_dev])
                if rc2 == 0 and uuid_out.strip():
                    fs_spec = f"UUID={uuid_out.strip()}"
                else:
                    fs_spec = swap_dev
                lines.append(f"{fs_spec}\tnone\tswap\tdefaults\t0\t0")

    lines.append("")

    try:
        with open(fstab_path, "w") as f:
            f.write("\n".join(lines))
    except OSError as e:
        return False, f"Failed to write fstab: {e}"

    return _verify_fstab(fstab_path)


def _verify_fstab(fstab_path: str) -> tuple[bool, str]:
    """Verify that the fstab file was written and is non-empty."""
    try:
        with open(fstab_path, "r") as f:
            content = f.read()
        if not content.strip():
            return False, "Generated fstab is empty"
        # Check that at least root is listed
        if "/" not in content:
            return False, "fstab does not contain a root (/) entry"
        log_info("fstab verified successfully")
        return True, ""
    except OSError as e:
        return False, f"Failed to verify fstab: {e}"


def copy_mirrorlist() -> tuple[bool, str]:
    """
    Copy the live environment's mirror lists to the target system.
    """
    mirror_sources = [
        "/etc/pacman.d/mirrorlist",
        "/etc/pacman.d/mirrorlist-arch",
    ]

    target_dir = os.path.join(MOUNT_POINT, "etc", "pacman.d")
    os.makedirs(target_dir, exist_ok=True)

    for src in mirror_sources:
        if os.path.isfile(src):
            dst = os.path.join(target_dir, os.path.basename(src))
            try:
                shutil.copy2(src, dst)
                log_info(f"Copied {src} → {dst}")
            except OSError as e:
                log_error(f"Failed to copy {src}: {e}")

    return True, ""


def copy_pacman_conf() -> tuple[bool, str]:
    """
    Copy /etc/pacman.conf to the target, preserving repo configuration.
    """
    src = "/etc/pacman.conf"
    dst = os.path.join(MOUNT_POINT, "etc", "pacman.conf")

    if os.path.isfile(src):
        try:
            shutil.copy2(src, dst)
            log_info("Copied pacman.conf to target")
        except OSError as e:
            log_error(f"Failed to copy pacman.conf: {e}")

    return True, ""
