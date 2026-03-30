"""
artixinstall.installer.prereqs - Live ISO prerequisite checks.
"""

from artixinstall.utils.shell import command_exists, run
from artixinstall.utils.log import log_info


FILESYSTEM_COMMANDS = {
    "ext4": ["mkfs.ext4"],
    "btrfs": ["mkfs.btrfs"],
    "xfs": ["mkfs.xfs"],
    "f2fs": ["mkfs.f2fs"],
}

BASE_LIVE_PACKAGES = [
    "artools-base",
    "pacman-contrib",
    "util-linux",
    "dosfstools",
    "e2fsprogs",
]

OPTIONAL_LIVE_PACKAGES = {
    "parted": "parted",
    "cryptsetup": "cryptsetup",
    "btrfs": "btrfs-progs",
    "xfs": "xfsprogs",
    "f2fs": "f2fs-tools",
}


def get_live_packages(disk_config: dict | None) -> list[str]:
    """Return the live-environment packages needed for the current install."""
    packages = list(BASE_LIVE_PACKAGES)

    if not disk_config:
        return packages

    layout = disk_config.get("layout")
    filesystem = disk_config.get("filesystem", "ext4")

    if layout == "auto":
        packages.append(OPTIONAL_LIVE_PACKAGES["parted"])

    if disk_config.get("encrypt"):
        packages.append(OPTIONAL_LIVE_PACKAGES["cryptsetup"])

    fs_pkg = OPTIONAL_LIVE_PACKAGES.get(filesystem)
    if fs_pkg:
        packages.append(fs_pkg)

    # Deduplicate while preserving order.
    return list(dict.fromkeys(packages))


def install_live_prerequisites(disk_config: dict | None) -> tuple[bool, str]:
    """
    Install the packages needed by the installer into the live environment.

    This keeps lean Artix ISOs usable by preparing required tooling before any
    partitioning or formatting starts.
    """
    if not command_exists("pacman"):
        return False, "The live environment does not provide `pacman`, so prerequisites cannot be installed automatically."

    packages = get_live_packages(disk_config)
    log_info(f"Installing live prerequisites: {' '.join(packages)}")

    rc, _, stderr = run(
        ["pacman", "-Sy", "--noconfirm", "--needed", *packages],
        timeout=1800,
    )
    if rc != 0:
        return False, f"Failed to install live-environment packages: {stderr}"

    return True, ""


def check_live_environment(disk_config: dict | None) -> tuple[bool, str]:
    """
    Validate the commands required by the selected installation workflow.

    Official Artix live media ships `artools-base`, which provides `basestrap`,
    `fstabgen`, and `artix-chroot`, plus the usual `util-linux` tools such as
    `lsblk`, `mount`, `blkid`, and `findmnt`. Filesystem-specific tools vary
    more between ISO flavors, so we verify them explicitly.
    """
    required = {
        "lsblk": "disk detection",
        "mount": "mounting target filesystems",
        "swapon": "activating swap",
        "blkid": "UUID detection",
        "findmnt": "fstab generation fallback",
        "basestrap": "installing the base system",
        "artix-chroot": "running commands inside the target system",
    }

    if not command_exists("fstabgen") and not command_exists("genfstab"):
        required["fstabgen"] = "generating /etc/fstab (or install a provider for genfstab)"

    if disk_config:
        required["mkfs.fat"] = "formatting the boot partition"

        filesystem = disk_config.get("filesystem", "ext4")
        for cmd in FILESYSTEM_COMMANDS.get(filesystem, ["mkfs.ext4"]):
            required[cmd] = f"formatting the root filesystem as {filesystem}"

        if disk_config.get("layout") == "auto":
            required["parted"] = "automatic partitioning"
            if not command_exists("partprobe") and not command_exists("udevadm"):
                required["partprobe"] = "refreshing the partition table after partitioning"

        if disk_config.get("layout") == "manual":
            required["cfdisk"] = "manual partitioning"

        if disk_config.get("swap"):
            required["mkswap"] = "formatting swap"

        if disk_config.get("encrypt"):
            required["cryptsetup"] = "LUKS encryption"

    missing = [f"{cmd} ({reason})" for cmd, reason in required.items() if not command_exists(cmd)]
    if missing:
        return (
            False,
            "Missing required tools in the live environment:\n"
            + "\n".join(f"  - {item}" for item in missing)
            + "\n\nInstall the missing packages, then retry. Typical Artix live-ISO packages "
              "for these tools are: artools-base util-linux dosfstools e2fsprogs "
              "btrfs-progs xfsprogs f2fs-tools cryptsetup parted.",
        )

    return True, ""
