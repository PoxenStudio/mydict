from collections.abc import Iterator
from pathlib import Path

from mdict_utils.base.readmdict import MDD, MDX

from app.parsers.base import DictionaryParser, ParsedEntry
from app.services.resource_service import rewrite_resource_refs, write_resource


def _open_mdict(factory, path: Path):
    """打开 MDict 文件，把「当前构建不支持」转成可读的校验错误。

    mdict-utils 只有在额外装了可选的 python-lzo 时才支持 LZO 压缩块，否则对引擎版本 <2.0 的
    老词典抛 RuntimeError("LZO compression is not supported")。裸抛出去会被后台任务的兜底
    分支变成「服务器内部错误，请查看后端日志」，管理员看不出是格式问题；转成 ValueError 后
    走既有的解析校验错误通道，前端直接显示原因。
    """
    try:
        return factory(str(path))
    except RuntimeError as exc:
        if "LZO" in str(exc):
            raise ValueError(
                f"{path.name} 使用了 LZO 压缩（MDict 引擎版本低于 2.0），当前构建未启用 LZO 支持"
            ) from exc
        raise


class MDictParser(DictionaryParser):
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

        # resource_dir 为 None 表示只要释义、不要发音/图片（大词典的 .mdd 常有几个 GB，
        # 解包一份等于再占一份磁盘）。这时既不落盘资源，也不改写释义里的资源引用——
        # 改写只会指向 /dict-res/ 下不存在的文件，保留原始相对引用更诚实。
        if resource_dir is not None:
            # 先落盘 .mdd 资源，供随后改写的 definition HTML 引用。
            for mdd_path in mdd_paths:
                mdd = _open_mdict(MDD, mdd_path)
                for key, content in mdd.items():
                    relative_path = key.decode("utf-8", errors="replace")
                    write_resource(resource_dir, relative_path, content)

        for mdx_path in mdx_paths:
            mdx = _open_mdict(MDX, mdx_path)
            for key, value in mdx.items():
                word = key.decode("utf-8", errors="replace")
                html = value.decode("utf-8", errors="replace")
                definition = (
                    rewrite_resource_refs(html, dictionary_id) if resource_dir is not None else html
                )
                yield ParsedEntry(word=word, definition=definition)

    def sample(self, file_paths: list[Path], limit: int) -> list[ParsedEntry]:
        """只迭代前 limit 条即停。

        刻意不加载 .mdd：parse() 会把 .mdd 里的图片/音频全量落盘，采样只是判断语言，
        不能有这个副作用；释义也保持原始 HTML，不做资源引用改写。
        """
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        sampled: list[ParsedEntry] = []
        for mdx_path in mdx_paths:
            mdx = _open_mdict(MDX, mdx_path)
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
