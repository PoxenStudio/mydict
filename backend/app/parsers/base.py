from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ParsedEntry:
    """统一词条结构，跨格式解析器共用。"""

    word: str
    definition: str
    phonetic: str | None = None
    extra: dict | None = None


class DictionaryParser(ABC):
    """三种词典格式解析器的统一接口。"""

    @abstractmethod
    def parse(
        self,
        file_paths: list[Path],
        *,
        dictionary_id: int,
        resource_dir: Path,
    ) -> Iterator[ParsedEntry]:
        """流式解析词典文件，逐条 yield ParsedEntry。

        若词典包含图片/音频资源（如 MDict 的 .mdd），解析器负责把资源落盘到
        resource_dir，并将 definition 中的资源引用改写为
        /dict-res/{dictionary_id}/res/... 绝对路径。
        """
        raise NotImplementedError
