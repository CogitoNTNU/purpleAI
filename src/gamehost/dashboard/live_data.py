"""Share an incremental, normalized event snapshot across browser sessions."""

from threading import RLock

import pandas as pd
from activity import event_frame
from event_store import EventArchive


class LiveData:
    def __init__(self, directory):
        self.archive = EventArchive(directory)
        self.frame = event_frame([])
        self.lock = RLock()
        self.revision = -1

    def refresh(self):
        """Published frames are not mutated after return; callers treat them as read-only."""
        with self.lock:
            events = self.archive.refresh()
            if self.revision != self.archive.revision:
                if self.archive.rebuilt or self.frame.empty:
                    frame = event_frame(events)
                else:
                    frame = pd.concat(
                        [self.frame, event_frame(self.archive.appended)],
                        ignore_index=True,
                    )
                self.frame = frame.sort_values(
                    "time", kind="stable", na_position="last"
                ).reset_index(drop=True)
                self.revision = self.archive.revision
            return self.frame
