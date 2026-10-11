from legacy_roster.gui_state import is_current_scan, sync_packed_order


class FakeWidget:
    def __init__(self, parent):
        self.parent = parent

    def pack_configure(self, before=None, after=None):
        siblings = self.parent.children
        siblings.remove(self)
        if before is not None:
            siblings.insert(siblings.index(before), self)
        elif after is not None:
            siblings.insert(siblings.index(after) + 1, self)
        else:
            siblings.append(self)


class FakeContainer:
    def __init__(self):
        self.children = []

    def pack_slaves(self):
        return list(self.children)


def test_only_the_latest_roster_scan_can_update_the_window():
    assert is_current_scan(4, 4)
    assert not is_current_scan(3, 4)


def test_existing_roster_rows_are_reordered_in_place():
    container = FakeContainer()
    a, b, c = (FakeWidget(container) for _ in range(3))
    container.children[:] = [a, b, c]

    sync_packed_order(container, [c, b, a])

    assert container.pack_slaves() == [c, b, a]
    sync_packed_order(container, [c, b, a])
    assert container.pack_slaves() == [c, b, a]
