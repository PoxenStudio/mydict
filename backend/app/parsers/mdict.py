from collections.abc import Iterator
from pathlib import Path

from mdict_utils.base import readmdict as _readmdict
from mdict_utils.base.readmdict import MDD, MDX

# LZO 压缩支持：readmdict 的 LZO 分支代码是现成的，只是缺 python-lzo（无预编译
# wheel、编译不可靠）。这里注入 ctypes 版垫片（直调 liblzo2），使 6 部 LZO 词典
# （读懂你的化验单、超级新华字典等）可以正常导入。若镜像里真装了 python-lzo，
# 则保留原实现不动。
if getattr(_readmdict, "lzo", None) is None:
    from app.parsers import lzo_compat

    _readmdict.lzo = lzo_compat

from app.parsers.base import (
    SAMPLE_SCAN_FACTOR,
    DictionaryParser,
    ParsedEntry,
    is_informative,
    is_informative_headword,
    spread_downsample,
)
from app.parsers.mdict_stylesheet import expand_style_markers, is_compact, stylesheet_of
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


def read_stylesheet(path: Path) -> dict[str, tuple[str, str]]:
    """打开 `.mdx` 读它的 `StyleSheet` 字段，供「从源文件修复」展开存量词条用。

    注意代价：`MDX.__init__` 会把**整份词头索引**读进内存（实测 The little dict 8.7 秒、
    搜韵诗词 17.6 秒），所以调用方必须先确认这部词典真的需要展开，不能每部都调。
    需要连 Compact 标志一起拿时用 `read_style_context`。
    """
    return stylesheet_of(_open_mdict(MDX, path))


def read_style_context(path: Path) -> tuple[dict[str, tuple[str, str]], bool]:
    """样式表 + Compact 标志一起取（同一次打开，省一遍整份词头索引的加载）。"""
    mdx = _open_mdict(MDX, path)
    return stylesheet_of(mdx), is_compact(mdx)


class MDictParser(DictionaryParser):
    def __init__(self) -> None:
        # 大 MDX 打开时要加载整份词头索引，采样与解析共用同一次打开
        self._mdx_cache: dict[Path, object] = {}
        # 每份 .mdx 的样式表只解析一次；Compact 标志与样式表同源，一起缓存
        self._stylesheet_cache: dict[Path, tuple[dict[str, tuple[str, str]], bool]] = {}

    def _open_mdx(self, path: Path):
        if path not in self._mdx_cache:
            self._mdx_cache[path] = _open_mdict(MDX, path)
        return self._mdx_cache[path]

    def _style_context_for(self, mdx_path: Path) -> tuple[dict[str, tuple[str, str]], bool]:
        if mdx_path not in self._stylesheet_cache:
            mdx = self._open_mdx(mdx_path)
            self._stylesheet_cache[mdx_path] = (stylesheet_of(mdx), is_compact(mdx))
        return self._stylesheet_cache[mdx_path]

    def parse(
        self,
        file_paths: list[Path],
        *,
        dictionary_id: int,
        resource_dir: Path | None,
        overwrite_resources: bool = True,
    ) -> Iterator[ParsedEntry]:
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        mdd_paths = [p for p in file_paths if p.suffix.lower() == ".mdd"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        # resource_dir 为 None：不落盘 .mdd 资源，也不改写释义里的资源引用
        # （样式标记仍然照常展开 —— 那是文字排版，与「不导入发音/图片」无关）
        if resource_dir is not None:
            for mdd_path in mdd_paths:
                mdd = _open_mdict(MDD, mdd_path)
                for key, content in mdd.items():
                    relative_path = key.decode("utf-8", errors="replace")
                    write_resource(
                        resource_dir, relative_path, content, overwrite=overwrite_resources
                    )
            # 样式表/字体/脚本不在 .mdd 里，而是躺在 .mdx 同级目录；见
            # copy_sibling_resources 的说明
            copy_sibling_resources(resource_dir, file_paths)

        for mdx_path in mdx_paths:
            mdx = self._open_mdx(mdx_path)
            sheet, compact = self._style_context_for(mdx_path)
            for key, value in mdx.items():
                word = key.decode("utf-8", errors="replace")
                html = value.decode("utf-8", errors="replace")
                # 先展开 `` `编号` `` 样式标记、再改写资源引用：样式表的标签里本身可能
                # 含 src/href（如 <img src=...>），这个顺序才能让它们一并被改写
                definition = expand_style_markers(html, sheet, compact=compact)
                if resource_dir is not None:
                    definition = rewrite_resource_refs(definition, dictionary_id)
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
