import threading
import sys
import time

class Spinner:
    def __init__(self, message="Loading"):
        self.message = message
        # Moon phases sequence rotating clockwise
        self.spinner_chars = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
        self.stop_event = threading.Event()
        self.thread = None

    def _spin(self):
        idx = 0
        dots = 0
        while not self.stop_event.is_set():
            char = self.spinner_chars[idx % len(self.spinner_chars)]
            dot_str = "." * dots
            space_str = " " * (3 - dots)
            sys.stdout.write(f"\r  [{char}] {self.message}{dot_str}{space_str}")
            sys.stdout.flush()
            idx += 1
            dots = (dots + 1) % 4
            self.stop_event.wait(0.25)
        # Clean up line
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        if self.thread:
            self.stop_event.set()
            self.thread.join()
