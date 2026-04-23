"""
artixinstall.installer.users — Root password setup and user account creation.

Handles setting the root password and creating user accounts with optional
sudo/wheel group membership.
"""

from pathlib import Path

from artixinstall.utils.shell import run, MOUNT_POINT
from artixinstall.utils.log import log_info, log_error
from artixinstall.utils.validate import is_valid_username, is_valid_password, sanitize_shell_arg
from artixinstall.tui.screen import Screen
from artixinstall.tui.prompts import password_input_confirmed, text_input, yes_no

"""

    
"""
_HYPRLAND_NVIDIA_CONFIG = [
"# This is an example Hyprland config file.",
"# Refer to the wiki for more information.",
"# https://wiki.hypr.land/Configuring/",
"",
"# Please note not all available settings / options are set here.",
"# For a full list, see the wiki",
"",
"# You can split this configuration into multiple files",
"# Create your files separately and then link them to this file like this:",
"# source = ~/.config/hypr/myColors.conf",
"",
"",
"################",
"### MONITORS ###",
"################",
"",
"# See https://wiki.hypr.land/Configuring/Monitors/",
"monitor=,preferred,auto,auto",
"",
"",
"###################",
"### MY PROGRAMS ###",
"###################",
"",
"# See https://wiki.hypr.land/Configuring/Keywords/",
"",
"# Set programs that you use",
"$terminal = kitty",
"$fileManager = dolphin",
"$menu = hyprlauncher",
"",
"",
"#################",
"### AUTOSTART ###",
"#################",
"",
"# Autostart necessary processes (like notifications daemons, status bars, etc.)",
"# Or execute your favorite apps at launch like this:",
"",
"# exec-once = $terminal",
"# exec-once = nm-applet &",
"# exec-once = waybar & hyprpaper & firefox",
"",
"",
"#############################",
"### ENVIRONMENT VARIABLES ###",
"#############################",
"",
"# See https://wiki.hypr.land/Configuring/Environment-variables/",
"",
"env = XCURSOR_SIZE,24",
"env = HYPRCURSOR_SIZE,24",
"env = LIBVA_DRIVER_NAME,nvidia",
"env = XDG_SESSION_TYPE,wayland",
"env = GBM_BACKEND,nvidia-drm",
"env = __GLX_VENDOR_LIBRARY_NAME,nvidia",
"env = WLR_NO_HARDWARE_CURSORS,1",
"",
"",
"###################",
"### PERMISSIONS ###",
"###################",
"",
"# See https://wiki.hypr.land/Configuring/Permissions/",
"# Please note permission changes here require a Hyprland restart and are not applied on-the-fly",
"# for security reasons",
"",
"# ecosystem {",
"#   enforce_permissions = 1",
"# }",
"",
"# permission = /usr/(bin|local/bin)/grim, screencopy, allow",
"# permission = /usr/(lib|libexec|lib64)/xdg-desktop-portal-hyprland, screencopy, allow",
"# permission = /usr/(bin|local/bin)/hyprpm, plugin, allow",
"",
"",
"#####################",
"### LOOK AND FEEL ###",
"#####################",
"",
"# Refer to https://wiki.hypr.land/Configuring/Variables/",
"",
"# https://wiki.hypr.land/Configuring/Variables/#general",
"general {",
    "gaps_in = 5",
    "gaps_out = 20",
"",
    "border_size = 2",
"",
    "# https://wiki.hypr.land/Configuring/Variables/#variable-types for info about colors",
    "col.active_border = rgba(33ccffee) rgba(00ff99ee) 45deg",
    "col.inactive_border = rgba(595959aa)",
"",
    "# Set to true enable resizing windows by clicking and dragging on borders and gaps",
    "resize_on_border = false",
"",
    "# Please see https://wiki.hypr.land/Configuring/Tearing/ before you turn this on",
    "allow_tearing = false",
"",
    "layout = dwindle",
"}",
"",
"# https://wiki.hypr.land/Configuring/Variables/#decoration",
"decoration {",
    "rounding = 10",
    "rounding_power = 2",
"",
    "# Change transparency of focused and unfocused windows",
    "active_opacity = 1.0",
    "inactive_opacity = 1.0",
"",
    "shadow {",
        "enabled = true",
        "range = 4",
        "render_power = 3",
        "color = rgba(1a1a1aee)",
    "}",
"",
    "# https://wiki.hypr.land/Configuring/Variables/#blur",
    "blur {",
        "enabled = true",
        "size = 3",
        "passes = 1",
"",
        "vibrancy = 0.1696",
    "}",
"}",
"",
"# https://wiki.hypr.land/Configuring/Variables/#animations",
"animations {",
    "enabled = yes, please :)",
"",
    "# Default curves, see https://wiki.hypr.land/Configuring/Animations/#curves",
    "#        NAME,           X0,   Y0,   X1,   Y1",
    "bezier = easeOutQuint,   0.23, 1,    0.32, 1",
    "bezier = easeInOutCubic, 0.65, 0.05, 0.36, 1",
    "bezier = linear,         0,    0,    1,    1",
    "bezier = almostLinear,   0.5,  0.5,  0.75, 1",
    "bezier = quick,          0.15, 0,    0.1,  1",
"",
    "# Default animations, see https://wiki.hypr.land/Configuring/Animations/",
    "#           NAME,          ONOFF, SPEED, CURVE,        [STYLE]",
    "animation = global,        1,     10,    default",
    "animation = border,        1,     5.39,  easeOutQuint",
    "animation = windows,       1,     4.79,  easeOutQuint",
    "animation = windowsIn,     1,     4.1,   easeOutQuint, popin 87%",
    "animation = windowsOut,    1,     1.49,  linear,       popin 87%",
    "animation = fadeIn,        1,     1.73,  almostLinear",
    "animation = fadeOut,       1,     1.46,  almostLinear",
    "animation = fade,          1,     3.03,  quick",
    "animation = layers,        1,     3.81,  easeOutQuint",
    "animation = layersIn,      1,     4,     easeOutQuint, fade",
    "animation = layersOut,     1,     1.5,   linear,       fade",
    "animation = fadeLayersIn,  1,     1.79,  almostLinear",
    "animation = fadeLayersOut, 1,     1.39,  almostLinear",
    "animation = workspaces,    1,     1.94,  almostLinear, fade",
    "animation = workspacesIn,  1,     1.21,  almostLinear, fade",
    "animation = workspacesOut, 1,     1.94,  almostLinear, fade",
    "animation = zoomFactor,    1,     7,     quick",
"}",
"",
"# Ref https://wiki.hypr.land/Configuring/Workspace-Rules/",
"# uncomment all if you wish to use that.",
"# workspace = w[tv1], gapsout:0, gapsin:0",
"# workspace = f[1], gapsout:0, gapsin:0",
"# windowrule {",
"#     name = no-gaps-wtv1",
"#     match:float = false",
"#     match:workspace = w[tv1]",
"#",
"#     border_size = 0",
"#     rounding = 0",
"# }",
"#",
"# windowrule {",
"#     name = no-gaps-f1",
"#     match:float = false",
"#     match:workspace = f[1]",
"#",
"#     border_size = 0",
"#     rounding = 0",
"# }",
"",
"# See https://wiki.hypr.land/Configuring/Dwindle-Layout/ for more",
"dwindle {",
    "pseudotile = true # Master switch for pseudotiling. Enabling is bound to mainMod + P in the keybinds section below",
    "preserve_split = true # You probably want this",
"}",
"",
"# See https://wiki.hypr.land/Configuring/Master-Layout/ for more",
"master {",
    "new_status = master",
"}",
"",
"# https://wiki.hypr.land/Configuring/Variables/#misc",
"misc {",
    "force_default_wallpaper = -1 # Set to 0 or 1 to disable the anime mascot wallpapers",
    "disable_hyprland_logo = false # If true disables the random hyprland logo / anime girl background. :(",
"}",
"",
"",
"#############",
"### INPUT ###",
"#############",
"",
"# https://wiki.hypr.land/Configuring/Variables/#input",
"input {",
    "kb_layout = us",
    "kb_variant =",
    "kb_model =",
    "kb_options =",
    "kb_rules =",
"",
    "follow_mouse = 1",
"",
    "sensitivity = 0 # -1.0 - 1.0, 0 means no modification.",
"",
    "touchpad {",
        "natural_scroll = false",
    "}",
"}",
"",
"# See https://wiki.hypr.land/Configuring/Gestures",
"gesture = 3, horizontal, workspace",
"",
"# Example per-device config",
"# See https://wiki.hypr.land/Configuring/Keywords/#per-device-input-configs for more",
"device {",
    "name = epic-mouse-v1",
    "sensitivity = -0.5",
"}",
"",
"",
"###################",
"### KEYBINDINGS ###",
"###################",
"",
"# See https://wiki.hypr.land/Configuring/Keywords/",
"$mainMod = SUPER ",
"",
"# Example binds, see https://wiki.hypr.land/Configuring/Binds/ for more",
"bind = $mainMod, Q, exec, $terminal",
"bind = $mainMod, C, killactive,",
"bind = $mainMod, M, exec, command -v hyprshutdown >/dev/null 2>&1 && hyprshutdown || hyprctl dispatch exit",
"bind = $mainMod, E, exec, $fileManager",
"bind = $mainMod, V, togglefloating,",
"bind = $mainMod, R, exec, $menu",
"bind = $mainMod, P, pseudo, # dwindle",
"bind = $mainMod, J, layoutmsg, togglesplit # dwindle",
"",
"# Move focus with mainMod + arrow keys",
"bind = $mainMod, left, movefocus, l",
"bind = $mainMod, right, movefocus, r",
"bind = $mainMod, up, movefocus, u",
"bind = $mainMod, down, movefocus, d",
"",
"# Switch workspaces with mainMod + [0-9]",
"bind = $mainMod, 1, workspace, 1",
"bind = $mainMod, 2, workspace, 2",
"bind = $mainMod, 3, workspace, 3",
"bind = $mainMod, 4, workspace, 4",
"bind = $mainMod, 5, workspace, 5",
"bind = $mainMod, 6, workspace, 6",
"bind = $mainMod, 7, workspace, 7",
"bind = $mainMod, 8, workspace, 8",
"bind = $mainMod, 9, workspace, 9",
"bind = $mainMod, 0, workspace, 10",
"",
"# Move active window to a workspace with mainMod + SHIFT + [0-9]",
"bind = $mainMod SHIFT, 1, movetoworkspace, 1",
"bind = $mainMod SHIFT, 2, movetoworkspace, 2",
"bind = $mainMod SHIFT, 3, movetoworkspace, 3",
"bind = $mainMod SHIFT, 4, movetoworkspace, 4",
"bind = $mainMod SHIFT, 5, movetoworkspace, 5",
"bind = $mainMod SHIFT, 6, movetoworkspace, 6",
"bind = $mainMod SHIFT, 7, movetoworkspace, 7",
"bind = $mainMod SHIFT, 8, movetoworkspace, 8",
"bind = $mainMod SHIFT, 9, movetoworkspace, 9",
"bind = $mainMod SHIFT, 0, movetoworkspace, 10",
"",
"# Example special workspace (scratchpad)",
"bind = $mainMod, S, togglespecialworkspace, magic",
"bind = $mainMod SHIFT, S, movetoworkspace, special:magic",
"",
"# Scroll through existing workspaces with mainMod + scroll",
"bind = $mainMod, mouse_down, workspace, e+1",
"bind = $mainMod, mouse_up, workspace, e-1",
"",
"# Move/resize windows with mainMod + LMB/RMB and dragging",
"bindm = $mainMod, mouse:272, movewindow",
"bindm = $mainMod, mouse:273, resizewindow",
"",
"# Laptop multimedia keys for volume and LCD brightness",
"bindel = ,XF86AudioRaiseVolume, exec, wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+",
"bindel = ,XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
"bindel = ,XF86AudioMute, exec, wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
"bindel = ,XF86AudioMicMute, exec, wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
"bindel = ,XF86MonBrightnessUp, exec, brightnessctl -e4 -n2 set 5%+",
"bindel = ,XF86MonBrightnessDown, exec, brightnessctl -e4 -n2 set 5%-",
"",
"# Requires playerctl",
"bindl = , XF86AudioNext, exec, playerctl next",
"bindl = , XF86AudioPause, exec, playerctl play-pause",
"bindl = , XF86AudioPlay, exec, playerctl play-pause",
"bindl = , XF86AudioPrev, exec, playerctl previous",
"",
"##############################",
"### WINDOWS AND WORKSPACES ###",
"##############################",
"",
"# See https://wiki.hypr.land/Configuring/Window-Rules/ for more",
"# See https://wiki.hypr.land/Configuring/Workspace-Rules/ for workspace rules",
"",
"# Example windowrules that are useful",
"",
"windowrule {",
    "# Ignore maximize requests from all apps. You'll probably like this.",
    "name = suppress-maximize-events",
    "match:class = .*",
"",
    "suppress_event = maximize",
"}",
"",
"windowrule {",
    "# Fix some dragging issues with XWayland",
    "name = fix-xwayland-drags",
    "match:class = ^$",
    "match:title = ^$",
    "match:xwayland = true",
    "match:float = true",
    "match:fullscreen = false",
    "match:pin = false",
"",
    "no_focus = true",
"}",
"",
"# Hyprland-run windowrule",
"windowrule {",
    "name = move-hyprland-run",
"",
    "match:class = hyprland-run",
"",
    "move = 20 monitor_h-120",
    "float = yes",
"}"
]

