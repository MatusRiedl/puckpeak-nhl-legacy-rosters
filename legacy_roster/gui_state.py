"""Small, toolkit-independent helpers for keeping asynchronous window state current."""


def is_current_scan(scan_id, latest_id):
    """Whether a background roster scan still belongs to the latest requested path."""
    return scan_id == latest_id


def sync_packed_order(container, ordered_widgets):
    """Reorder packed widgets in place, avoiding destroy/recreate redraws."""
    ordered_widgets = list(ordered_widgets)
    if container.pack_slaves() == ordered_widgets:
        return
    for index in range(len(ordered_widgets) - 1, -1, -1):
        widget = ordered_widgets[index]
        if index + 1 < len(ordered_widgets):
            widget.pack_configure(before=ordered_widgets[index + 1])
        else:
            siblings = container.pack_slaves()
            last = next((child for child in reversed(siblings) if child is not widget), None)
            if last is not None:
                widget.pack_configure(after=last)
