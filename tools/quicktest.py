"""Run only the tests a change can affect, in parallel. Minutes, not an hour.

    python tools/quicktest.py                 tests of every changed file (git status), parallel
    python tools/quicktest.py --full          the whole suite, parallel (before a release)
    python tools/quicktest.py --list          only say which test files would run
    python tools/quicktest.py tests/test_x.py extra pytest words ...

A changed test file runs itself. A changed module runs the test files that name it (`import` or `name.`); a module
nearly every test builds on (pipeline, builder, layout ...) runs the CORE files instead. Needs pytest and pytest-xdist
(`pip install pytest pytest-xdist`); sets LEGACY_ROSTER_DISC from the environment only, never a path of its own.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, 'tests')
CORE = ['test_pipeline.py', 'test_leagues.py', 'test_lineups.py', 'test_contracts.py', 'test_gamepatch.py',
        'test_edits.py', 'test_identity.py']
WIDE = {'pipeline', 'builder', 'layout', 'verify', 'roster', 'tdb', 'schema', 'schema_names', 'datasource', 'matching',
        'donors', 'edits', 'conftest'}
WORKERS = max(2, min(12, (os.cpu_count() or 4) - 2))


def changed():
    out = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd=ROOT, capture_output=True, text=True).stdout
    return [line[3:].strip().strip('"') for line in out.splitlines() if line[3:].strip().endswith('.py')]


def mentions(stem):
    pattern = re.compile(rf'(\bimport\s+[\w, ]*\b{stem}\b|\bfrom\s+[\w.]*\b{stem}\b|\b{stem}\.)')
    hit = []
    for name in sorted(os.listdir(TESTS)):
        if name.startswith('test_') and name.endswith('.py'):
            with open(os.path.join(TESTS, name), encoding='utf-8') as f:
                if pattern.search(f.read()):
                    hit.append(name)
    return hit


def select(paths):
    files, why = [], {}
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        if path.startswith('tests/') and stem.startswith('test_'):
            found = [stem + '.py']
        elif stem in WIDE:
            found = CORE
        elif path.endswith('.py') and not path.startswith('docs'):
            found = mentions(stem)
        else:
            found = []
        for name in found:
            if name not in files and os.path.exists(os.path.join(TESTS, name)):
                files.append(name)
                why[name] = path
    return files, why


def main(argv):
    full, only_list = '--full' in argv, '--list' in argv
    argv = [a for a in argv if a not in ('--full', '--list')]
    explicit = [a for a in argv if a.startswith('tests') or a.endswith('.py')]
    extra = [a for a in argv if a not in explicit]
    if full:
        targets = []
    elif explicit:
        targets = explicit
    else:
        names, why = select(changed())
        targets = [os.path.join('tests', n) for n in names]
        for n in names:
            print(f"  {n:34} <- {why[n]}")
        if not targets:
            print("no test file is affected by the changed files")
            return 0
    if only_list:
        return 0
    cmd = [sys.executable, '-m', 'pytest', '-q', '--tb=short', '-p', 'no:cacheprovider', '--durations=8',
           '-n', str(WORKERS), '--dist', 'loadfile'] + targets + extra
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
