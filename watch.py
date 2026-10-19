"""Noticing that files were changed on disk (the map and the textures, saved from the editor or an image editor)."""
import os
import time


class FileWatcher:
    """Call changed() once a frame: True once after the files changed and stopped changing.

    The files are checked every `interval` seconds. A change is only reported when two checks in a row see
    the same new state, so a file caught half way through being saved is waited for, not read."""

    def __init__(self, paths, interval=0.5, clock=time.monotonic):
        self.paths = list(paths)
        self.interval = interval
        self.clock = clock
        self.seen = self.stamps()
        self.waiting = None                         # the changed state seen at the last check, until it holds still
        self.next_check = clock() + interval

    def stamps(self):
        """(modification time, size) of each file; None for one that cannot be read."""
        stamps = []
        for path in self.paths:
            try:
                info = os.stat(path)
                stamps.append((info.st_mtime_ns, info.st_size))
            except OSError:
                stamps.append(None)
        return tuple(stamps)

    def changed(self):
        now = self.clock()
        if now < self.next_check:
            return False
        self.next_check = now + self.interval
        current = self.stamps()
        if current == self.seen:
            self.waiting = None
            return False
        if current != self.waiting:                 # still changing: look again before reading it
            self.waiting = current
            return False
        self.seen, self.waiting = current, None
        return True
