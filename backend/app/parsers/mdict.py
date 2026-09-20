from collections.abc import Iterator
from pathlib import Path

from mdict_utils.base.readmdict import MDD, MDX

from app.parsers.base import DictionaryParser, ParsedEntry
from app.services.resource_service import rewrite_resource_refs, write_resource


def _open_mdict(factory, path: Path):
    """打开 MDict 文件；LZO 压缩块（未装 python-lzo）的 RuntimeError 转成可读的 ValueError。"""
    try:
        return factory(str(path))
    except RuntimeError as exc:
        if "LZO" in str(exc):
            raise ValueError(
                f"{path.name} 使用了 LZO 压缩（MDict 引擎版本低于 2.0），当前构建未启用 LZO 支持"
            ) from exc
        raise


class MDictParser(DictionaryParser):
    def __init__(self) -> None:
        # 大 MDX 打开时要加载整份词头索引，采样与解析共用同一次打开
        self._mdx_cache: dict[Path, object] = {}

    def _open_mdx(self, path: Path):
        if path not in self._mdx_cache:
            self._mdx_cache[path] = _open_mdict(MDX, path)
        return self._mdx_cache[path]

    def parse(
        self,
        file_paths: list[Path],
        *,
        dictionary_id: int,
        resource_dir: Path | None,
    ) -> Iterator[ParsedEntry]:
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        mdd_paths = [p for p in file_paths if p.suffix.lower() == ".mdd"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        # resource_dir 为 None：不落盘 .mdd 资源，也不改写释义里的资源引用
        if resource_dir is not None:
            for mdd_path in mdd_paths:
                mdd = _open_mdict(MDD, mdd_path)
                for key, content in mdd.items():
                    relative_path = key.decode("utf-8", errors="replace")
                    write_resource(resource_dir, relative_path, content)

        for mdx_path in mdx_paths:
            mdx = self._open_mdx(mdx_path)
            for key, value in mdx.items():
                word = key.decode("utf-8", errors="replace")
                html = value.decode("utf-8", errors="replace")
                definition = (
                    rewrite_resource_refs(html, dictionary_id) if resource_dir is not None else html
                )
                yield ParsedEntry(word=word, definition=definition)

    def sample(self, file_paths: list[Path], limit: int) -> list[ParsedEntry]:
        """只迭代前 limit 条即停；不加载 .mdd，释义保持原始 HTML。"""
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        sampled: list[ParsedEntry] = []
        for mdx_path in mdx_paths:
            mdx = self._open_mdx(mdx_path)
            for key, value in mdx.items():
                sampled.append(
                    ParsedEntry(
                        word=key.decode("utf-8", errors="replace"),
                        definition=value.decode("utf-8", errors="replace"),
                    )
                )
                if len(sampled) >= limit:
                    return sampled
        return sampled
