from __future__ import annotations

import ctypes
import os
import re

from ctypes import wintypes


# =========================================================
# Constantes Windows
# =========================================================

TOKEN_QUERY = 0x0008

TOKEN_USER_CLASS = 1

SDDL_REVISION_1 = 1


# Droits nécessaires au CLIENT Atlas :
#
# FILE_READ_DATA
# FILE_WRITE_DATA
# FILE_READ_EA
# FILE_WRITE_EA
# FILE_READ_ATTRIBUTES
# FILE_WRITE_ATTRIBUTES
# READ_CONTROL
# SYNCHRONIZE
#
# On exclut volontairement FILE_APPEND_DATA (0x0004),
# car pour un Named Pipe ce bit correspond aussi à
# FILE_CREATE_PIPE_INSTANCE.
#
# Cela empêche le client Atlas d'obtenir le droit
# de créer lui-même une instance serveur du pipe.

CLIENT_PIPE_ACCESS_MASK = 0x0012019B


SID_PATTERN = re.compile(
    r"^S-\d+(?:-\d+)+$"
)


# =========================================================
# Structures Windows
# =========================================================


class SID_AND_ATTRIBUTES(
    ctypes.Structure
):

    _fields_ = [
        (
            "Sid",
            wintypes.LPVOID,
        ),
        (
            "Attributes",
            wintypes.DWORD,
        ),
    ]


class TOKEN_USER(
    ctypes.Structure
):

    _fields_ = [
        (
            "User",
            SID_AND_ATTRIBUTES,
        ),
    ]


class SECURITY_ATTRIBUTES(
    ctypes.Structure
):

    _fields_ = [
        (
            "nLength",
            wintypes.DWORD,
        ),
        (
            "lpSecurityDescriptor",
            wintypes.LPVOID,
        ),
        (
            "bInheritHandle",
            wintypes.BOOL,
        ),
    ]


# =========================================================
# DLL Windows
# =========================================================


kernel32 = ctypes.WinDLL(
    "kernel32",
    use_last_error=True,
)

advapi32 = ctypes.WinDLL(
    "advapi32",
    use_last_error=True,
)


# =========================================================
# Prototypes
# =========================================================


kernel32.GetCurrentProcess.argtypes = []

kernel32.GetCurrentProcess.restype = (
    wintypes.HANDLE
)


kernel32.CloseHandle.argtypes = [
    wintypes.HANDLE,
]

kernel32.CloseHandle.restype = (
    wintypes.BOOL
)


kernel32.LocalFree.argtypes = [
    wintypes.LPVOID,
]

kernel32.LocalFree.restype = (
    wintypes.LPVOID
)


advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(
        wintypes.HANDLE
    ),
]

advapi32.OpenProcessToken.restype = (
    wintypes.BOOL
)


advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(
        wintypes.DWORD
    ),
]

advapi32.GetTokenInformation.restype = (
    wintypes.BOOL
)


advapi32.ConvertSidToStringSidW.argtypes = [
    wintypes.LPVOID,
    ctypes.POINTER(
        wintypes.LPWSTR
    ),
]

advapi32.ConvertSidToStringSidW.restype = (
    wintypes.BOOL
)


advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(
        wintypes.LPVOID
    ),
    ctypes.POINTER(
        wintypes.DWORD
    ),
]

advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = (
    wintypes.BOOL
)


# =========================================================
# Exceptions
# =========================================================


class PipeSecurityError(
    RuntimeError
):
    pass


# =========================================================
# SID utilisateur
# =========================================================


