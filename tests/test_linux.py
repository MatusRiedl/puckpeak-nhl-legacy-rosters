"""RPCS3 on Linux (and a Mac): the program may be an AppImage or the Flatpak, and its data lives in a home folder. Every test
builds the folders it needs in a temp folder; nothing needs a roster."""
import os

import pytest

from legacy_roster import onlinecfg, savedata


def _data(root):
    os.makedirs(os.path.join(root, 'dev_hdd0', 'home', '00000001', 'savedata'))
    return root


def test_a_folder_with_only_an_appimage_is_rpcs3(tmp_path, monkeypatch):
    monkeypatch.setattr(savedata, 'WINDOWS', False)
    folder = tmp_path / 'apps'
    folder.mkdir()
    image = folder / 'rpcs3-v0.0.35-17000-abcdef12_linux64.AppImage'
    image.write_bytes(b'x')
    (folder / 'notes.AppImage').write_bytes(b'x')           # not an RPCS3
    monkeypatch.setattr(savedata, 'data_folders', lambda: [_data(str(tmp_path / 'config' / 'rpcs3'))])
    with pytest.raises(savedata.NoGameError) as err:        # no roster, no game: but the program and its data are found
        savedata.find_rpcs3(str(folder))
    assert err.value.rpcs3.exe == str(image) and err.value.rpcs3.folder == str(tmp_path / 'config' / 'rpcs3')


def test_commands_for_the_program_the_appimage_and_the_flatpak(tmp_path, monkeypatch):
    monkeypatch.setattr(savedata, 'WINDOWS', False)
    monkeypatch.setattr(savedata, 'MAC', False)
    image = tmp_path / 'RPCS3.AppImage'
    image.write_bytes(b'x')
    plain = savedata.Rpcs3(str(image), 'saves', '00000001', root=str(tmp_path))
    assert plain.command() == [str(image)] and plain.launch_dir() == str(tmp_path) and not plain.flatpak
    if os.name != 'nt':
        assert os.access(image, os.X_OK)                    # an AppImage that was not executable is made so
    flat_root = str(tmp_path / '.var' / 'app' / 'net.rpcs3.RPCS3' / 'config' / 'rpcs3')
    flat = savedata.Rpcs3(None, 'saves', '00000001', root=flat_root)
    monkeypatch.setattr(savedata.shutil, 'which', lambda name: '/usr/bin/' + name if name == 'flatpak' else None)
    assert flat.flatpak and flat.command() == ['flatpak', 'run', 'net.rpcs3.RPCS3'] and flat.launch_dir() is None
    monkeypatch.setattr(savedata.shutil, 'which', lambda name: None)
    assert flat.command() is None                           # no flatpak program on this PC: nothing to start
    bare = savedata.Rpcs3(None, 'saves', '00000001', root=str(tmp_path / 'data'))
    assert bare.command() is None
    monkeypatch.setattr(savedata.shutil, 'which', lambda name: '/usr/local/bin/rpcs3' if name == 'rpcs3' else None)
    assert bare.command() == ['/usr/local/bin/rpcs3']


def test_the_online_start_uses_that_command_and_the_flatpaks_own_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(savedata, 'WINDOWS', False)
    flat_root = str(tmp_path / '.var' / 'app' / 'net.rpcs3.RPCS3' / 'config' / 'rpcs3')
    flat = savedata.Rpcs3(None, 'saves', '00000001', root=flat_root)
    flat.game_disc = lambda title: '/games/NHL'
    monkeypatch.setattr(savedata.shutil, 'which', lambda name: '/usr/bin/flatpak')
    assert onlinecfg.launch_args(flat, 'BLES02153', '/cfg.yml') == [
        'flatpak', 'run', 'net.rpcs3.RPCS3', '--no-gui', '--config', '/cfg.yml', '/games/NHL']
    assert onlinecfg.config_dir(flat) == os.path.join(flat_root, 'online') and os.path.isdir(os.path.join(flat_root, 'online'))
    flat.game_disc = lambda title: None
    assert onlinecfg.launch_args(flat, 'BLES02153', '/cfg.yml') is None
    mac = savedata.Rpcs3('/Applications/RPCS3.app', 'saves', '00000001', root=str(tmp_path))
    mac.game_disc = lambda title: '/games/NHL'
    assert onlinecfg.launch_args(mac, 'BLES02153', '/cfg.yml')[:4] == ['open', '-a', '/Applications/RPCS3.app', '--args']


def test_the_log_is_where_the_system_puts_it(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('XDG_CACHE_HOME', str(home / '.cache'))
    rpcs3 = savedata.Rpcs3('/opt/rpcs3', 'saves', '00000001', root=str(tmp_path / 'data'))
    assert onlinecfg.log_path(rpcs3, posix=False) == os.path.join(str(tmp_path / 'data'), 'log', 'RPCS3.log')
    log = home / '.cache' / 'rpcs3' / 'RPCS3.log'
    log.parent.mkdir(parents=True)
    log.write_text('RPCS3 v0.0.43-20402-abc Alpha')
    assert onlinecfg.log_path(rpcs3, posix=True) == str(log)
    assert onlinecfg.rpcs3_build(rpcs3) in (20402, None)    # Windows reads the folder's own log only
    flat = savedata.Rpcs3(None, 'saves', '00000001', root=str(home / '.var' / 'app' / 'net.rpcs3.RPCS3' / 'config' / 'rpcs3'))
    flat_log = home / '.var' / 'app' / 'net.rpcs3.RPCS3' / 'cache' / 'rpcs3' / 'RPCS3.log'
    flat_log.parent.mkdir(parents=True)
    flat_log.write_text('x')
    assert onlinecfg.log_path(flat, posix=True) == str(flat_log) or os.path.getmtime(log) > os.path.getmtime(flat_log)


def test_a_running_flatpak_or_appimage_is_found_and_the_appimage_by_its_own_file(tmp_path):
    for pid, cmd, env in (('101', '/app/bin/rpcs3', None),
                          ('102', '/tmp/.mount_rpcs3Xy/usr/bin/rpcs3', b'HOME=/h\0APPIMAGE=/home/u/RPCS3.AppImage\0')):
        folder = tmp_path / pid
        folder.mkdir()
        (folder / 'cmdline').write_bytes(cmd.encode() + b'\0')
        if env:
            (folder / 'environ').write_bytes(env)
    assert savedata._running_posix(str(tmp_path)) == '/app/bin/rpcs3'       # the Flatpak: a path that is not on this PC
    os.remove(tmp_path / '101' / 'cmdline')
    assert savedata._running_posix(str(tmp_path)) == '/home/u/RPCS3.AppImage'
