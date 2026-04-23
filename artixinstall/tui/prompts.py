"""
artixinstall.tui.prompts — Text input, password input, yes/no, and
multi-select prompts built on curses.
"""

import curses
from artixinstall.tui.screen import (
    Screen, COLOR_NORMAL, COLOR_HEADER, COLOR_SELECTED,
    COLOR_VALUE_SET, COLOR_VALUE_UNSET, COLOR_ERROR, COLOR_TITLE,
)


def text_input(screen: Screen, prompt: str,
               default: str = "",
               validator=None,
               mask_char: str | None = None) -> str | None:
    """
    Show a text input prompt and return the entered string.

    Parameters
    ----------
    screen : Screen
        The screen to draw on.
    prompt : str
        The prompt text shown above the input field.
    default : str
        Pre-filled default value.
    validator : callable or None
        A function(str) -> (bool, str) that validates the input.
        Returns (True, "") on success, (False, reason) on failure.
    mask_char : str or None
        If set (e.g. '*'), each character is displayed as this char
        instead of the actual character. Used for password entry.

    Returns
    -------
    str or None
        The entered text, or None if the user pressed ESC.
    """
    curses.curs_set(1)  # Show cursor
    buffer = list(default)
    cursor_pos = len(buffer)
    error_msg = ""

    try:
        while True:
            screen.refresh_size()
            screen.clear()
            screen.draw_header()
            screen.draw_footer("Enter to confirm  ESC to cancel")

            y = screen.content_y + 2

            # Prompt (may be multi-line)
            prompt_lines = prompt.split("\n")
            for pl in prompt_lines:
                screen.draw_text(y, 2, pl, COLOR_TITLE, bold=True)
                y += 1
            y += 1  # blank line after prompt

            # Input field with horizontal scrolling
            full_text = (mask_char * len(buffer)) if mask_char else "".join(buffer)
            field_prefix = "> "
            field_start_x = 2 + len(field_prefix)
            visible_width = max(1, screen.width - field_start_x - 2)

            # Compute scroll offset so cursor is always visible
            scroll_offset = 0
            if cursor_pos > visible_width - 1:
                scroll_offset = cursor_pos - visible_width + 1

            visible_text = full_text[scroll_offset:scroll_offset + visible_width]

            screen.draw_text(y, 2, field_prefix, COLOR_NORMAL)
            # Clear the field area first, then draw visible portion
            screen.draw_text(y, field_start_x, " " * visible_width, COLOR_NORMAL)
            screen.draw_text(y, field_start_x, visible_text, COLOR_VALUE_SET)

            # Position cursor relative to scroll offset
            cursor_x = field_start_x + (cursor_pos - scroll_offset)
            try:
                screen.stdscr.move(y, min(cursor_x, screen.width - 2))
            except curses.error:
                pass

            # Error message
            if error_msg:
                screen.draw_text(y + 2, 4, error_msg, COLOR_ERROR)

            screen.stdscr.refresh()

            key = screen.get_input()

            if key == 27:  # ESC
                return None

            elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
                value = "".join(buffer)
                if validator:
                    valid, reason = validator(value)
                    if not valid:
                        error_msg = reason
                        continue
                return value

            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if cursor_pos > 0:
                    buffer.pop(cursor_pos - 1)
                    cursor_pos -= 1
                    error_msg = ""

            elif key == curses.KEY_DC:  # Delete key
                if cursor_pos < len(buffer):
                    buffer.pop(cursor_pos)
                    error_msg = ""

            elif key == curses.KEY_LEFT:
                if cursor_pos > 0:
                    cursor_pos -= 1

            elif key == curses.KEY_RIGHT:
                if cursor_pos < len(buffer):
                    cursor_pos += 1

            elif key == curses.KEY_HOME:
                cursor_pos = 0

            elif key == curses.KEY_END:
                cursor_pos = len(buffer)

            elif key == curses.KEY_RESIZE:
                screen.refresh_size()
                continue

            elif 32 <= key <= 126:  # Printable ASCII
                buffer.insert(cursor_pos, chr(key))
                cursor_pos += 1
                error_msg = ""

    finally:
        curses.curs_set(0)


