"""
artixinstall.installer.disk — Disk detection, partitioning, formatting, and mounting.

Handles both automatic and manual partitioning workflows, with support for
EFI and BIOS systems, multiple filesystems, optional swap, and LUKS encryption.
"""

import os
import re
from artixinstall.utils.shell import run, run_live, command_exists, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.tui.screen import Screen
from artixinstall.tui.menu import run_menu, run_selection_menu, MenuItem
from artixinstall.tui.prompts import confirm_destructive, yes_no, password_input_confirmed


def is_efi() -> bool:
    """Check if the system booted in EFI mode."""
    return os.path.isdir("/sys/firmware/efi") or run("sudo dmesg | grep 'EFI v'")[0]==0 or run("dmesg | grep 'EFI v'")[0]==0


def detect_disks() -> list[dict]:
    """
    Detect available block devices.

    Returns a list of dicts with keys: name, size, type, path, model.
    """
    rc, stdout, stderr = run("lsblk -dno NAME,SIZE,TYPE,MODEL")
    if rc != 0:
        log_error(f"Failed to detect disks: {stderr}")
        return []

    disks = []
    for line in stdout.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[2] == "disk":
            model = parts[3].strip() if len(parts) > 3 else ""
            disks.append({
                "name": parts[0],
                "size": parts[1],
                "type": parts[2],
                "path": f"/dev/{parts[0]}",
                "model": model,
            })
    return disks


def detect_disk_info(disk_path: str) -> dict:
    """
    Get detailed information about a disk.

    Returns a dict with transport, rotational, removable.
    """
    name = os.path.basename(disk_path)
    info = {"transport": "unknown", "rotational": False, "removable": False}

    # Check if SSD or HDD
    rot_path = f"/sys/block/{name}/queue/rotational"
    if os.path.isfile(rot_path):
        try:
            with open(rot_path) as f:
                info["rotational"] = f.read().strip() == "1"
        except OSError:
            pass

    # Check if removable
    rem_path = f"/sys/block/{name}/removable"
    if os.path.isfile(rem_path):
        try:
            with open(rem_path) as f:
                info["removable"] = f.read().strip() == "1"
        except OSError:
            pass

    return info


def configure_disk(screen: Screen) -> dict | None:
    """
    Interactive disk configuration flow.

    Returns a config dict with keys:
        disk: str — device path (e.g. /dev/sda)
        layout: str — "auto" or "manual"
        swap: bool — whether swap partition is included
        filesystem: str — root filesystem
        efi: bool — whether system is EFI
        boot_part: str — boot partition path
        root_part: str — root partition path
        swap_part: str — swap partition path (or "")
        encrypt: bool — whether LUKS encryption is used
        encrypt_password: str — LUKS password (or "")

    Or None if the user cancelled.
    """
    # Step 1: Detect and select disk
    disks = detect_disks()
    if not disks:
        screen.show_error("No disks detected! Make sure you have a storage device connected.")
        return None

    items = []
    for d in disks:
        model_str = f" - {d['model']}" if d['model'] else ""
        info = detect_disk_info(d["path"])
        disk_type = "HDD" if info["rotational"] else "SSD"
        if info["removable"]:
            disk_type = "USB/Removable"

        items.append(MenuItem(
            label=f"{d['path']}{model_str}",
            key=d["path"],
            value=f"{d['size']} ({disk_type})",
            is_set=True,
        ))

    selected = run_menu(screen, "Select a disk", items,
                        footer="↑↓ Navigate  Enter Select  ESC Back")
    if selected is None:
        return None

    disk_path = selected.key

    # Step 2: Choose partitioning method
    method = run_selection_menu(screen, f"Partition method for {disk_path}", [
        "Automatic (wipe and partition entire disk)",
        "Manual (launch cfdisk)",
    ])
    if method is None:
        return None

    efi = is_efi()

    if method.startswith("Manual"):
        return _manual_partition(screen, disk_path, efi)
    else:
        return _automatic_partition(screen, disk_path, efi)


