"""Update credentials use Windows Credential Manager, never INI or logs."""
import ctypes
from ctypes import wintypes
import sys

TARGET = 'LocalDeck/GitHubUpdates'


class CredentialError(Exception): pass


class CREDENTIAL(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD), ('TargetName', wintypes.LPWSTR),
                ('Comment', wintypes.LPWSTR), ('LastWritten', wintypes.FILETIME),
                ('CredentialBlobSize', wintypes.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
                ('Persist', wintypes.DWORD), ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


def api():
    if sys.platform != 'win32': raise CredentialError('私有仓库授权需要 Windows 凭据管理器。')
    library = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    library.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    library.CredReadW.restype = wintypes.BOOL
    library.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]; library.CredWriteW.restype = wintypes.BOOL
    library.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]; library.CredDeleteW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]; library.CredFree.restype = None
    return library


def read_token():
    if sys.platform != 'win32': return ''
    library = api(); value = ctypes.POINTER(CREDENTIAL)()
    if not library.CredReadW(TARGET, 1, 0, ctypes.byref(value)):
        if ctypes.get_last_error() == 1168: return ''
        raise CredentialError('无法读取更新授权，请检查 Windows 凭据管理器。')
    try: return ctypes.string_at(value.contents.CredentialBlob, value.contents.CredentialBlobSize).decode('utf-8')
    finally: library.CredFree(value)


def save_token(token):
    library = api()
    if not token:
        if not library.CredDeleteW(TARGET, 1, 0) and ctypes.get_last_error() != 1168: raise CredentialError('无法移除更新授权。')
        return
    blob = token.encode('utf-8')
    if len(blob) > 2560: raise CredentialError('访问令牌过长。')
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    value = CREDENTIAL(); value.Type = 1; value.TargetName = TARGET; value.CredentialBlobSize = len(blob)
    value.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)); value.Persist = 2; value.UserName = 'GitHub'
    if not library.CredWriteW(ctypes.byref(value), 0): raise CredentialError('无法保存更新授权，请检查 Windows 凭据管理器。')
