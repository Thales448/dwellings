import queue
import threading
from typing import Any


class Hub:
    def __init__(self) -> None:
        self._subs: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        mailbox: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)
        with self._lock:
            self._subs.append(mailbox)
        return mailbox

    def unsubscribe(self, mailbox: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if mailbox in self._subs:
                self._subs.remove(mailbox)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            targets = list(self._subs)
        for mailbox in targets:
            try:
                mailbox.put_nowait(event)
            except queue.Full:
                continue


hub = Hub()