def _automatic_partition(screen: Screen, disk_path: str, efi: bool) -> dict | None:
    """Automatic partitioning: wipe disk, create partitions, format, mount."""
    # Ask about swap
    swap_choice = run_selection_menu(screen, "Swap configuration", [
        "With swap partition (4 GB)",
        "With swap partition (8 GB)",
        "Without swap (can add swapfile later)",
    ])
    if swap_choice is None:
        return None
    use_swap = not swap_choice.startswith("Without")
    swap_size_mb = 8192 if "8 GB" in swap_choice else 4096

    home_result = yes_no(screen, "Create a separate /home partition?", default=False)
    if home_result is None:
        return None
    separate_home = home_result
    root_size_mb = 0
    if separate_home:
        root_size = run_selection_menu(screen, "Root partition size (the rest goes to /home)", [
            "30 GB",
            "50 GB",
            "80 GB",
            "100 GB",
        ])
        if root_size is None:
            return None
        root_size_mb = int(root_size.split()[0]) * 1024

    # Ask about filesystem
    fs = run_selection_menu(screen, "Root filesystem", [
        "ext4 (recommended, mature, reliable)",
        "btrfs (snapshots, compression, modern)",
        "xfs (high performance, large files)",
        "f2fs (optimized for flash/SSD)",
    ])
    if fs is None:
        return None
    filesystem = fs.split()[0]

    # Ask about encryption
    encrypt = False
    encrypt_password = ""
    enc_result = yes_no(screen, "Enable LUKS disk encryption on root partition?", default=False)
    if enc_result is None:
        return None
    if enc_result:
        encrypt_password = password_input_confirmed(
            screen,
            prompt="Enter encryption passphrase",
            confirm_prompt="Confirm encryption passphrase",
        )
        if encrypt_password is None:
            return None
        if not encrypt_password:
            screen.show_error("Encryption passphrase cannot be empty.")
            return None
        encrypt = True

    # Safety confirmation
    enc_warning = " THIS WILL CREATE AN ENCRYPTED VOLUME." if encrypt else ""
    if not confirm_destructive(screen,
            f"This will permanently erase ALL data on {disk_path}.{enc_warning}\n"
            "This action cannot be undone."):
        return None

    # Determine partition naming convention (nvme vs sd)
    if "nvme" in disk_path or "mmcblk" in disk_path:
        part_prefix = f"{disk_path}p"
    else:
        part_prefix = disk_path

    boot_end = 513
    swap_end = boot_end + swap_size_mb if use_swap else boot_end

    config = {
        "disk": disk_path,
        "layout": "auto",
        "swap": use_swap,
        "home": separate_home,
        "swap_size_mb": swap_size_mb if use_swap else 0,
        "root_size_mb": root_size_mb,
        "filesystem": filesystem,
        "efi": efi,
        "boot_part": f"{part_prefix}1",
        "root_part": "",
        "swap_part": "",
        "home_part": "",
        "encrypt": encrypt,
        "encrypt_password": encrypt_password,
    }

    if use_swap:
        config["swap_part"] = f"{part_prefix}2"
        config["root_part"] = f"{part_prefix}3"
        if separate_home:
            config["home_part"] = f"{part_prefix}4"
    else:
        config["root_part"] = f"{part_prefix}2"
        if separate_home:
            config["home_part"] = f"{part_prefix}3"

    return config


