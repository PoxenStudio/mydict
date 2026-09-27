"""LZO 解压垫片（ctypes 直调 liblzo2）的用例。

解压类用例依赖系统库 liblzo2（镜像里装了 liblzo2-2），本机没有时跳过；格式校验不碰库，
任何环境都跑。样本来自 liblzo2 的 lzo1x_1_compress，带回溯引用，不只是字面量。
"""

import pytest

from app.parsers import lzo_compat

_TEXT = ("词典 LZO 压缩块 " * 50).encode()
_PAYLOAD = bytes.fromhex(
    "0003e8af8de585b8204c5a4f20e58e8be7bca9e59d972020000000d650000e85b8204c5a4f20e58e8be7bca9"
    "e59d9720110000"
)


def _framed(payload: bytes, length: int) -> bytes:
    return b"\xf0" + length.to_bytes(4, "big") + payload


@pytest.fixture
def liblzo2() -> None:
    try:
        lzo_compat._load()
    except RuntimeError:
        pytest.skip("本机没有 liblzo2")


def test_decompress_round_trips_real_lzo1x_block(liblzo2) -> None:
    assert lzo_compat.decompress(_framed(_PAYLOAD, len(_TEXT))) == _TEXT


def test_decompress_literal_only_block(liblzo2) -> None:
    # 17+5 表示 5 个字面字节，0x11 0x00 0x00 为结束标记
    assert lzo_compat.decompress(_framed(b"\x16hello\x11\x00\x00", 5)) == b"hello"


def test_decompress_rejects_length_mismatch(liblzo2) -> None:
    with pytest.raises(ValueError, match="长度不符"):
        lzo_compat.decompress(_framed(_PAYLOAD, len(_TEXT) + 1))


def test_decompress_rejects_corrupted_block(liblzo2) -> None:
    with pytest.raises(ValueError, match="LZO 错误码"):
        lzo_compat.decompress(_framed(_PAYLOAD[:20], len(_TEXT)))


@pytest.mark.parametrize("data", [b"", b"\xf0\x00", b"\x00" + (5).to_bytes(4, "big") + b"x"])
def test_decompress_rejects_missing_length_header(data: bytes) -> None:
    with pytest.raises(ValueError, match="长度头"):
        lzo_compat.decompress(data)
