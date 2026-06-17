import os
import glob
import logging
from datetime import datetime


class SessionErrorLogger:
    def __init__(self, log_dir="~/.anton_logs", max_files=5, debug_mode=False):
        self.log_dir = os.path.expanduser(log_dir)
        self.max_files = max_files
        self.debug_mode = debug_mode
        self._setup()

    def _setup(self):
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
            except OSError:
                pass

        self._cleanup_old_logs()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.log_dir, f"error_session_{timestamp}.log")

        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        root_logger.setLevel(logging.DEBUG if self.debug_mode else logging.ERROR)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG if self.debug_mode else logging.ERROR)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except OSError:
            pass

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if self.debug_mode else logging.CRITICAL)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    def _cleanup_old_logs(self):
        try:
            pattern = os.path.join(self.log_dir, "error_session_*.log")
            files = glob.glob(pattern)

            files.sort(key=os.path.getmtime)

            while len(files) >= self.max_files:
                oldest_file = files.pop(0)
                os.remove(oldest_file)
        except OSError:
            pass