def _manual_partition(screen: Screen, disk_path: str, efi: bool) -> dict | None:
    """
    Launch cfdisk for manual partitioning, then ask the user which
    partitions to use for boot, root, and swap.
    """
    screen.show_message(
        "Manual Partitioning",
        f"cfdisk will now launch for {disk_path}.\n"
        "Create your partitions, then write and quit.\n\n"
        "You will need at minimum:\n"
        "  - A boot partition (512MB+, EFI System type for UEFI)\n"
        "  - A root partition (remainder)\n"
        "  - Optionally a swap partition",
    )

    # Launch cfdisk — this takes over the terminal
    curses_was_active = True
    try:
        import curses as _curses
        _curses.endwin()
    except Exception:
        curses_was_active = False

    if not command_exists("cfdisk"):
        screen.show_error(
            "cfdisk is not available in this live environment.\n"
            "Install util-linux or use automatic partitioning."
        )
        return None

    run_live(f"cfdisk {disk_path}")

    # Restore curses
    if curses_was_active:
        screen.stdscr.refresh()

    # Now ask user to identify their partitions
    rc, stdout, _ = run(f"lsblk -lno NAME,SIZE,TYPE,FSTYPE {disk_path}")
    if rc != 0:
        screen.show_error("Failed to read partition table after cfdisk.")
        return None

    parts = []
    for line in stdout.strip().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == "part":
            fstype = fields[3] if len(fields) > 3 else ""
            parts.append({
                "name": fields[0],
                "size": fields[1],
                "path": f"/dev/{fields[0]}",
                "fstype": fstype,
            })

    if not parts:
        screen.show_error("No partitions found. Did you write the table in cfdisk?")
        return None

    part_labels = [f"{p['path']} ({p['size']}{', ' + p['fstype'] if p['fstype'] else ''})" for p in parts]

    # Select boot partition
    boot_sel = run_selection_menu(screen, "Select BOOT partition", part_labels)
    if boot_sel is None:
        return None
    boot_part = parts[part_labels.index(boot_sel)]["path"]

    # Select root partition
    remaining = [l for l in part_labels if l != boot_sel]
    if not remaining:
        screen.show_error("Not enough partitions for root.")
        return None
    root_sel = run_selection_menu(screen, "Select ROOT partition", remaining)
    if root_sel is None:
        return None
    root_part = parts[part_labels.index(root_sel)]["path"]

    # Ask about optional /home and swap
    swap_part = ""
    home_part = ""
    remaining2 = [l for l in remaining if l != root_sel]
    if remaining2:
        use_home = yes_no(screen, "Do you have a separate /home partition?", default=False)
        if use_home:
            home_sel = run_selection_menu(screen, "Select HOME partition", remaining2)
            if home_sel:
                home_part = parts[part_labels.index(home_sel)]["path"]
                remaining2 = [l for l in remaining2 if l != home_sel]

    if remaining2:
        use_swap = yes_no(screen, "Do you have a swap partition?", default=False)
        if use_swap:
            swap_sel = run_selection_menu(screen, "Select SWAP partition", remaining2)
            if swap_sel:
                swap_part = parts[part_labels.index(swap_sel)]["path"]

    # Choose filesystem
    fs = run_selection_menu(screen, "Root filesystem", [
        "ext4 (recommended)", "btrfs", "xfs", "f2fs",
    ])
    if fs is None:
        return None
    filesystem = fs.split()[0]

    # Ask about encryption
    encrypt = False
    encrypt_password = ""
    enc_result = yes_no(screen, "Enable LUKS encryption on root?", default=False)
    if enc_result:
        encrypt_password = password_input_confirmed(
            screen,
            prompt="Enter encryption passphrase",
            confirm_prompt="Confirm encryption passphrase",
        )
        if encrypt_password is None:
            encrypt = False
        elif encrypt_password:
            encrypt = True
        else:
            screen.show_error("Empty passphrase — skipping encryption.")

    return {
        "disk": disk_path,
        "layout": "manual",
        "swap": bool(swap_part),
        "home": bool(home_part),
        "swap_size_mb": 0,
        "root_size_mb": 0,
        "filesystem": filesystem,
        "efi": efi,
        "boot_part": boot_part,
        "root_part": root_part,
        "swap_part": swap_part,
        "home_part": home_part,
        "encrypt": encrypt,
        "encrypt_password": encrypt_password,
    }


# ── Execution functions (called during installation) ──


def _device_exists(path: str) -> bool:
    """Return True when a valid block-device path exists."""
    return isinstance(path, str) and path.startswith("/dev/") and os.path.exists(path)


