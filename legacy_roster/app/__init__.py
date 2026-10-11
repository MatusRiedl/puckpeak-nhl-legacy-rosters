"""The window's logic without any window toolkit: what the window shows (as plain data, "slices")
and what its buttons do. The web window (`window/`) shows the slices and calls the actions; the
tests drive the same controllers with a fake host. Standard library only (Pillow is imported lazily
for pictures), never pywebview."""
