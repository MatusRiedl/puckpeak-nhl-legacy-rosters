"""Work that takes a while runs in a thread of its own; the window stays responsive."""
import threading
import traceback

from .. import datasource


def log_unexpected(err):
    """Keep the details of an unexpected error for a bug report; returns what to tell the player."""
    path = datasource.app_dir('logs', 'error.log')
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(traceback.format_exc() + '\n')
    except OSError:
        pass
    return f"Something went wrong: {err}\nThe details were saved to {path}"


def run(work, done=None, failed=None, expected=()):
    """work() in a background thread; then done(result), or failed(message) when it raised. The
    `expected` errors are told as they are, anything else is logged first (log_unexpected)."""
    def body():
        try:
            result = work()
        except expected as err:
            if failed:
                failed(str(err))
            return
        except Exception as err:            # anything unexpected: keep the details for a bug report
            message = log_unexpected(err)
            if failed:
                failed(message)
            return
        if done:
            done(result)
    thread = threading.Thread(target=body, daemon=True)
    thread.start()
    return thread
