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
        resource_dir: Path | None,
    ) -> Iterator[ParsedEntry]:
        """流式解析词典文件，逐条 yield ParsedEntry。

        若词典包含图片/音频资源（如 MDict 的 .mdd），解析器负责把资源落盘到
        resource_dir，并将 definition 中的资源引用改写为
        /dict-res/{dictionary_id}/res/... 绝对路径。

        resource_dir 为 None 表示只需释义、不要资源：此时不落盘任何资源，也不改写
        definition 里的资源引用（改了也只会指向不存在的文件）。
        """
        raise NotImplementedError

    @abstractmethod
    def sample(self, file_paths: list[Path], limit: int) -> list[ParsedEntry]:
        """只读采样至多 limit 条词条，供语言识别等只需少量样本的判断使用。

        与 parse() 的关键差别是绝不写盘：不落 .mdd 资源、不改写释义里的资源引用、
        不创建任何目录；且读取量有上界，不会为了采样把整份大词典读进内存。
        """
        raise NotImplementedError