def _wait_for_device(path: str, attempts: int = 10) -> bool:
    """Wait briefly for a kernel-created block device to appear."""
    for _ in range(attempts):
        if _device_exists(path):
            return True
        run(["sleep", "1"])
    return _device_exists(path)


def _get_disk_usage_details(disk: str) -> list[str]:
    """Return a list of reasons why a disk appears to be in use."""
    details: list[str] = []

    rc, stdout, _ = run(["lsblk", "-nrpo", "NAME,MOUNTPOINT", disk])
    if rc == 0:
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].strip():
                details.append(f"{parts[0]} mounted on {parts[1].strip()}")

    rc, stdout, _ = run(["swapon", "--show=NAME", "--noheadings"])
    if rc == 0:
        for swap_dev in stdout.splitlines():
            swap_dev = swap_dev.strip()
            if swap_dev and swap_dev.startswith(disk):
                details.append(f"{swap_dev} is active swap")

    return details


def _format_disk_in_use_error(disk: str, details: list[str], stderr: str = "") -> str:
    """Build a helpful error message for disks that are busy."""
    lines = [f"The selected disk is in use and cannot be repartitioned right now: {disk}"]
    if details:
        lines.append("")
        lines.append("Detected usage:")
        lines.extend(f"  - {item}" for item in details)
    lines.append("")
    lines.append("This often means you selected the live USB or a disk with mounted partitions.")
    lines.append("Choose a different target disk, or unmount/deactivate anything using this disk and retry.")
    if stderr.strip():
        lines.append("")
        lines.append(f"parted said: {stderr.strip()}")
    return "\n".join(lines)


def _list_mounts_under(path: str) -> list[str]:
    """Return mountpoints rooted under the given path, deepest first."""
    rc, stdout, _ = run(["findmnt", "-R", "-n", "-o", "TARGET", path])
    if rc != 0:
        return []

    mounts = []
    for line in stdout.splitlines():
        target = line.strip()
        if target and (target == path or target.startswith(f"{path}/")):
            mounts.append(target)

    return sorted(set(mounts), key=len, reverse=True)


def cleanup_install_environment(config: dict | None = None) -> tuple[bool, str]:
    """
    Clean up stale state from previous failed installation attempts.

    This is intentionally conservative: it only tears down `/mnt`, swap, and
    the well-known `cryptroot` mapping used by this installer.
    """
    errors: list[str] = []

    run(["swapoff", "-a"])

    mounts = _list_mounts_under(MOUNT_POINT)
    if mounts:
        run(["umount", "-R", MOUNT_POINT])
        mounts = _list_mounts_under(MOUNT_POINT)
        for mount in mounts:
            rc, _, err = run(["umount", mount])
            if rc != 0:
                errors.append(f"Failed to unmount {mount}: {err.strip()}")

    if os.path.exists("/dev/mapper/cryptroot"):
        rc, _, err = run(["cryptsetup", "close", "cryptroot"])
        if rc != 0:
            errors.append(f"Failed to close cryptroot: {err.strip()}")

    remaining_mounts = _list_mounts_under(MOUNT_POINT)
    if remaining_mounts:
        errors.append(
            "Some target mounts are still active: " + ", ".join(remaining_mounts)
        )

    if config and config.get("swap_part"):
        rc, stdout, _ = run(["swapon", "--show=NAME", "--noheadings"])
        if rc == 0:
            active_swap = {line.strip() for line in stdout.splitlines() if line.strip()}
            if config["swap_part"] in active_swap:
                errors.append(f"Swap is still active on {config['swap_part']}")

    if errors:
        return (
            False,
            "Failed to clean up a previous installation attempt cleanly:\n"
            + "\n".join(f"  - {item}" for item in errors),
        )

    log_info("Cleaned up stale mounts, swap, and cryptroot state")
    return True, ""


