"""
artixinstall.installer.bootloader — GRUB and systemd-boot (via elogind) setup.

Handles detecting firmware type (EFI vs BIOS), installing and configuring
the selected bootloader inside the chroot, including LUKS encryption support.
"""

import os
import re

from artixinstall.utils.shell import run, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_selection_menu
from artixinstall.installer.disk import is_efi

# Bootloader options
BOOTLOADERS = {
    "grub": {
        "label": "GRUB (recommended)",
        "packages_efi": ["grub", "efibootmgr", "os-prober"],
        "packages_bios": ["grub", "os-prober"],
    },
    "systemd-boot": {
        "label": "systemd-boot (via elogind, EFI only)",
        "packages_efi": ["efibootmgr"],
        "packages_bios": [],  # systemd-boot doesn't support BIOS
    },
}


def configure_bootloader(screen: Screen) -> str | None:
    """
    Interactive bootloader selection.

    Returns the bootloader key ("grub" or "systemd-boot"), or None if cancelled.
    """
    efi = is_efi()

    if efi:
        options = [info["label"] for info in BOOTLOADERS.values()]
        keys = list(BOOTLOADERS.keys())
    else:
        # BIOS only supports GRUB
        options = [BOOTLOADERS["grub"]["label"]]
        keys = ["grub"]

    selected = run_selection_menu(screen, "Select bootloader", options)
    if selected is None:
        return None

    idx = options.index(selected)
    return keys[idx]


def configure_grub_custom_params(screen: Screen) -> str:
    """
    Prompt user for custom GRUB install parameters.

    Returns custom parameters string, or empty string if user declines/cancels.
    """
    from artixinstall.tui.prompts import yes_no, text_input

    if not yes_no(screen,
            "Set custom GRUB install parameters?\n"
            "Only choose yes if you know what you're doing.",
            default=False):
        return ""

    params = text_input(screen,
        "Enter custom GRUB install parameters:\n"
        "(e.g., --target=x86_64-efi-signed)",
        default="")
    return params.strip() if params else ""


def get_bootloader_packages(bootloader: str, efi: bool) -> list[str]:
    """Get the packages needed for the selected bootloader."""
    info = BOOTLOADERS.get(bootloader, {})
    if efi:
        return list(info.get("packages_efi", []))
    return list(info.get("packages_bios", []))


def apply_bootloader(bootloader: str, disk_config: dict,
                     kernel: str = "linux", grub_params: str = "") -> tuple[bool, str]:
    """
    Install and configure the selected bootloader inside the chroot.

    Parameters
    ----------
    bootloader : str
        "grub" or "systemd-boot"
    disk_config : dict
        The disk configuration dict from disk.configure_disk()
    kernel : str
        The kernel package name (e.g. "linux", "linux-lts")
    grub_params : str
        Custom GRUB install parameters (only used for GRUB)

    Returns
    -------
    tuple[bool, str]
        (success, error_message)
    """
    efi = disk_config.get("efi", is_efi())
    disk = disk_config.get("disk", "")
    encrypt = disk_config.get("encrypt", False)

    if bootloader == "grub":
        return _install_grub(efi, disk, disk_config, kernel, grub_params)
    elif bootloader == "systemd-boot":
        if not efi:
            return False, "systemd-boot requires UEFI firmware"
        return _install_systemd_boot(disk_config, kernel)
    else:
        return False, f"Unknown bootloader: {bootloader}"


def _install_grub(efi: bool, disk: str, disk_config: dict,
                  kernel: str, grub_params: str = "") -> tuple[bool, str]:
    """Install and configure GRUB, with LUKS and custom parameters support."""
    encrypt = disk_config.get("encrypt", False)

    # If encrypted, configure GRUB for LUKS
    if encrypt:
        root_part = disk_config.get("root_part", "")
        rc, uuid_out, _ = run(f"blkid -s UUID -o value {root_part}")
        root_uuid = uuid_out.strip() if rc == 0 else ""

        if root_uuid:
            # Set GRUB_CMDLINE_LINUX for encrypted root
            grub_default = os.path.join(MOUNT_POINT, "etc", "default", "grub")
            try:
                with open(grub_default, "r") as f:
                    content = f.read()

                # Add cryptdevice parameter regardless of the existing defaults.
                crypto_args = f"cryptdevice=UUID={root_uuid}:cryptroot root=/dev/mapper/cryptroot"
                cmdline_match = re.search(r'^GRUB_CMDLINE_LINUX="([^"]*)"', content, re.MULTILINE)
                if cmdline_match:
                    existing_args = cmdline_match.group(1).strip()
                    merged_args = f"{crypto_args} {existing_args}".strip()
                    merged_args = " ".join(dict.fromkeys(merged_args.split()))
                    crypto_line = f'GRUB_CMDLINE_LINUX="{merged_args}"'
                    content = (
                        content[:cmdline_match.start()]
                        + crypto_line
                        + content[cmdline_match.end():]
                    )
                else:
                    content += f'\nGRUB_CMDLINE_LINUX="{crypto_args}"\n'

                # Enable GRUB_ENABLE_CRYPTODISK
                if "GRUB_ENABLE_CRYPTODISK" not in content:
                    content += "\nGRUB_ENABLE_CRYPTODISK=y\n"
                else:
                    content = content.replace(
                        "#GRUB_ENABLE_CRYPTODISK=y",
                        "GRUB_ENABLE_CRYPTODISK=y",
                    )

                with open(grub_default, "w") as f:
                    f.write(content)

                log_info("GRUB configured for LUKS encryption")

            except OSError as e:
                log_error(f"Failed to configure GRUB for encryption: {e}")

    if efi:
        # UEFI GRUB installation
        grub_cmd = "grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=artix"
        if grub_params:
            grub_cmd = f"grub-install {grub_params} --target=x86_64-efi --efi-directory=/boot --bootloader-id=artix"
        rc, _, stderr = run(grub_cmd, chroot=True)
        if rc != 0:
            return False, f"grub-install (EFI) failed: {stderr}"
    else:
        # BIOS GRUB installation
        if not disk:
            return False, "Disk path required for BIOS GRUB installation"
        grub_cmd = f"grub-install --target=i386-pc {disk}"
        if grub_params:
            grub_cmd = f"grub-install {grub_params} --target=i386-pc {disk}"
        rc, _, stderr = run(grub_cmd, chroot=True)
        if rc != 0:
            return False, f"grub-install (BIOS) failed: {stderr}"

    # Generate GRUB config
    rc, _, stderr = run(
        "grub-mkconfig -o /boot/grub/grub.cfg",
        chroot=True,
    )
    if rc != 0:
        return False, f"grub-mkconfig failed: {stderr}"

    log_info(f"GRUB installed ({'EFI' if efi else 'BIOS'})")
    return True, ""


