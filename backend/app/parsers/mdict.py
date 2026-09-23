from collections.abc import Iterator
from pathlib import Path

from mdict_utils.base.readmdict import MDD, MDX

from app.parsers.base import (
    SAMPLE_SCAN_FACTOR,
    DictionaryParser,
    ParsedEntry,
    is_informative,
    is_informative_headword,
    spread_downsample,
)
from app.services.resource_service import (
    copy_sibling_resources,
    rewrite_resource_refs,
    write_resource,
)


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
            # 样式表/字体/脚本不在 .mdd 里，而是躺在 .mdx 同级目录；见
            # copy_sibling_resources 的说明
            copy_sibling_resources(resource_dir, file_paths)

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
        """只迭代到够 limit 条「有信息量」的词条为止。

        刻意不加载 .mdd：parse() 会把 .mdd 里的图片/音频全量落盘，采样只是判断语言，
        不能有这个副作用；释义也保持原始 HTML，不做资源引用改写。
        """
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        sampled: list[ParsedEntry] = []
        scanned = 0
        scan_cap = limit * SAMPLE_SCAN_FACTOR
        for mdx_path in mdx_paths:
            mdx = self._open_mdx(mdx_path)
            for key, value in mdx.items():
                scanned += 1
                if scanned > scan_cap:
                    return sampled
                word = key.decode("utf-8", errors="replace")
                definition = value.decode("utf-8", errors="replace")
                # 扫描版词典整条释义就是一个 <img>，拿它判不出语言；索引项（纯数字词头）
                # 同理。跳过它们继续往后找真正的正文。
                if not is_informative(word, definition):
                    continue
                sampled.append(ParsedEntry(word=word, definition=definition))
                if len(sampled) >= limit:
                    return sampled
        return sampled

    def sample_headwords(self, file_paths: list[Path], limit: int) -> list[str]:
        """跨整部词典均匀取词头。

        `mdict_utils` 在 `MDX.__init__` 里就把整个词头表读进内存了（`_key_list`，
        元素是 `(record_offset, utf-8 字节)`），所以按下标取值是纯内存操作，
        不必为采样顺序解压几十万条记录——这正是能取「中段」而不是只能取「开头」的原因。
        """
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        words: list[str] = []
        for mdx_path in mdx_paths:
            mdx = self._open_mdx(mdx_path)
            key_list = getattr(mdx, "_key_list", None)
            if key_list:
                total = len(key_list)
                # 跨度按 2 倍目标取（词头里难免混着纯数字/符号的索引项），并且**跑完整段**
                # 再统一下采样——中途收满就停会退回「只取开头」。
                step = max(1, total // (limit * 2))
                collected: list[str] = []
                for index in range(0, total, step):
                    word = key_list[index][1].decode("utf-8", errors="replace")
                    if is_informative_headword(word):
                        collected.append(word)
                return spread_downsample(collected, limit)
            # 上游换成惰性词头表时的退路：只能顺序取开头
            for key in mdx.keys():
                word = key.decode("utf-8", errors="replace")
                if not is_informative_headword(word):
                    continue
                words.append(word)
                if len(words) >= limit:
                    return words[:limit]
        return words[:limit]
