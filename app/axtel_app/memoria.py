"""Leitura de memória compartilhada nomeada do Windows, somente leitura.

Usa OpenFileMappingW, que só abre o mapa se o jogo já o criou. O Axtel nunca
cria um mapa com o nome do jogo.
"""
import ctypes
import sys

# Buffers simulados (usados só pelos testes automáticos fora do Windows).
SIMULADOS = {}

if sys.platform == "win32":
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenFileMappingW.restype = wintypes.HANDLE
    _k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.MapViewOfFile.restype = ctypes.c_void_p
    _k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    _k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]

    class _MBI(ctypes.Structure):
        _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                    ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                    ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                    ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]

    _k32.VirtualQuery.restype = ctypes.c_size_t
    _k32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]

FILE_MAP_READ = 0x0004


class Pagina:
    """Uma página de memória compartilhada (ex.: Local\\acevo_pmf_graphics)."""

    def __init__(self, nome, tamanho):
        self.nome = nome
        self.tamanho = tamanho
        self._h = None
        self._p = None
        self._disp = 0
        self.erro = 0  # último erro do Windows ao abrir (5 = acesso negado)

    @property
    def aberta(self):
        return self._p is not None or self.nome in SIMULADOS

    def abrir(self):
        if self.nome in SIMULADOS:
            return True
        if sys.platform != "win32":
            return False
        if self._p:
            return True
        h = _k32.OpenFileMappingW(FILE_MAP_READ, False, self.nome)
        if not h:
            self.erro = ctypes.get_last_error()
            return False
        self.erro = 0
        p = _k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0)
        if not p:
            _k32.CloseHandle(h)
            return False
        mbi = _MBI()
        _k32.VirtualQuery(p, ctypes.byref(mbi), ctypes.sizeof(mbi))
        self._h, self._p, self._disp = h, p, int(mbi.RegionSize or 0)
        return True

    def ler(self):
        """Devolve uma cópia dos bytes da página (completa com zeros se for menor)."""
        if self.nome in SIMULADOS:
            dados = bytes(SIMULADOS[self.nome])
        elif self._p:
            n = min(self.tamanho, self._disp) if self._disp else self.tamanho
            dados = ctypes.string_at(self._p, n)
        else:
            return None
        if len(dados) < self.tamanho:
            dados = dados + bytes(self.tamanho - len(dados))
        return dados

    def ler_trecho(self, inicio, n):
        """Lê só um pedaço da página (para mapas grandes como o do iRacing)."""
        if self.nome in SIMULADOS:
            return bytes(SIMULADOS[self.nome][inicio:inicio + n]).ljust(n, b"\x00")
        if not self._p:
            return None
        if self._disp and inicio + n > self._disp:
            n = max(0, self._disp - inicio)
        return ctypes.string_at(self._p + inicio, n) if n else b""

    def fechar(self):
        if sys.platform == "win32" and self._p:
            _k32.UnmapViewOfFile(self._p)
            _k32.CloseHandle(self._h)
        self._h = self._p = None
        self._disp = 0
