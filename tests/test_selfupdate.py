"""The update check: versions, GitHub's answer, the checksum, the swap of the exe."""
import hashlib
import http.server
import threading

import pytest

from legacy_roster.app import selfupdate as U


def release_json(tag='v0.11.0', digest=None, **extra):
    asset = {'name': U.EXE_ASSET, 'browser_download_url': 'http://x/exe', 'size': 3}
    if digest:
        asset['digest'] = 'sha256:' + digest
    data = {'tag_name': tag, 'html_url': 'http://x/page', 'body': '# New\n- a thing', 'assets': [asset]}
    data.update(extra)
    return data


def test_parse_version():
    assert U.parse_version('v0.11.0') == (0, 11, 0)
    assert U.parse_version('0.10') == (0, 10, 0)
    assert U.parse_version('v0.9.2-beta') is None
    assert U.parse_version(None) is None
    assert U.parse_version('0.10.0') < U.parse_version('0.11.0') < U.parse_version('0.100.0')


def test_latest_only_when_newer():
    assert U.latest('0.10.0', lambda url: release_json('v0.11.0')).text == '0.11.0'
    assert U.latest('0.11.0', lambda url: release_json('v0.11.0')) is None
    assert U.latest('0.12.0', lambda url: release_json('v0.11.0')) is None


def test_latest_ignores_drafts_prereleases_and_errors():
    assert U.latest('0.10.0', lambda url: release_json(prerelease=True)) is None
    assert U.latest('0.10.0', lambda url: release_json(draft=True)) is None

    def offline(url):
        raise OSError("no connection")
    assert U.latest('0.10.0', offline) is None
    assert U.latest('0.10.0', lambda url: ['not', 'a', 'release']) is None


def test_digest_from_the_asset_or_the_sums_file():
    digest = 'ab' * 32
    assert U.from_json(release_json(digest=digest)).digest == digest
    assert U.from_json(release_json(digest=digest)).can_install()
    plain = release_json()
    assert not U.from_json(plain).can_install()
    plain['assets'].append({'name': U.SUMS_ASSET, 'browser_download_url': 'http://x/sums'})
    sums = f"{digest}  {U.EXE_ASSET}\n"
    assert U.from_json(plain, lambda url: sums).digest == digest
    assert U.from_json(plain, lambda url: "nonsense").digest is None


def test_due_every_twelve_hours_and_not_when_switched_off():
    assert U.due({}, now=10 ** 6)
    assert not U.due({'update_checked': 1000}, now=1000 + U.CHECK_EVERY - 1)
    assert U.due({'update_checked': 1000}, now=1000 + U.CHECK_EVERY)
    assert not U.due({'check_updates': False}, now=10 ** 9)


@pytest.fixture
def server(tmp_path):
    body = b'new program'
    served = {'body': body}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(served['body'])))
            self.end_headers()
            self.wfile.write(served['body'])

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/exe", served
    httpd.shutdown()


def test_download_checks_the_checksum(server, tmp_path):
    url, served = server
    good = U.Release((0, 11, 0), 'v0.11.0', '', 'p', url, 0, hashlib.sha256(served['body']).hexdigest())
    seen = []
    target = tmp_path / 'x.new'
    U.download(good, str(target), seen.append)
    assert target.read_bytes() == b'new program' and seen and seen[-1] == 1.0

    bad = U.Release((0, 11, 0), 'v0.11.0', '', 'p', url, 0, '0' * 64)
    other = tmp_path / 'y.new'
    with pytest.raises(ValueError):
        U.download(bad, str(other))
    assert not other.exists()          # a file that is not the published one is not kept


def test_swap_replaces_and_keeps_the_old_one(tmp_path):
    exe, new = tmp_path / 'app.exe', tmp_path / 'app.exe.new'
    exe.write_bytes(b'old')
    new.write_bytes(b'new')
    U.swap(str(new), str(exe))
    assert exe.read_bytes() == b'new' and (tmp_path / 'app.exe.old').read_bytes() == b'old'
    U.clean_leftovers(str(exe))
    assert not (tmp_path / 'app.exe.old').exists()


def test_swap_puts_the_old_exe_back_when_the_new_one_is_missing(tmp_path):
    exe = tmp_path / 'app.exe'
    exe.write_bytes(b'old')
    with pytest.raises(OSError):
        U.swap(str(tmp_path / 'missing.new'), str(exe))
    assert exe.read_bytes() == b'old'


def test_a_source_run_cannot_replace_itself():
    assert U.running_exe() is None
    with pytest.raises(RuntimeError):
        U.install(U.Release((9, 0, 0), 'v9', '', 'p', 'http://x', 1, 'a' * 64))
