"""Clear an old update token saved by pre-open-source builds."""
import ctypes
import sys


def clear_legacy_update_credential():
    if sys.platform != 'win32': return
    try:
        library = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
        library.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
        library.CredDeleteW.restype = ctypes.c_int
        library.CredDeleteW('LocalDeck/GitHubUpdates', 1, 0)
    except (AttributeError, OSError):
        pass
