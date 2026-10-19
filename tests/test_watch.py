"""Noticing changed files: reported once, and only after the file has stopped changing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watch import FileWatcher


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def later(self):
        self.now += 1.0


def test_a_change_is_reported_once_it_has_held_still(tmp_path):
    path = tmp_path / "map.json"
    path.write_text("one")
    clock = Clock()
    watcher = FileWatcher([path], clock=clock)
    clock.later()
    assert not watcher.changed()                    # nothing happened
    path.write_text("two!")
    clock.later()
    assert not watcher.changed()                    # seen changing: wait for it to settle
    clock.later()
    assert watcher.changed()                        # the same state twice: it is saved
    clock.later()
    assert not watcher.changed()                    # and only reported once


def test_a_file_still_being_written_is_waited_for(tmp_path):
    path = tmp_path / "map.json"
    path.write_text("one")
    clock = Clock()
    watcher = FileWatcher([path], clock=clock)
    path.write_text("")                             # half way through a save
    clock.later()
    assert not watcher.changed()
    path.write_text("the whole file")
    clock.later()
    assert not watcher.changed()                    # changed again since the last look
    clock.later()
    assert watcher.changed()


def test_checks_are_spaced_by_the_interval(tmp_path):
    path = tmp_path / "map.json"
    path.write_text("one")
    clock = Clock()
    watcher = FileWatcher([path], interval=5.0, clock=clock)
    path.write_text("two!")
    clock.now = 4.0
    assert not watcher.changed() and watcher.waiting is None    # too soon to look
    clock.now = 5.0
    watcher.changed()
    assert watcher.waiting is not None


def test_a_missing_file_is_a_change_when_it_appears(tmp_path):
    path = tmp_path / "textures.png"
    clock = Clock()
    watcher = FileWatcher([path], clock=clock)
    path.write_text("x")
    for _ in range(2):
        clock.later()
        result = watcher.changed()
    assert result
