from collections.abc import Iterator
from pathlib import Path

from mdict_utils.base.readmdict import MDD, MDX

from app.parsers.base import DictionaryParser, ParsedEntry
from app.services.resource_service import rewrite_resource_refs, write_resource


class MDictParser(DictionaryParser):
    def parse(
        self,
        file_paths: list[Path],
        *,
        dictionary_id: int,
        resource_dir: Path,
    ) -> Iterator[ParsedEntry]:
        mdx_paths = [p for p in file_paths if p.suffix.lower() == ".mdx"]
        mdd_paths = [p for p in file_paths if p.suffix.lower() == ".mdd"]
        if not mdx_paths:
            raise ValueError("MDict 词典缺少 .mdx 文件")

        # 先落盘 .mdd 资源，供随后改写的 definition HTML 引用。
        for mdd_path in mdd_paths:
            mdd = MDD(str(mdd_path))
            for key, content in mdd.items():
                relative_path = key.decode("utf-8", errors="replace")
                write_resource(resource_dir, relative_path, content)

        for mdx_path in mdx_paths:
            mdx = MDX(str(mdx_path))
            for key, value in mdx.items():
                word = key.decode("utf-8", errors="replace")
                html = value.decode("utf-8", errors="replace")
                definition = rewrite_resource_refs(html, dictionary_id)
                yield ParsedEntry(word=word, definition=definition)