_HYPRLAND_PIPEWIRE_AUTOSTART = [
    "exec-once = pipewire",
    "exec-once = pipewire-pulse",
    "exec-once = wireplumber",
]


def configure_root_password(screen: Screen) -> str | None:
    """
    Prompt for the root password (twice for confirmation).

    Returns the password string, or None if cancelled.
    Note: The password is returned in memory only and never logged.
    """
    return password_input_confirmed(
        screen,
        prompt="Enter root password",
        confirm_prompt="Confirm root password",
    )


def configure_user(screen: Screen) -> dict | None:
    """
    Interactive user account configuration.

    Returns a dict with keys:
        username: str
        password: str
        sudo: bool

    Or None if cancelled.
    """
    # Ask for username
    username = text_input(
        screen,
        "Enter username (lowercase, alphanumeric/underscore):",
        validator=is_valid_username,
    )
    if username is None:
        return None

    # Ask for password
    password = password_input_confirmed(
        screen,
        prompt=f"Enter password for '{username}'",
        confirm_prompt=f"Confirm password for '{username}'",
    )
    if password is None:
        return None

    # Ask about sudo access
    sudo = yes_no(screen, f"Grant '{username}' sudo (wheel) access?", default=True)
    if sudo is None:
        return None

    return {
        "username": username,
        "password": password,
        "sudo": sudo,
    }


