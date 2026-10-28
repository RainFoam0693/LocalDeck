"""Prompt boundaries plus child processes distinguish an idle shell from a task."""
import uuid
import psutil


class PromptActivity:
    def __init__(self):
        self.tag = 'LocalDeck_' + uuid.uuid4().hex
        self.marker = '\x1b]133;A;' + self.tag + '\x1b\\'
        self.tail = ''
        self.executing = False
        self.seen_prompt = False

    def input(self, text):
        if '\r' in text or '\n' in text: self.executing = True

    def output(self, text):
        data = self.tail + text
        if self.marker in data: self.executing = False; self.seen_prompt = True
        self.tail = data[-(len(self.marker)-1):]

    def shell_options(self, shell, environment):
        env = dict(environment)
        if shell == 'powershell':
            # Keep the profile's original prompt, including custom themes.
            script = ("$global:__LocalDeckPrompt = $function:prompt; function global:prompt { "
                      "[Console]::Write([string][char]27 + ']133;A;" + self.tag + "' + [char]27 + '\\'); "
                      "if ($global:__LocalDeckPrompt) { & $global:__LocalDeckPrompt } "
                      "else { 'PS ' + (Get-Location) + '> ' } }")
            return ['powershell.exe', '-NoLogo', '-NoExit', '-Command', script], env
        env['PROMPT'] = self.marker.replace('\x1b', '$E') + env.get('PROMPT', '$P$G')
        return [env.get('COMSPEC', 'cmd.exe'), '/d'], env


def has_child_jobs(pid):
    try:
        children = psutil.Process(pid).children(recursive=True)
        for child in children:
            try:
                if child.status() == psutil.STATUS_ZOMBIE: continue
                if child.name().lower() not in {'conhost.exe', 'openconsole.exe', 'winpty-agent.exe'}: return True
            except psutil.NoSuchProcess: continue
            except psutil.AccessDenied: return True
        return False
    except psutil.NoSuchProcess: return False
    except psutil.AccessDenied: return True