def _install_systemd_boot(disk_config: dict, kernel: str) -> tuple[bool, str]:
    """Install and configure systemd-boot (bootctl), with LUKS support."""
    encrypt = disk_config.get("encrypt", False)

    # Install bootctl
    rc, _, stderr = run(
        "bootctl --path=/boot install",
        chroot=True,
    )
    if rc != 0:
        return False, f"bootctl install failed: {stderr}"

    # Get root partition UUID
    if encrypt:
        # For encrypted setups, we need the LUKS partition UUID and
        # the decrypted device UUID
        luks_part = disk_config.get("root_part", "")
        rc, luks_uuid, _ = run(f"blkid -s UUID -o value {luks_part}")
        if rc != 0 or not luks_uuid.strip():
            return False, f"Failed to get LUKS partition UUID"

        actual_root = disk_config.get("_actual_root", "/dev/mapper/cryptroot")
        rc, root_uuid, _ = run(f"blkid -s UUID -o value {actual_root}")
        if rc != 0 or not root_uuid.strip():
            return False, f"Failed to get decrypted root UUID"

        root_uuid = root_uuid.strip()
        luks_uuid = luks_uuid.strip()
        options_line = f"options cryptdevice=UUID={luks_uuid}:cryptroot root=/dev/mapper/cryptroot rw"

    else:
        root_part = disk_config.get("root_part", "")
        rc, uuid_out, stderr = run(f"blkid -s UUID -o value {root_part}")
        if rc != 0 or not uuid_out.strip():
            return False, f"Failed to get root UUID: {stderr}"

        root_uuid = uuid_out.strip()
        root_fs = disk_config.get("filesystem", "ext4")
        options_line = f"options root=UUID={root_uuid} rw rootfstype={root_fs}"

    # Write loader.conf
    loader_conf = os.path.join(MOUNT_POINT, "boot", "loader", "loader.conf")
    os.makedirs(os.path.dirname(loader_conf), exist_ok=True)
    try:
        with open(loader_conf, "w") as f:
            f.write("default artix.conf\n")
            f.write("timeout 5\n")
            f.write("console-mode max\n")
            f.write("editor no\n")
    except OSError as e:
        return False, f"Failed to write loader.conf: {e}"

    # Determine kernel file names based on kernel choice
    if kernel == "linux":
        vmlinuz = "/vmlinuz-linux"
        initrd = "/initramfs-linux.img"
        fallback_initrd = "/initramfs-linux-fallback.img"
    else:
        vmlinuz = f"/vmlinuz-{kernel}"
        initrd = f"/initramfs-{kernel}.img"
        fallback_initrd = f"/initramfs-{kernel}-fallback.img"

    # Write boot entry
    entries_dir = os.path.join(MOUNT_POINT, "boot", "loader", "entries")
    os.makedirs(entries_dir, exist_ok=True)

    entry_conf = os.path.join(entries_dir, "artix.conf")
    try:
        with open(entry_conf, "w") as f:
            f.write("title   Artix Linux\n")
            f.write(f"linux   {vmlinuz}\n")

            # Add microcode if present
            for ucode in ["intel-ucode.img", "amd-ucode.img"]:
                ucode_path = os.path.join(MOUNT_POINT, "boot", ucode)
                if os.path.isfile(ucode_path):
                    f.write(f"initrd  /{ucode}\n")

            f.write(f"initrd  {initrd}\n")
            f.write(f"{options_line}\n")
    except OSError as e:
        return False, f"Failed to write boot entry: {e}"

    # Write fallback entry
    fallback_conf = os.path.join(entries_dir, "artix-fallback.conf")
    try:
        with open(fallback_conf, "w") as f:
            f.write("title   Artix Linux (fallback)\n")
            f.write(f"linux   {vmlinuz}\n")

            for ucode in ["intel-ucode.img", "amd-ucode.img"]:
                ucode_path = os.path.join(MOUNT_POINT, "boot", ucode)
                if os.path.isfile(ucode_path):
                    f.write(f"initrd  /{ucode}\n")

            f.write(f"initrd  {fallback_initrd}\n")
            f.write(f"{options_line}\n")
    except OSError as e:
        return False, f"Failed to write fallback boot entry: {e}"

    log_info("systemd-boot installed and configured")
    return True, ""
