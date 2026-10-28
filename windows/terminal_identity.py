"""Read task identities without exposing command arguments or blocking the UI."""
import ntpath
import re
import psutil

HELPERS = {'conhost.exe', 'openconsole.exe', 'winpty-agent.exe', 'cmd.exe', 'powershell.exe', 'pwsh.exe'}
KNOWN = {'Yunzai', 'Vite', 'Next.js', 'Nuxt'}


def process_label(name, args):
    command = ' '.join(args) if args else name
    for token, label in [('yunzai', 'Yunzai'), ('vite', 'Vite'), ('next', 'Next.js'), ('nuxt', 'Nuxt')]:
        if re.search(r'(^|[/\\ @:_-])' + token + r'([/\\ .:@_-]|$)', command, re.I): return label
    executable = ntpath.basename(name)
    runtime = executable.lower().removesuffix('.exe')
    if not any(flag in args for flag in ('-c', '-e', '--eval')) and (runtime in {'node', 'python', 'python3', 'ruby', 'java', 'deno', 'bun'} or re.fullmatch(r'python3\.\d+', runtime)):
        script = next((arg for arg in args[1:] if not arg.startswith('-') and arg != 'run'), '')
        if '/' in script or '\\' in script or script.endswith(('.js', '.mjs', '.py', '.jar', '.rb', '.ts')):
            return ntpath.basename(script)[:40]
    return ''.join(c for c in executable if ord(c) >= 32 and ord(c) != 127)[:40]


def task_identity(pid):
    try: children = psutil.Process(pid).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied): return None
    candidates = []
    for child in children:
        try:
            name = child.name()
            if name.lower() in HELPERS or child.status() == psutil.STATUS_ZOMBIE: continue
            try: args = child.cmdline()
            except psutil.AccessDenied: args = []
            candidates.append((process_label(name, args), child.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
    return next((item for item in candidates if item[0] in KNOWN), candidates[-1] if candidates else None)