def password_input(screen: Screen, prompt: str) -> str | None:
    """
    Prompt for a password (displayed as asterisks).
    """
    return text_input(screen, prompt, mask_char="*")


def password_input_confirmed(screen: Screen, prompt: str = "Enter password",
                              confirm_prompt: str = "Confirm password"
                              ) -> str | None:
    """
    Prompt for a password twice and verify they match.

    Returns the password string, or None if cancelled.
    """
    while True:
        pw1 = password_input(screen, prompt)
        if pw1 is None:
            return None

        if not pw1:
            screen.show_error("Password cannot be empty.")
            continue

        pw2 = password_input(screen, confirm_prompt)
        if pw2 is None:
            return None

        if pw1 != pw2:
            screen.show_error("Passwords do not match. Please try again.")
            continue

        return pw1


def yes_no(screen: Screen, question: str,
           default: bool = True) -> bool | None:
    """
    Show a yes/no prompt. Returns True for yes, False for no,
    None if cancelled (ESC).
    """
    options = ["Yes", "No"]
    selected = 0 if default else 1

    while True:
        screen.refresh_size()
        screen.clear()
        screen.draw_header()
        screen.draw_footer("↑↓ Navigate  Enter Select  ESC Cancel")

        y = screen.content_y + 2
        # Draw question text, handling embedded newlines
        question_lines = question.split("\n")
        for ql in question_lines:
            screen.draw_text(y, 2, ql, COLOR_TITLE, bold=True)
            y += 1
        y += 1  # blank line between question and options

        for i, opt in enumerate(options):
            if i == selected:
                line = f"  > {opt}".ljust(screen.width - 4)
                screen.draw_text(y + i, 2, line, COLOR_SELECTED)
            else:
                screen.draw_text(y + i, 6, opt, COLOR_NORMAL)

        screen.stdscr.refresh()
        key = screen.get_input()

        if key in (curses.KEY_UP, ord('k')):
            selected = max(0, selected - 1)
        elif key in (curses.KEY_DOWN, ord('j')):
            selected = min(1, selected + 1)
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return selected == 0
        elif key == 27:
            return None
        elif key == curses.KEY_RESIZE:
            screen.refresh_size()


def confirm_destructive(screen: Screen, warning: str) -> bool:
    """
    Show a destructive action warning that requires the user to type 'yes'.

    Returns True only if the user types 'yes' exactly.
    """
    result = text_input(
        screen,
        f"⚠  WARNING: {warning}\n\n"
        f"Type 'yes' to confirm, or press ESC to cancel:",
    )
    return result is not None and result.strip().lower() == "yes"


