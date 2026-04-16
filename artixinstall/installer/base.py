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


PACKAGE_ALIASES = {
    "plasma": ["plasma-meta", "plasma"],
    "kde-applications": ["kde-applications-meta", "kde-applications"],
    "xf86-video-amdgpu": ["xf86-video-amdgpu", "xlibre-xf86-video-amdgpu", "xlibre-video-amdgpu"],
    "xf86-video-intel": ["xf86-video-intel", "xlibre-xf86-video-intel", "xlibre-video-intel"],
    "xf86-video-nouveau": ["xf86-video-nouveau", "xlibre-xf86-video-nouveau", "xlibre-video-nouveau"],
    "xf86-video-vmware": ["xf86-video-vmware", "xlibre-xf86-video-vmware", "xlibre-video-vmware"],
}

_PREFERRED_PROVIDER_PACKAGES = [
    "iptables-nft",
    "noto-fonts",
    "noto-fonts-emoji",
]

# Obsolete split packages that conflict with their newer unified replacements.
# These are passed to basestrap/pacman via --ignore so they don't block
# installation when a package group (e.g. gnome-extra) pulls the replacement.
_IGNORED_CONFLICTS = [
    "gnome-builder-clang",     # merged into gnome-builder >=49
    "gnome-builder-flatpak",   # merged into gnome-builder >=49
]


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

    # Add essential tools (bootloader packages are added separately
    # via get_bootloader_packages() in the orchestration layer)
    packages.extend([
        "sudo",
        "nano",
        "vim",
        "mkinitcpio",
        "xdg-user-dirs",
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

    success, resolved_packages, err = _validate_package_list(unique_packages)
    if not success:
        return False, err

    pkg_str = " ".join(resolved_packages)
    log_info(f"Installing base system: basestrap {MOUNT_POINT} {pkg_str}")

    # Build --ignore flags for known conflicting obsolete packages
    ignore_args = []
    if _IGNORED_CONFLICTS:
        ignore_args = ["--ignore", ",".join(_IGNORED_CONFLICTS)]
        log_info(f"Ignoring known conflicting packages: {', '.join(_IGNORED_CONFLICTS)}")

    if live_output:
        rc, err = run_live_result(
            ["basestrap", MOUNT_POINT, *ignore_args, *resolved_packages],
            timeout=3600,
        )
        if rc != 0:
            return False, f"basestrap failed: {err}"
        log_info("Base system installed successfully")
        return True, ""

    rc, stdout, stderr = run(
        ["basestrap", MOUNT_POINT, *ignore_args, *resolved_packages],
        timeout=3600,  # 60 minute timeout for large package sets
    )

    if rc != 0:
        return False, f"basestrap failed: {stderr}"

    log_info("Base system installed successfully")
    return True, ""


def _package_exists(pkg: str) -> bool:
    """Check whether an install target exists as package or package group."""
    rc, _, _ = run(["pacman", "-Si", pkg], timeout=30)
    if rc == 0:
        return True

    rc_group, group_out, _ = run(["pacman", "-Sg", pkg], timeout=30)
    return rc_group == 0 and bool(group_out.strip())


def _group_packages(group_name: str) -> list[str]:
    """Expand a pacman package group into concrete package names."""
    rc, stdout, _ = run(["pacman", "-Sg", group_name], timeout=30)
    if rc != 0 or not stdout.strip():
        return []

    packages: list[str] = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == group_name:
            packages.append(parts[1])
    return packages


def _candidate_names(pkg: str) -> list[str]:
    """Return candidate Artix package names for a requested install target."""
    candidates = PACKAGE_ALIASES.get(pkg, [pkg])

    if pkg.startswith("xf86-video-"):
        suffix = pkg.removeprefix("xf86-video-")
        candidates.extend([
            f"xlibre-xf86-video-{suffix}",
            f"xlibre-video-{suffix}",
        ])

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def _validate_package_list(packages: list[str]) -> tuple[bool, list[str], str]:
    """
    Check that requested install targets exist in the configured pacman repos.

    Artix desktop selections may include both package names and package-group
    names (for example `gnome`, `xfce4`, `mate-extra`, `lxqt`). We accept
    either here so valid group-based DE selections are not rejected before
    `basestrap`.
    """
    missing = []
    resolved = []

    for pkg in packages:
        found = None
        for candidate in _candidate_names(pkg):
            if _package_exists(candidate):
                found = candidate
                break

        if found is None:
            missing.append(pkg)
            log_error(f"Package lookup failed for {pkg}; tried: {', '.join(_candidate_names(pkg))}")
            continue

        group_members = _group_packages(found)
        if group_members:
            kept = [member for member in group_members if member not in _IGNORED_CONFLICTS]
            if kept:
                resolved.extend(kept)
                log_info(f"Expanded group {found} -> {', '.join(kept[:8])}" + (" ..." if len(kept) > 8 else ""))
            continue

        resolved.append(found)
        if found != pkg:
            log_info(f"Resolved package {pkg} -> {found}")

    if missing:
        return False, [], "These packages or package groups were not found in the current repositories: " + ", ".join(missing)

    final_resolved: list[str] = []
    seen: set[str] = set()
    for preferred in _PREFERRED_PROVIDER_PACKAGES:
        if preferred not in seen and _package_exists(preferred):
            final_resolved.append(preferred)
            seen.add(preferred)
    for pkg in resolved:
        if pkg not in seen:
            final_resolved.append(pkg)
            seen.add(pkg)

    return True, final_resolved, ""


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


def setup_mirrorlist(mode: str = "fastest") -> tuple[bool, str]:
    """
    Prepare the live mirrorlist for basestrap and copy it into the target.

    Modes:
    - fastest: rank the current Artix mirrorlist and keep the top mirrors
    - live/default: use the current live mirror configuration as-is
    - custom URL: write a single custom server line elsewhere before calling this
    """
    mirror_path = "/etc/pacman.d/mirrorlist"

    if mode == "fastest":
        if not command_exists("rankmirrors"):
            return False, "Fastest-mirror mode requires `rankmirrors`, but it is not available in the live environment."
        if not os.path.isfile(mirror_path):
            return False, f"Mirror list not found: {mirror_path}"

        rc, stdout, stderr = run(["rankmirrors", "-n", "6", mirror_path], timeout=300)
        if rc != 0:
            return False, f"Failed to rank Artix mirrors: {stderr}"
        if "Server =" not in stdout:
            return False, "rankmirrors did not return a usable mirror list."

        try:
            with open(mirror_path, "w") as f:
                f.write(stdout)
            log_info("Ranked Artix mirrors and selected the fastest entries")
        except OSError as e:
            return False, f"Failed to write ranked mirror list: {e}"

    return copy_mirrorlist()


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


def install_aur_packages(aur_packages: list[str],
                         username: str) -> tuple[bool, str]:
    """Install packages from the AUR inside the chroot.

    Builds and installs ``yay`` (AUR helper) first, then uses it to install
    the requested packages.  ``yay`` handles recursive AUR dependency
    resolution automatically (e.g. mangowm-git → scenefx0.4).

    Parameters
    ----------
    aur_packages : list[str]
        AUR package names to install (e.g. ``["mangowm-git"]``).
    username : str
        The non-root user account created earlier in the install flow.

    Returns
    -------
    tuple[bool, str]
        (success, error_message)
    """
    if not aur_packages:
        return True, ""

    # ── Step 1: Install build prerequisites ──
    rc, _, stderr = run(
        ["pacman", "-S", "--noconfirm", "--needed", "git", "base-devel", "go"],
        chroot=True,
        timeout=600,
    )
    if rc != 0:
        return False, f"Failed to install AUR build dependencies: {stderr}"

    build_dir = f"/home/{username}/.cache/aur-build"
    cache_dir = f"/home/{username}/.cache"

    # Create build directory and Go cache, all owned by the user
    rc, _, stderr = run(
        f"mkdir -p {build_dir} {cache_dir}/go-build "
        f"&& chown -R {username}:{username} {cache_dir}",
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to create AUR build directory: {stderr}"

    # Temporarily allow user to run pacman without password
    sudoers_tmp = "/etc/sudoers.d/aur-install-tmp"
    rc, _, stderr = run(
        f'echo "{username} ALL=(ALL) NOPASSWD: ALL" > {sudoers_tmp} && chmod 440 {sudoers_tmp}',
        chroot=True,
    )
    if rc != 0:
        log_error(f"Failed to set temp sudoers for AUR install: {stderr}")

    # ── Step 2: Build and install yay (AUR helper) ──
    yay_dir = f"{build_dir}/yay"
    rc, _, stderr = run(
        f"su - {username} -c 'git clone --depth 1 https://aur.archlinux.org/yay.git {yay_dir}'",
        chroot=True,
        timeout=120,
    )
    if rc != 0:
        run(f"rm -f {sudoers_tmp}", chroot=True)
        return False, f"Failed to clone yay: {stderr}"

    rc, _, stderr = run(
        f"su - {username} -c 'cd {yay_dir} && makepkg -si --noconfirm --needed'",
        chroot=True,
        timeout=600,
    )
    if rc != 0:
        run(f"rm -f {sudoers_tmp}", chroot=True)
        return False, f"Failed to build/install yay: {stderr}"

    log_info("yay AUR helper installed successfully")

    # ── Step 3: Install the actual AUR packages via yay ──
    errors = []
    for pkg in aur_packages:
        log_info(f"Installing AUR package via yay: {pkg}")

        rc, _, stderr = run(
            f"su - {username} -c 'yay -S --noconfirm --needed --answerdiff None --answerclean None {pkg}'",
            chroot=True,
            timeout=1800,
        )
        if rc != 0:
            errors.append(f"Failed to install {pkg}: {stderr}")
            continue

        log_info(f"AUR package {pkg} installed successfully")

    # ── Cleanup ──
    run(f"rm -f {sudoers_tmp}", chroot=True)
    run(f"rm -rf {build_dir}", chroot=True)

    if errors:
        return False, "; ".join(errors)

    return True, ""