def get_current_user_sid() -> str:

    if os.name != "nt":

        raise PipeSecurityError(
            "La sécurité des Named Pipes "
            "est disponible uniquement "
            "sous Windows."
        )

    token = (
        wintypes.HANDLE()
    )

    process = (
        kernel32.GetCurrentProcess()
    )

    if not advapi32.OpenProcessToken(
        process,
        TOKEN_QUERY,
        ctypes.byref(
            token
        ),
    ):

        raise PipeSecurityError(
            "Impossible d'ouvrir le token "
            f"Windows : {ctypes.WinError(ctypes.get_last_error())}"
        )

    try:

        required_size = (
            wintypes.DWORD(
                0
            )
        )

        # Premier appel volontairement sans buffer
        # pour connaître sa taille.
        advapi32.GetTokenInformation(
            token,
            TOKEN_USER_CLASS,
            None,
            0,
            ctypes.byref(
                required_size
            ),
        )

        if required_size.value == 0:

            raise PipeSecurityError(
                "Impossible de déterminer "
                "la taille du token utilisateur."
            )

        buffer = (
            ctypes.create_string_buffer(
                required_size.value
            )
        )

        if not advapi32.GetTokenInformation(
            token,
            TOKEN_USER_CLASS,
            buffer,
            required_size.value,
            ctypes.byref(
                required_size
            ),
        ):

            raise PipeSecurityError(
                "Impossible de lire le token "
                f"Windows : {ctypes.WinError(ctypes.get_last_error())}"
            )

        token_user = ctypes.cast(
            buffer,
            ctypes.POINTER(
                TOKEN_USER
            ),
        ).contents

        sid_string_pointer = (
            wintypes.LPWSTR()
        )

        if not advapi32.ConvertSidToStringSidW(
            token_user.User.Sid,
            ctypes.byref(
                sid_string_pointer
            ),
        ):

            raise PipeSecurityError(
                "Impossible de convertir "
                f"le SID : {ctypes.WinError(ctypes.get_last_error())}"
            )

        try:

            sid_string = (
                sid_string_pointer.value
            )

            if not sid_string:

                raise PipeSecurityError(
                    "Le SID Windows obtenu "
                    "est vide."
                )

            return sid_string

        finally:

            if sid_string_pointer:

                kernel32.LocalFree(
                    ctypes.cast(
                        sid_string_pointer,
                        wintypes.LPVOID,
                    )
                )

    finally:

        if token:

            kernel32.CloseHandle(
                token
            )


# =========================================================
# SID autorisé
# =========================================================


def resolve_allowed_user_sid(
    allowed_user_sid: str | None = None,
) -> str:

    sid = allowed_user_sid

    if sid is None:

        sid = os.getenv(
            "ATLAS_ALLOWED_USER_SID"
        )

    if sid is None:

        sid = get_current_user_sid()

    sid = sid.strip()

    if not SID_PATTERN.fullmatch(
        sid
    ):

        raise PipeSecurityError(
            "Le SID utilisateur Atlas "
            "est invalide."
        )

    return sid


# =========================================================
# Security Descriptor
# =========================================================


def create_pipe_security_attributes(
    allowed_user_sid: str,
) -> tuple[
    SECURITY_ATTRIBUTES,
    wintypes.LPVOID,
    str,
]:

    allowed_user_sid = (
        resolve_allowed_user_sid(
            allowed_user_sid
        )
    )

    # D:P
    # = DACL protégée.
    #
    # SY = LocalSystem
    # BA = Builtin Administrators
    #
    # L'utilisateur Atlas reçoit uniquement
    # les droits individuels nécessaires au
    # transport duplex.

    client_rights = (
        f"0x{CLIENT_PIPE_ACCESS_MASK:08X}"
    )

    sddl = (
        "D:P"
        "(A;;GA;;;SY)"
        "(A;;GA;;;BA)"
        f"(A;;{client_rights};;;{allowed_user_sid})"
    )

    security_descriptor = (
        wintypes.LPVOID()
    )

    if not (
        advapi32
        .ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl,
            SDDL_REVISION_1,
            ctypes.byref(
                security_descriptor
            ),
            None,
        )
    ):

        raise PipeSecurityError(
            "Impossible de créer le "
            "Security Descriptor du pipe : "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )

    security_attributes = (
        SECURITY_ATTRIBUTES()
    )

    security_attributes.nLength = (
        ctypes.sizeof(
            SECURITY_ATTRIBUTES
        )
    )

    security_attributes.lpSecurityDescriptor = (
        security_descriptor
    )

    security_attributes.bInheritHandle = (
        False
    )

    return (
        security_attributes,
        security_descriptor,
        sddl,
    )


def free_security_descriptor(
    security_descriptor: wintypes.LPVOID,
) -> None:

    if security_descriptor:

        kernel32.LocalFree(
            security_descriptor
        )