def show_progress(screen: Screen, steps: list[dict],
                  on_step=None) -> bool:
    """
    Display an installation progress screen.

    Parameters
    ----------
    steps : list[dict]
        Each dict has: 'label' (str), 'func' (callable that returns (bool, str))
    on_step : callable or None
        Optional callback(step_index, label) called before each step.

    Returns
    -------
    bool
        True if all steps completed successfully.
    """
    results = []  # List of (status, label, error_msg)

    screen.clear()
    screen.draw_header()
    screen.draw_footer("Installation in progress...")

    y_start = screen.content_y + 2
    screen.draw_text(y_start - 1, 2, "Installing Artix Linux", COLOR_TITLE, bold=True)

    for i, step in enumerate(steps):
        label = step["label"]
        func = step["func"]
        live_output = step.get("live_output", False)

        # Draw current status
        y = y_start + i
        if y >= screen.footer_y - 1:
            # Scroll: shift everything up
            screen.clear()
            screen.draw_header()
            screen.draw_footer("Installation in progress...")
            screen.draw_text(y_start - 1, 2, "Installing Artix Linux", COLOR_TITLE, bold=True)
            offset = i - (screen.footer_y - y_start - 3)
            for j, (status, rlabel, _) in enumerate(results):
                ry = y_start + j - offset
                if ry >= y_start and ry < screen.footer_y - 1:
                    marker = "[✓]" if status else "[✗]"
                    color = COLOR_VALUE_SET if status else COLOR_ERROR
                    screen.draw_text(ry, 4, f"{marker} {rlabel}", color)
            y = y_start + i - offset

        # Show spinner/working indicator
        screen.draw_text(y, 4, f"[⟳] {label}...", COLOR_NORMAL, bold=True)
        screen.stdscr.refresh()

        if on_step:
            on_step(i, label)

        # Execute the step
        try:
            if live_output:
                curses.endwin()
                print(f"\n==> {label} (live output below)\n")
                success, error = func()
                curses.reset_prog_mode()
                screen.stdscr.refresh()
                curses.doupdate()
                screen.refresh_size()
                screen.clear()
                screen.draw_header()
                screen.draw_footer("Installation in progress...")
                screen.draw_text(y_start - 1, 2, "Installing Artix Linux", COLOR_TITLE, bold=True)
                for j, (status, rlabel, _) in enumerate(results):
                    ry = y_start + j
                    if ry < screen.footer_y - 1:
                        marker = "[âœ“]" if status else "[âœ—]"
                        color = COLOR_VALUE_SET if status else COLOR_ERROR
                        screen.draw_text(ry, 4, f"{marker} {rlabel}", color)
                y = y_start + i
            else:
                success, error = func()
        except Exception as e:
            success = False
            error = str(e)

        results.append((success, label, error))

        # Update display
        if success:
            screen.draw_text(y, 4, f"[✓] {label}   ", COLOR_VALUE_SET)
        else:
            screen.draw_text(y, 4, f"[✗] {label}   ", COLOR_ERROR)
            screen.stdscr.refresh()

            # Show error details and ask what to do
            error_lines = error[:200] if error else "Unknown error"
            err_y = y + 1
            screen.draw_text(err_y, 8, f"Error: {error_lines}", COLOR_ERROR)
            screen.draw_footer("R to retry  A to abort  S to skip")
            screen.stdscr.refresh()

            while True:
                key = screen.get_input()
                if key in (ord('r'), ord('R')):
                    # Retry this step
                    results.pop()
                    screen.draw_text(y, 4, f"[⟳] {label}...", COLOR_NORMAL, bold=True)
                    screen.draw_text(err_y, 8, " " * 60, COLOR_NORMAL)
                    screen.draw_footer("Installation in progress...")
                    screen.stdscr.refresh()
                    try:
                        if live_output:
                            curses.endwin()
                            print(f"\n==> Retrying {label} (live output below)\n")
                            success, error = func()
                            curses.reset_prog_mode()
                            screen.stdscr.refresh()
                            curses.doupdate()
                            screen.refresh_size()
                        else:
                            success, error = func()
                    except Exception as e:
                        success = False
                        error = str(e)
                    results.append((success, label, error))
                    if success:
                        screen.draw_text(y, 4, f"[✓] {label}   ", COLOR_VALUE_SET)
                        screen.draw_text(err_y, 8, " " * 60, COLOR_NORMAL)
                        break
                    else:
                        error_lines = error[:200] if error else "Unknown error"
                        screen.draw_text(y, 4, f"[✗] {label}   ", COLOR_ERROR)
                        screen.draw_text(err_y, 8, f"Error: {error_lines}", COLOR_ERROR)
                        screen.draw_footer("R to retry  A to abort  S to skip")
                        screen.stdscr.refresh()
                        continue

                elif key in (ord('a'), ord('A')):
                    screen.draw_footer("Installation aborted. Press any key.")
                    screen.stdscr.refresh()
                    screen.get_input()
                    return False

                elif key in (ord('s'), ord('S')):
                    screen.draw_text(y, 4, f"[–] {label} (skipped)", COLOR_VALUE_UNSET)
                    screen.draw_text(err_y, 8, " " * 60, COLOR_NORMAL)
                    break

        screen.stdscr.refresh()

    # All done
    screen.draw_footer("Press any key to continue")
    screen.stdscr.refresh()
    screen.get_input()

    return all(status for status, _, _ in results)
