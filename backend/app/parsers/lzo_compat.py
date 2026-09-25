"""LZO 解压垫片：用 ctypes 直接调系统 liblzo2，替代编译不可靠的 python-lzo。

背景：MDict 的 LZO 压缩块需要 `lzo.decompress(b"\\xf0" + 4字节大端原长 + 压缩数据)`
（readmdict.py 的调用约定），而 python-lzo 无预编译 wheel、源码编译在镜像里不可靠。
liblzo2-2 运行库极小且直接可用，这里实现 python-lzo 兼容的最小接口，在
app/parsers/mdict.py 导入时注入 `mdict_utils.base.readmdict.lzo`。

lzo1x_decompress_safe 的签名（liblzo2）：
    int lzo1x_decompress_safe(const lzo_byte *src, lzo_uint src_len,
                              lzo_byte *dst, lzo_uint *dst_len)
lzo_uint 与 size_t 同宽（amd64 上 8 字节）。
"""

import ctypes
import ctypes.util
import threading

_lib = None
_lock = threading.Lock()


def _load():
    global _lib
    if _lib is not None:
        return _lib
    with _lock:
        if _lib is not None:
            return _lib
        candidates = ["liblzo2.so.2", ctypes.util.find_library("lzo2")]
        last_error = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                lib = ctypes.CDLL(candidate)
                break
            except OSError as exc:
                last_error = exc
        else:
            raise RuntimeError(
                f"无法加载 liblzo2（LZO 压缩支持不可用）: {last_error}"
            )
        lib.lzo1x_decompress_safe.restype = ctypes.c_int
        lib.lzo1x_decompress_safe.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        _lib = lib
        return _lib


def decompress(data: bytes) -> bytes:
    """python-lzo 兼容的解压入口：`\\xf0` + 4 字节大端解压后长度 + lzo1x 数据。"""
    if len(data) < 5 or data[0] != 0xF0:
        raise ValueError("不是 python-lzo 带长度头的 LZO1X 数据")
    expected = int.from_bytes(data[1:5], "big")
    src = bytes(data[5:])
    lib = _load()
    dst = ctypes.create_string_buffer(expected + 64)
    # dst_len 是 in/out：入参为缓冲区容量，出参为实际解压长度
    dst_len = ctypes.c_size_t(expected + 64)
    rc = lib.lzo1x_decompress_safe(src, len(src), dst, ctypes.byref(dst_len))
    if rc != 0:  # LZO_E_OK == 0
        raise ValueError(f"liblzo2 解压失败: LZO 错误码 {rc}")
    out = dst.raw[: dst_len.value]
    if dst_len.value != expected:
        raise ValueError(
            f"LZO 解压长度不符：预期 {expected}，实际 {dst_len.value}"
        )
    return out
