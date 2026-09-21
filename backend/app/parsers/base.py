import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# 释义可能是 HTML（MDict 的释义整段是 HTML），标签名与属性名全是拉丁字母。
# 「判断这段文字用什么语言写」「这段是不是根本没有正文」之前都必须先把标签剥掉。
TAG_RE = re.compile(r"<[^>]+>")

# 字符实体同样要剥掉：`&nbsp;` 会被当成 4 个拉丁字母算进占比，中文释义里密集出现的
# 话足以把语言判断从 zh 拉向 en。
_ENTITY_RE = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,7}|#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6});")

# 释义剥掉标签与实体后少于这个字符数就认为「没有正文」——扫描版词典（整页是 <img>）
# 属于这类，拿它们去判语言只会得到噪声。阈值取 2 而不是更大：真实词典里
# `n. 苹果` 这种极短释义是合法内容，不能误伤。
_MIN_DEFINITION_CHARS = 2

# 词头里至少要有一个「有意义的文字字符」：字母、汉字（含扩展区）或假名。
# 纯数字/符号的词条（`0`、`110`、`---`）是索引项，不代表词典正文用什么语言写。
# 汉典的前若干条正是 `0`、`110`、`120` 这种，只看开头就会把整部中文词典判成 en。
_MEANINGFUL_CHAR_RE = re.compile(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")


def strip_markup(text: str | None) -> str:
    """去掉 HTML 标签与字符实体，只留下真正的文字。"""
    if not text:
        return ""
    return _ENTITY_RE.sub(" ", TAG_RE.sub(" ", text))


# 采样释义时最多扫过的条数 = limit * 本系数。开头可能全是索引项或整页扫描图（全被判为
# 无信息量），所以要多扫一些；但不能无限扫，否则采样就成了整部词典的解析。
SAMPLE_SCAN_FACTOR = 25


@dataclass(slots=True)
class ParsedEntry:
    """统一词条结构，跨格式解析器共用。"""

    word: str
    definition: str
    phonetic: str | None = None
    extra: dict | None = None


def is_informative_headword(word: str) -> bool:
    """词头是否含「有意义的文字字符」（字母/汉字/假名）。

    纯数字与纯符号的词条是索引项（`0`、`110`、`---`），按字符脚本占比判断时它们既不
    贡献拉丁字母也不贡献汉字，留着只会稀释样本。
    """
    return bool(_MEANINGFUL_CHAR_RE.search(word or ""))


def is_informative(word: str, definition: str | None) -> bool:
    """这条词条是否适合用来判断词典的语言方向。

    采样只取「开头若干条」时，开头往往是索引页、数字条目或整页扫描图，据此判断会判错；
    这里把这类无信息量的样本剔掉，剩下的才参与判定。
    """
    if not is_informative_headword(word):
        return False
    return len(strip_markup(definition).strip()) >= _MIN_DEFINITION_CHARS


def spread_downsample(candidates: list[str], limit: int) -> list[str]:
    """把「已按跨度遍历整份词典收集到的候选」再均匀降到 limit 个。

    为什么不能「收满 limit 就停」：那样收集到的是遍历顺序里最靠前的那批，等于又退回
    「只取开头」。必须先跨完整份收集、再统一下采样，才真的覆盖词典全段。
    """
    if len(candidates) <= limit:
        return candidates
    step = max(1, len(candidates) // limit)
    return candidates[::step][:limit]


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

        resource_dir 为 None 表示不要资源：不落盘，也不改写 definition 里的资源引用。
        """
        raise NotImplementedError

    @abstractmethod
    def sample(self, file_paths: list[Path], limit: int) -> list[ParsedEntry]:
        """只读采样至多 limit 条**有信息量**的词条，供语言识别使用。

        与 parse() 的关键差别是绝不写盘：不落 .mdd 资源、不改写释义里的资源引用、
        不创建任何目录；且读取量有上界，不会为了采样把整份大词典读进内存。

        只返回 is_informative() 为真的词条，并另有一个扫描条数上限，避免开头全是
        索引项/扫描图时把整部词典扫一遍。
        """
        raise NotImplementedError

    @abstractmethod
    def sample_headwords(self, file_paths: list[Path], limit: int) -> list[str]:
        """跨**整部**词典均匀取至多 limit 个词头。

        为什么要跨整部而不是取开头：词典开头常是索引、数字条目、拼音索引
        （`0`、`110`、`a1`），据此判断语言方向会得到 en 这种错得离谱的结果——
        而语言方向是查询路由的依据，判错会让这部词典的几十万条内容永远查不到。

        实现必须做到「不必顺序读完整个词条流」：MDict 直接用初始化时已建好的内存
        词头表索引，StarDict/ECDICT 按字节偏移 seek。
        """
        raise NotImplementedError
