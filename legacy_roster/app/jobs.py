"""Work that takes a while runs in a thread of its own; the window stays responsive."""
import datetime
import os
import threading
import traceback

from .. import datasource


def log_block(lines=(), err=None):
    """Append one block to logs/error.log for a bug report: the time, the program's version, `lines` (what the
    program was doing: the roster, the folders, the steps) and the traceback of the error being handled. Returns the
    log's path."""
    from .. import __version__
    path = datasource.app_dir('logs', 'error.log')
    text = [f"=== {datetime.datetime.now().isoformat(timespec='seconds')}  version {__version__}"]
    text += [f"    {line}" for line in lines]
    if err is not None:
        text.append(traceback.format_exc().rstrip() if err.__traceback__ else f"{type(err).__name__}: {err}")
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(text) + '\n\n')
    except OSError:
        pass
    return path


def where(err):
    """The last frame of the program's own code in `err`'s traceback as " (file.py:123 in function)", '' when it has
    none: a player's screenshot of the message then says where it went wrong."""
    last = None
    for frame in traceback.extract_tb(err.__traceback__):
        parts = frame.filename.replace(os.sep, '/').split('/legacy_roster/')
        if len(parts) > 1:
            last = (parts[-1], frame.lineno, frame.name)
    return f" ({last[0]}:{last[1]} in {last[2]})" if last else ''


def log_unexpected(err, context=()):
    """Keep the details of an unexpected error for a bug report; returns what to tell the player."""
    path = log_block(context, err)
    return f"Something went wrong: {err}{where(err)}\nThe details were saved to {path}"


def run(work, done=None, failed=None, expected=(), context=None):
    """work() in a background thread; then done(result), or failed(message) when it raised. The
    `expected` errors are told as they are, anything else is logged first (log_unexpected). Every failure leaves a
    block in the error log; `context()` gives its lines (what the work was about), asked only when it failed."""
    def lines():
        try:
            return list(context()) if context else []
        except Exception as err:            # the context must never hide the error itself
            return [f"(the details could not be gathered: {err})"]

    def body():
        try:
            result = work()
        except expected as err:
            text = str(err)
            if isinstance(err, OSError) and err.filename and str(err.filename) not in text:
                text += f": {err.filename}"     # a missing folder: say which one
            log_block(lines(), err)
            if failed:
                failed(text)
            return
        except Exception as err:            # anything unexpected: keep the details for a bug report
            message = log_unexpected(err, lines())
            if failed:
                failed(message)
            return
        if done:
            done(result)
    thread = threading.Thread(target=body, daemon=True)
    thread.start()
    return thread