def partition_disk(config: dict) -> tuple[bool, str]:
    """
    Partition the disk according to the config.

    Only runs for automatic layout — manual is already done via cfdisk.
    """
    if config["layout"] == "manual":
        log_info("Skipping partitioning (manual layout)")
        return True, ""

    disk = config["disk"]
    efi = config["efi"]
    use_swap = config["swap"]
    use_home = config.get("home", False)
    swap_size_mb = config.get("swap_size_mb", 4096)
    root_size_mb = config.get("root_size_mb", 0)

    if not _device_exists(disk):
        return False, f"Target disk does not exist: {disk}"
    if not command_exists("parted"):
        return False, "Automatic partitioning requires `parted`, but it is not installed on this Artix live ISO."
    usage_details = _get_disk_usage_details(disk)
    if usage_details:
        return False, _format_disk_in_use_error(disk, usage_details)

    # Wipe and create partition label
    label = "gpt" if efi else "msdos"
    rc, _, err = run(["parted", "-s", disk, "mklabel", label])
    if rc != 0:
        if "being used" in err.lower() or "in use" in err.lower() or "busy" in err.lower():
            return False, _format_disk_in_use_error(disk, _get_disk_usage_details(disk), err)
        return False, f"Failed to create partition label: {err}"

    boot_end = 513  # MB

    if efi:
        # EFI boot partition: fat32 with ESP flag
        rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", "fat32", "1MiB", f"{boot_end}MiB"])
        if rc != 0:
            return False, f"Failed to create boot partition: {err}"
        rc, _, err = run(["parted", "-s", disk, "set", "1", "esp", "on"])
        if rc != 0:
            return False, f"Failed to set ESP flag: {err}"
    else:
        # BIOS boot partition: ext2 with boot flag
        rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", "ext2", "1MiB", f"{boot_end}MiB"])
        if rc != 0:
            return False, f"Failed to create boot partition: {err}"
        rc, _, err = run(["parted", "-s", disk, "set", "1", "boot", "on"])
        if rc != 0:
            return False, f"Failed to set boot flag: {err}"

    if use_swap:
        swap_end = boot_end + swap_size_mb
        rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", "linux-swap", f"{boot_end}MiB", f"{swap_end}MiB"])
        if rc != 0:
            return False, f"Failed to create swap partition: {err}"
        if use_home and root_size_mb > 0:
            root_end = swap_end + root_size_mb
            rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", f"{swap_end}MiB", f"{root_end}MiB"])
            if rc != 0:
                return False, f"Failed to create root partition: {err}"
            rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", f"{root_end}MiB", "100%"])
            if rc != 0:
                return False, f"Failed to create home partition: {err}"
        else:
            rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", f"{swap_end}MiB", "100%"])
            if rc != 0:
                return False, f"Failed to create root partition: {err}"
    else:
        if use_home and root_size_mb > 0:
            root_end = boot_end + root_size_mb
            rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", f"{boot_end}MiB", f"{root_end}MiB"])
            if rc != 0:
                return False, f"Failed to create root partition: {err}"
            rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", f"{root_end}MiB", "100%"])
            if rc != 0:
                return False, f"Failed to create home partition: {err}"
        else:
            rc, _, err = run(["parted", "-s", disk, "mkpart", "primary", f"{boot_end}MiB", "100%"])
            if rc != 0:
                return False, f"Failed to create root partition: {err}"

    # Wait for kernel to pick up new partitions
    if command_exists("partprobe"):
        run(["partprobe", disk])
    elif command_exists("udevadm"):
        run(["udevadm", "settle"])
    run(["sleep", "2"])

    for key in ("boot_part", "root_part", "swap_part", "home_part"):
        part = config.get(key)
        if part and not _wait_for_device(part):
            return False, f"Partition device did not appear after partitioning: {part}"

    log_info(f"Partitioned {disk} successfully")
    return True, ""


