"""
artixinstall.tui.menu — Reusable curses menu component.

Provides a generic vertical list menu that supports:
- Arrow key navigation (up/down)
- Enter to select
- ESC / Q to go back
- Scrolling for long lists
- Optional value display on the right side of each item
"""

import curses
from artixinstall.tui.screen import (
    Screen, COLOR_NORMAL, COLOR_SELECTED, COLOR_VALUE_SET,
    COLOR_VALUE_UNSET, COLOR_SEPARATOR, COLOR_TITLE,
)


class MenuItem:
    """
    A single item in a menu.

    Attributes
    ----------
    label : str
        Display label shown on the left side.
    value : str
        Current value shown on the right side (empty string for action items).
    key : str
        Internal identifier used by the caller.
    is_separator : bool
        If True, this item is a non-selectable separator line.
    is_set : bool
        Whether the value has been configured (affects display color).
    """

    def __init__(self, label: str, key: str = "",
                 value: str = "", is_set: bool = False,
                 is_separator: bool = False) -> None:
        self.label = label
        self.key = key or label.lower().replace(" ", "_")
        self.value = value
        self.is_set = is_set
        self.is_separator = is_separator


def run_menu(screen: Screen, title: str, items: list[MenuItem],
             footer: str = "↑↓ Navigate  Enter Select  ESC Back",
             allow_escape: bool = True, default_key: str = "") -> MenuItem | None:
    """
    Display a vertical selection menu and return the chosen MenuItem.

    Parameters
    ----------
    screen : Screen
        The screen instance to draw on.
    title : str
        Title displayed above the menu.
    items : list[MenuItem]
        The menu items (including separators).
    footer : str
        Help text shown in the footer bar.
    allow_escape : bool
        If True, ESC/Q returns None. If False, ESC is ignored
        (used for the main menu to prevent accidental exit).
    default_key : str
        Optional: key of the item to start selection at. If not found,
        starts at the first selectable item.

    Returns
    -------
    MenuItem or None
        The selected item, or None if the user pressed ESC/Q.
    """
    # Find first selectable item
    selectable = [i for i, item in enumerate(items) if not item.is_separator]
    if not selectable:
        return None

    # Try to start at the specified key, otherwise start at first
    selected_idx = selectable[0]
    if default_key:
        for idx in selectable:
            if items[idx].key == default_key:
                selected_idx = idx
                break

    scroll_offset = 0

    while True:
        screen.refresh_size()
        screen.clear()
        screen.draw_header()
        screen.draw_footer(footer)

        # Title
        screen.draw_text(screen.content_y, 2, title, COLOR_TITLE, bold=True)

        # Calculate visible area
        menu_start_y = screen.content_y + 2
        visible_count = screen.content_height - 2  # Leave room for title

        # Adjust scroll to keep selection visible
        sel_pos = selected_idx - scroll_offset
        if sel_pos < 0:
            scroll_offset = selected_idx
        elif sel_pos >= visible_count:
            scroll_offset = selected_idx - visible_count + 1

        # Draw items
        for draw_idx in range(visible_count):
            item_idx = draw_idx + scroll_offset
            if item_idx >= len(items):
                break

            item = items[item_idx]
            y = menu_start_y + draw_idx

            if item.is_separator:
                screen.draw_separator(y)
                continue

            is_selected = (item_idx == selected_idx)

            # Build the display line
            label = item.label
            value = item.value

            if is_selected:
                # Highlight entire line
                line = f"  > {label}"
                if value:
                    # Pad to align values on the right
                    pad = screen.width - len(line) - len(value) - 6
                    if pad > 0:
                        line += " " * pad + f"[{value}]"
                    else:
                        line += f"  [{value}]"
                # Pad to full width for the highlight bar
                line = line.ljust(screen.width - 2)
                screen.draw_text(y, 1, line[:screen.width - 2], COLOR_SELECTED)
            else:
                # Normal item
                screen.draw_text(y, 4, label, COLOR_NORMAL)
                if value:
                    val_color = COLOR_VALUE_SET if item.is_set else COLOR_VALUE_UNSET
                    val_text = f"[{value}]"
                    val_x = screen.width - len(val_text) - 4
                    if val_x > len(label) + 6:
                        screen.draw_text(y, val_x, val_text, val_color)

        # Show scroll indicators if needed
        if scroll_offset > 0:
            screen.draw_text(menu_start_y - 1, screen.width - 4, " ▲ ", COLOR_SEPARATOR)
        if scroll_offset + visible_count < len(items):
            end_y = menu_start_y + visible_count
            if end_y < screen.footer_y:
                screen.draw_text(end_y, screen.width - 4, " ▼ ", COLOR_SEPARATOR)

        screen.stdscr.refresh()

        # Handle input
        key = screen.get_input()

        if key == curses.KEY_RESIZE:
            screen.refresh_size()
            continue

        if key in (curses.KEY_UP, ord('k')):
            # Move to previous selectable item
            current_pos = selectable.index(selected_idx)
            if current_pos > 0:
                selected_idx = selectable[current_pos - 1]

        elif key in (curses.KEY_DOWN, ord('j')):
            # Move to next selectable item
            current_pos = selectable.index(selected_idx)
            if current_pos < len(selectable) - 1:
                selected_idx = selectable[current_pos + 1]

        elif key == curses.KEY_HOME:
            selected_idx = selectable[0]

        elif key == curses.KEY_END:
            selected_idx = selectable[-1]

        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return items[selected_idx]

        elif key == 27:  # ESC
            if allow_escape:
                return None
            # On the main menu, ESC does nothing

        elif key in (ord('q'), ord('Q')):
            if allow_escape:
                return None


def run_selection_menu(screen: Screen, title: str,
                       options: list[str],
                       footer: str = "↑↓ Navigate  Enter Select  ESC Back"
                       ) -> str | None:
    """
    Simplified menu that takes a list of strings and returns the selected one.
    """
    items = [MenuItem(label=opt, key=opt) for opt in options]
    result = run_menu(screen, title, items, footer)
    return result.key if result else None
