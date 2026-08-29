"""Personal proxy access, protected for the current Windows user (DPAPI)."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from openai import AsyncOpenAI

PROXY_URL = "https://atlasbot.freeboxos.fr/atlas-api/v1/"


def access_path():
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "Atlas" / "auth" / "access.bin" if local else None


def decrypt_access(data):
    if os.name != "nt":
        raise RuntimeError("L’activation Atlas protégée nécessite Windows.")

    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Activation Atlas illisible : réactivez ce compte Windows.")
    try:
        token = ctypes.string_at(target.data, target.length).decode("ascii")
        if not token.startswith("atlas_") or len(token) > 128:
            raise ValueError("Invalid activation")
        return token
    finally:
        kernel.LocalFree(target.data)


def create_client():
    path = access_path()
    if path is not None and path.exists():
        # Never pass the owner's key to the relay, even if present locally.
        token = decrypt_access(path.read_bytes())
        return AsyncOpenAI(api_key=token, base_url=PROXY_URL,
            websocket_base_url=PROXY_URL.replace("https://", "wss://"), max_retries=0)
    key = os.getenv("OPENAI_API_KEY")
    if key:
        # Retain direct access for the developer, with an explicit trusted endpoint.
        return AsyncOpenAI(api_key=key, base_url="https://api.openai.com/v1/",
                           websocket_base_url="wss://api.openai.com/v1/")
    raise RuntimeError("Atlas non activé : exécutez votre fichier Activer-Atlas.ps1 puis redémarrez le Core.")