def format_partitions(config: dict) -> tuple[bool, str]:
    """Format all partitions according to the config, including LUKS if enabled."""
    boot_part = config["boot_part"]
    root_part = config["root_part"]
    swap_part = config.get("swap_part", "")
    home_part = config.get("home_part", "")
    filesystem = config["filesystem"]
    efi = config["efi"]
    encrypt = config.get("encrypt", False)
    encrypt_password = config.get("encrypt_password", "")

    if not _device_exists(boot_part):
        return False, f"Boot partition does not exist: {boot_part}"
    if not _device_exists(root_part):
        return False, f"Root partition does not exist: {root_part}"
    if swap_part and not _device_exists(swap_part):
        return False, f"Swap partition does not exist: {swap_part}"
    if home_part and not _device_exists(home_part):
        return False, f"Home partition does not exist: {home_part}"

    # Format boot partition
    if efi:
        if not command_exists("mkfs.fat"):
            return False, "EFI installs require `mkfs.fat`, but it is not installed on this Artix live ISO."
        rc, _, err = run(["mkfs.fat", "-F", "32", boot_part])
    else:
        if not command_exists("mkfs.ext2"):
            return False, "BIOS installs require `mkfs.ext2`, but it is not installed on this Artix live ISO."
        rc, _, err = run(["mkfs.ext2", "-F", boot_part])
    if rc != 0:
        return False, f"Failed to format boot partition: {err}"

    # Handle root partition (possibly encrypting first)
    actual_root = root_part
    if encrypt and encrypt_password:
        if not command_exists("cryptsetup"):
            return False, "Encryption requires `cryptsetup`, but it is not installed on this Artix live ISO."
        # Set up LUKS
        rc, _, err = run(
            ["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", root_part, "--key-file", "-"],
            input_text=encrypt_password,
        )
        if rc != 0:
            return False, f"Failed to create LUKS volume: {err}"

        rc, _, err = run(
            ["cryptsetup", "open", root_part, "cryptroot", "--key-file", "-"],
            input_text=encrypt_password,
        )
        if rc != 0:
            return False, f"Failed to open LUKS volume: {err}"

        actual_root = "/dev/mapper/cryptroot"
        config["_actual_root"] = actual_root

        log_info("LUKS volume created and opened")

    # Format root partition
    fs_cmd = {
        "ext4": ["mkfs.ext4", "-F", actual_root],
        "btrfs": ["mkfs.btrfs", "-f", actual_root],
        "xfs": ["mkfs.xfs", "-f", actual_root],
        "f2fs": ["mkfs.f2fs", "-f", actual_root],
    }
    selected_cmd = fs_cmd.get(filesystem, ["mkfs.ext4", "-F", actual_root])
    if not command_exists(selected_cmd[0]):
        return False, f"Required filesystem tool is missing from the live ISO: {selected_cmd[0]}"
    rc, _, err = run(selected_cmd)
    if rc != 0:
        return False, f"Failed to format root partition: {err}"

    if home_part:
        home_cmd = fs_cmd.get(filesystem, ["mkfs.ext4", "-F", home_part]).copy()
        home_cmd[-1] = home_part
        rc, _, err = run(home_cmd)
        if rc != 0:
            return False, f"Failed to format home partition: {err}"

    # Format swap if applicable
    if swap_part:
        if not command_exists("mkswap"):
            return False, "Swap setup requires `mkswap`, but it is not installed on this Artix live ISO."
        rc, _, err = run(["mkswap", swap_part])
        if rc != 0:
            return False, f"Failed to format swap: {err}"

    log_info("Formatted all partitions")
    return True, ""