def apply_root_password(password: str) -> tuple[bool, str]:
    """
    Set the root password inside the chroot.

    Uses chpasswd via stdin to avoid the password appearing in process lists.
    """
    safe_pw = sanitize_shell_arg(password)

    rc, _, stderr = run(
        f'echo "root:{safe_pw}" | chpasswd',
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set root password: {stderr}"

    log_info("Root password set")
    return True, ""


def _write_hyprland_nvidia_config(username: str) -> tuple[bool, str]:
    """Ensure Hyprland has the basic NVIDIA environment variables configured."""
    home_dir = Path(MOUNT_POINT) / "home" / username
    hypr_dir = home_dir / ".config" / "hypr"
    hypr_conf = hypr_dir / "hyprland.conf"

    try:
        hypr_dir.mkdir(parents=True, exist_ok=True)
        if hypr_conf.exists():
            content = hypr_conf.read_text(encoding="utf-8")
        else:
            content = (
                "# Generated by artixinstall for Hyprland\n"
                "# Add your own bindings and monitors below.\n\n"
            )

        lines_to_add = [line for line in _HYPRLAND_NVIDIA_CONFIG if line not in content]
        if lines_to_add:
            if content and not content.endswith("\n"):
                content += "\n"
            if content.strip():
                content += "\n# NVIDIA compatibility\n"
            content += "\n".join(lines_to_add) + "\n"
            hypr_conf.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, f"Failed to write Hyprland NVIDIA config: {exc}"

    rc, _, stderr = run(
        f"chown -R {username}:{username} /home/{username}/.config",
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set Hyprland config ownership: {stderr}"

    return True, ""


def _write_hyprland_pipewire_config(username: str) -> tuple[bool, str]:
    """Ensure Hyprland starts the PipeWire user daemons on login."""
    home_dir = Path(MOUNT_POINT) / "home" / username
    hypr_dir = home_dir / ".config" / "hypr"
    hypr_conf = hypr_dir / "hyprland.conf"

    try:
        hypr_dir.mkdir(parents=True, exist_ok=True)
        if hypr_conf.exists():
            content = hypr_conf.read_text(encoding="utf-8")
        else:
            content = (
                "# Generated by artixinstall for Hyprland\n"
                "# Add your own bindings and monitors below.\n\n"
            )

        lines_to_add = [line for line in _HYPRLAND_PIPEWIRE_AUTOSTART if line not in content]
        if lines_to_add:
            if content and not content.endswith("\n"):
                content += "\n"
            if content.strip():
                content += "\n# PipeWire session startup\n"
            content += "\n".join(lines_to_add) + "\n"
            hypr_conf.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, f"Failed to write Hyprland PipeWire config: {exc}"

    rc, _, stderr = run(
        f"chown -R {username}:{username} /home/{username}/.config",
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set Hyprland config ownership: {stderr}"

    return True, ""


def apply_user(
    user_config: dict,
    desktop: str = "none",
    gpu_driver: str = "auto",
    audio: str = "pipewire",
) -> tuple[bool, str]:
    """
    Create a user account inside the chroot.

    Steps:
    1. Create user with useradd
    2. Set password with chpasswd
    3. If sudo, uncomment %wheel in /etc/sudoers
    """
    username = sanitize_shell_arg(user_config["username"])
    password = sanitize_shell_arg(user_config["password"])
    sudo = user_config["sudo"]

    # Create user with home directory and bash shell
    groups = "wheel" if sudo else "users"
    rc, _, stderr = run(
        f"useradd -m -G {groups} -s /bin/bash {username}",
        chroot=True,
    )
    if rc != 0:
        # User might already exist — try to continue
        if "already exists" not in stderr:
            return False, f"Failed to create user: {stderr}"
        log_info(f"User {username} already exists, continuing")

    # Set password
    rc, _, stderr = run(
        f'echo "{username}:{password}" | chpasswd',
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set user password: {stderr}"

    # Enable sudo for wheel group
    if sudo:
        rc, _, stderr = run(
            "sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers",
            chroot=True,
        )
        if rc != 0:
            # Try alternate format
            rc, _, stderr = run(
                "sed -i 's/^# %wheel ALL=(ALL) ALL/%wheel ALL=(ALL) ALL/' /etc/sudoers",
                chroot=True,
            )
            if rc != 0:
                log_error(f"Failed to enable sudo for wheel: {stderr}")
                # Non-fatal — continue

    run(
        f"mkdir -p /home/{username}/Desktop /home/{username}/Documents /home/{username}/Downloads "
        f"/home/{username}/Music /home/{username}/Pictures /home/{username}/Public "
        f"/home/{username}/Templates /home/{username}/Videos",
        chroot=True,
    )
    run(
        f"chown -R {username}:{username} /home/{username}",
        chroot=True,
    )

    if run("command -v xdg-user-dirs-update", chroot=True)[0] == 0:
        rc, _, stderr = run(
            f"su - {username} -c 'xdg-user-dirs-update'",
            chroot=True,
        )
        if rc != 0:
            log_error(f"Failed to initialize XDG user dirs: {stderr}")

    if desktop == "hyprland" and gpu_driver.startswith("nvidia"):
        ok, message = _write_hyprland_nvidia_config(username)
        if not ok:
            return False, message

    # PipeWire autostart — needed for WMs on Artix (no systemd --user).
    # Full DEs (GNOME, KDE, XFCE, etc.) handle PipeWire startup themselves.
    _WM_DESKTOPS = {
        "hyprland", "sway", "i3", "bspwm", "dwm", "qtile",
        "openbox", "awesome", "river", "mangowm", "niri",
    }
    if audio == "pipewire" and desktop in _WM_DESKTOPS:
        if desktop == "hyprland":
            ok, message = _write_hyprland_pipewire_config(username)
        else:
            ok, message = _write_pipewire_autostart(username, desktop)
        if not ok:
            return False, message

    log_info(f"User '{username}' created (sudo={sudo})")
    return True, ""


def _write_pipewire_autostart(username: str, desktop: str) -> tuple[bool, str]:
    """Create a PipeWire autostart script for non-systemd WM sessions.

    On Artix Linux there is no ``systemd --user`` to launch PipeWire
    automatically.  This function creates a small script that starts
    the PipeWire daemons and sources it from the user's login profile.
    """
    home_dir = Path(MOUNT_POINT) / "home" / username
    script_dir = home_dir / ".local" / "bin"
    script_path = script_dir / "pipewire-start.sh"
    bash_profile = home_dir / ".bash_profile"

    script_content = (
        "#!/bin/sh\n"
        "# Auto-generated by artixinstall — PipeWire session startup\n"
        "# Safe to remove if you manage PipeWire differently.\n"
        "\n"
        'if [ -z "$PIPEWIRE_STARTED" ]; then\n'
        '    export PIPEWIRE_STARTED=1\n'
        '    pipewire &\n'
        '    pipewire-pulse &\n'
        '    wireplumber &\n'
        "fi\n"
    )

    try:
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(0o755)

        # Source it from .bash_profile
        profile_content = ""
        if bash_profile.exists():
            profile_content = bash_profile.read_text(encoding="utf-8")

        source_line = '[ -x "$HOME/.local/bin/pipewire-start.sh" ] && . "$HOME/.local/bin/pipewire-start.sh"'
        if source_line not in profile_content:
            if profile_content and not profile_content.endswith("\n"):
                profile_content += "\n"
            profile_content += f"\n# PipeWire autostart (Artix — no systemd user service)\n{source_line}\n"
            bash_profile.write_text(profile_content, encoding="utf-8")

    except OSError as exc:
        return False, f"Failed to write PipeWire autostart: {exc}"

    rc, _, stderr = run(
        f"chown -R {username}:{username} /home/{username}/.local /home/{username}/.bash_profile",
        chroot=True,
    )
    if rc != 0:
        return False, f"Failed to set PipeWire autostart ownership: {stderr}"

    log_info(f"PipeWire autostart configured for {desktop}")
    return True, ""