def mount_partitions(config: dict) -> tuple[bool, str]:
    """Mount all partitions to the target mount point."""
    encrypt = config.get("encrypt", False)

    # Use decrypted device if encrypting
    if encrypt:
        root_dev = config.get("_actual_root", "/dev/mapper/cryptroot")
    else:
        root_dev = config["root_part"]

    boot_part = config["boot_part"]
    swap_part = config.get("swap_part", "")
    home_part = config.get("home_part", "")

    if not _device_exists(root_dev):
        return False, f"Root device is not available: {root_dev}"
    if not _device_exists(boot_part):
        return False, f"Boot partition is not available: {boot_part}"
    if swap_part and not _device_exists(swap_part):
        return False, f"Swap partition is not available: {swap_part}"
    if home_part and not _device_exists(home_part):
        return False, f"Home partition is not available: {home_part}"

    os.makedirs(MOUNT_POINT, exist_ok=True)

    # Mount root
    rc, _, err = run(["mount", root_dev, MOUNT_POINT])
    if rc != 0:
        return False, f"Failed to mount root: {err}"

    # Create and mount boot
    try:
        os.makedirs(f"{MOUNT_POINT}/boot", exist_ok=True)
    except OSError as e:
        return False, f"Failed to create /boot: {e}"

    rc, _, err = run(["mount", boot_part, f"{MOUNT_POINT}/boot"])
    if rc != 0:
        return False, f"Failed to mount boot: {err}"

    if home_part:
        try:
            os.makedirs(f"{MOUNT_POINT}/home", exist_ok=True)
        except OSError as e:
            return False, f"Failed to create /home: {e}"

        rc, _, err = run(["mount", home_part, f"{MOUNT_POINT}/home"])
        if rc != 0:
            return False, f"Failed to mount home: {err}"

    # Enable swap
    if swap_part:
        rc, _, err = run(["swapon", swap_part])
        if rc != 0:
            return False, f"Failed to enable swap: {err}"

    log_info("Mounted all partitions")
    return True, ""


def unmount_all() -> tuple[bool, str]:
    """Unmount all target partitions and close LUKS volumes."""
    run("swapoff -a")
    run(f"umount -R {MOUNT_POINT}")
    # Close LUKS if open
    run("cryptsetup close cryptroot 2>/dev/null")
    return True, ""


def setup_luks_hooks(config: dict) -> tuple[bool, str]:
    """
    If encryption is enabled, add the 'encrypt' hook to mkinitcpio
    and regenerate the initramfs inside the chroot.
    """
    if not config.get("encrypt", False):
        return True, ""

    mkinitcpio_path = os.path.join(MOUNT_POINT, "etc", "mkinitcpio.conf")

    try:
        with open(mkinitcpio_path, "r", encoding="utf-8") as f:
            content = f.read()

        hooks_match = re.search(r"^HOOKS=\(([^)]*)\)", content, re.MULTILINE)
        if hooks_match:
            hooks = hooks_match.group(1).split()
            if "encrypt" not in hooks:
                if "filesystems" in hooks:
                    hooks.insert(hooks.index("filesystems"), "encrypt")
                else:
                    hooks.append("encrypt")

            if "keyboard" in hooks and hooks.index("keyboard") > hooks.index("encrypt"):
                hooks.remove("keyboard")
                hooks.insert(hooks.index("encrypt"), "keyboard")
            if "keymap" in hooks and hooks.index("keymap") > hooks.index("encrypt"):
                hooks.remove("keymap")
                insert_at = hooks.index("encrypt")
                if "keyboard" in hooks:
                    insert_at = max(insert_at, hooks.index("keyboard") + 1)
                hooks.insert(insert_at, "keymap")

            new_hooks = f"HOOKS=({' '.join(hooks)})"
            content = content[:hooks_match.start()] + new_hooks + content[hooks_match.end():]
        else:
            content += "\nHOOKS=(base udev autodetect modconf block keyboard keymap encrypt filesystems fsck)\n"

        if "encrypt" not in content:
            return False, "Failed to add the mkinitcpio encrypt hook for the encrypted root."

        with open(mkinitcpio_path, "w", encoding="utf-8") as f:
            f.write(content)

    except OSError as e:
        log_error(f"Failed to update mkinitcpio.conf: {e}")
        return False, f"Failed to update mkinitcpio.conf: {e}"

    # Regenerate initramfs
    rc, _, stderr = run("mkinitcpio -P", chroot=True)
    if rc != 0:
        return False, f"Failed to regenerate initramfs: {stderr}"

    log_info("LUKS hooks configured and initramfs regenerated")
    return True, ""
