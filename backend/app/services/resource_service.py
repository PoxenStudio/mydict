import logging
import os
import re
import shutil
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("mydict.resource")

# 词条文档（含它引用的 CSS）可能用到的资源类型。带点的全小写形式，上传白名单也复用它。
#
# 刻意不含 Eudic 专有索引（.db / .db-wal / .bix / .bin）与 .pdf：实测词典目录里这类文件
# 占了附属文件总大小的六成（102MB / 176MB），却与 HTML 渲染毫无关系。
SIBLING_RESOURCE_EXTENSIONS = frozenset(
    {
        ".css",
        ".js",
        ".mjs",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".avif",
        ".bmp",
        ".ico",
        ".cur",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".mp3",
        ".wav",
        ".ogg",
        ".oga",
        ".opus",
        ".m4a",
        ".aac",
        ".flac",
        ".spx",
        ".mp4",
        ".webm",
        ".html",
        ".htm",
        ".txt",
        ".json",
        ".xml",
    }
)

# /dict-res 响应的 Content-Type。不交给 mimetypes 猜：容器里常常没有 /etc/mime.types，
# 内置表不认 .woff2/.otf/.ogg/.webp/.spx 等，Starlette 会退成 text/plain；而响应带了
# nosniff，Chrome 的 ORB 会拦掉 <img>/<audio> 拿到的 text/plain，资源就静默失效了。
_RESOURCE_MEDIA_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".cur": "image/x-icon",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".spx": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".json": "application/json",
    ".xml": "text/xml",
}


def resource_media_type(path: Path) -> str:
    """词典资源的 Content-Type；不认识的一律 application/octet-stream，交给浏览器按内容识别。

    .mdd 里常有无扩展名或扩展名写错的图片，octet-stream 能被 ORB 按内容嗅探放行，
    text/plain 则会被直接拦掉。
    """
    return _RESOURCE_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


# 匹配 HTML 中 src="..." / href="..." 属性值。
# 负向前瞻一口气跳过所有「不该改写」的引用，避免每条外部链接都要进一次 Python 回调——
# 释义里绝大多数资源引用都是 http(s)/data:，这个跳过是热路径上的主要优化。
#   entry://  MDict 的词条内跳转协议，指向另一条词条而不是文件，交给前端点击时拦截
#   #       页内锚点
#   //      、www. 协议相对/裸域名的外链
#   javascript: / file: 一律原样保留（前端会拦截点击，绝不把它改成可执行的样子）
_RESOURCE_REF_RE = re.compile(
    r"""(?P<attr>\b(?:src|href)\s*=\s*)(?P<quote>['"])(?P<path>[^'"]+)(?P=quote)""",
    re.IGNORECASE,
)

# 这些前缀开头的引用原样保留。放在 lookahead 里比在回调里判断更快。
_SKIP_PREFIX_RE = re.compile(
    r"^(?:https?://|data:|entry://|#|//|www\.|mailto:|javascript:|ftp://|blob:|tel:)",
    re.IGNORECASE,
)

# sound:// 是 MDict 的音频引用协议，指向 .mdd 里解包出来的音频文件，需要改写成可播放的 URL。
_SOUND_PREFIX_RE = re.compile(r"^sound://", re.IGNORECASE)

# file:///… 是 MDict 里「词典资源根目录」的写法，与 sound:// 同类，也要转成可访问的 URL。
#
# 必须放在下面的通用 scheme 判断**之前**：否则会被当成「未知协议」原样留下，而浏览器加载
# `file:///down/7/x.gif` 只会失败。`file:` 后面跟两个还是三个斜杠、用正斜杠还是反斜杠都有
# 实例（实测朗文 LDOCE5 是 `file://media/...`、汉典是 `file:///down/...`），一律吃掉。
#
# 指到词典外部的写法（`file:///etc/passwd`）会被改写成 /dict-res/{id}/res/etc/passwd ——
# 那是个 404，但原本的 `file://` 在浏览器里同样打不开，不存在「改坏了」。
_FILE_PREFIX_RE = re.compile(r"^file:[\\/]+", re.IGNORECASE)

# 「带 scheme」的通用判据：字母开头 + 若干合法字符 + 冒号。
# 放在 sound:// 之后判断，用来把其它未知协议（ws://、自定义协议等）保守地原样留下。
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def normalize_resource_path(raw_path: str) -> str:
    """把词典内部的资源相对路径规范化为正斜杠、去掉开头分隔符，拒绝路径穿越。"""
    path = raw_path.replace("\\", "/").lstrip("/")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"resource path traversal rejected: {raw_path!r}")
    return "/".join(parts)


def write_resource(
    resource_dir: Path, relative_path: str, content: bytes, *, overwrite: bool = True
) -> None:
    """将资源内容写入 resource_dir/relative_path，自动创建父目录。

    overwrite=False 用于给**正在服务**的词典补文件：已存在的跳过，新文件走「临时文件 +
    os.replace」，不让并发请求读到半截内容。
    """
    normalized = normalize_resource_path(relative_path)
    target = resource_dir / normalized
    if not overwrite and target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        target.write_bytes(content)
        return
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _source_dirs(sources: Iterable[Path]) -> list[Path]:
    """把「词典相关路径」统一成要扫描的目录列表。

    传进来的既可能是文件（dicts_dir 导入存的是 .mdx/.mdd 的完整路径），
    也可能是目录（浏览器上传导入存的是该词典的 source/ 目录），两种都要能处理。
    """
    dirs: list[Path] = []
    for source in sources:
        directory = source if source.is_dir() else source.parent
        if directory not in dirs:
            dirs.append(directory)
    return dirs


# 超过这个条目数就不建索引。实测会用到这里的两部词典（汉典 19499、新漢語林2 1890）都远
# 在范围内；The little dict 的 res/ 顶层有 67.6 万个文件，建索引要几十 MB，不能让它得逞。
# 超限时返回空索引且**结果照样被 lru_cache 记住**，所以代价只在第一次付出。
_MAX_INDEXED_NAMES = 30_000


@lru_cache(maxsize=16)
def _directory_index(directory: str) -> dict[str, str]:
    """目录项「小写名 → 真实名」，供大小写不敏感兜底查找用。

    实测 19499 个文件的目录建一次索引约 4ms、约 300KB，所以缓存 16 个目录封顶几 MB；
    只在精确路径不存在时才会被用到。目录内容后续只增不减（比如按需转码新落盘的 mp3），
    而精确匹配始终先走文件系统，所以缓存过期不会影响正确性。
    """
    index: dict[str, str] = {}
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(index) >= _MAX_INDEXED_NAMES:
                    return {}
                index[entry.name.lower()] = entry.name
    except OSError:
        return {}
    return index


def _match_case_insensitively(root: Path, relative: str) -> Path | None:
    """在 root 下逐段按大小写不敏感查找 relative；找到文件才返回。"""
    current = root
    for part in relative.split("/"):
        candidate = current / part
        if candidate.exists():
            current = candidate
            continue
        real = _directory_index(str(current)).get(part.lower())
        if real is None:
            return None
        current = current / real
    return current if current.is_file() else None


def strip_legacy_file_prefix(relative: str) -> str:
    """去掉历史坏链接里多出来的一截 `file:/` 前缀。

    早期改写把 `file:///down/x.gif` 拼成了 `/dict-res/7/res/file:/down/x.gif`，于是请求
    路径里成了 `file:/down/x.gif`。新导入的词典不会再产生这种值（`_FILE_PREFIX_RE` 已经
    接管改写），但已入库的行需要兼容——`definition_repair` 能就地清掉它们，跑之前和
    没跑的部署都靠这里兜住。
    """
    return _FILE_PREFIX_RE.sub("", relative)


def resolve_resource_file(res_dir: Path, relative: str) -> Path | None:
    """把资源相对路径解析成 `res/` 下的真实文件，解析不到返回 None。

    调用方需先用 `normalize_resource_path` 做过路径穿越校验、并用
    `strip_legacy_file_prefix` 去掉历史坏链接的前缀。

    这里多做一件事：**大小写不敏感兜底**。词典大多在 Windows 上打包，词条引用常与 `.mdd`
    里的键大小写不一致——实测汉典的图片引用**全部**是小写、实际键却是混合大小写
    （引用 `down/30/305626w1b7f8b.gif`、实际 `305626w1b7F8B.gif`，`down/0` 一个目录里就有
    一万九千个这种文件），新漢語林2 的外字引用则相反（引用 `gaiji/B245.png`、实际小写）。
    Windows 与 MDict 客户端都不区分大小写，Linux 上就是 404。逐段解析，每段仍优先精确匹配。
    """
    if not relative:
        return None
    target = res_dir / relative
    if target.is_file():
        return target
    return _match_case_insensitively(res_dir, relative)


def copy_sibling_resources(resource_dir: Path, sources: Iterable[Path]) -> int:
    """把词典文件旁边的附属资源复制进 `resource_dir`，返回成功复制的文件数。

    MDict 的惯例是把样式表、字体、脚本、图片放在 `.mdx` **同级目录**：词条里的
    `<link href="oxbw.css">` 与 CSS 里的 `url("SourceHanSerifJP-Regular.otf")` 都按
    「词典文件所在目录」解析——MDict 客户端就是这么做的。这些文件并不在 `.mdd` 里
    （实测大辞泉的 `oxbw.css`/`oxbw.js`、岩波的 `iwakoku.css`、広辞苑的 `gcy.css` 与 6 个
    `.otf`、明镜的 `MK3.css`、新世纪的 `xinrihanshuangjie.css`、Weblio 的 `thesaurus.css`
    都是如此，Weblio 甚至没有 `.mdd`），所以只解包 `.mdd` 会让它们全部 404——词条于是以
    无样式渲染，图标回到原始像素（`Audio.png` 75×74、`b276.png` 387×150）、表格丢掉边框。

    只扫一层目录、只复制扩展名在白名单里的**直接子文件**。

    已存在的同名文件不覆盖：`.mdd` 里解包出来的那份属于词典容器内，更权威。
    写入走「临时文件 + os.replace」原子替换——补齐存量词典时词典是启用状态、可能正有人
    在查，直接写会让请求读到半截 CSS。
    """
    count = 0
    for directory in _source_dirs(sources):
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            logger.warning("无法读取词典目录 %s，跳过附属资源复制", directory, exc_info=True)
            continue

        for child in children:
            # 词典本体（.mdx/.mdd）不在白名单里，自然不会被复制
            if child.suffix.lower() not in SIBLING_RESOURCE_EXTENSIONS:
                continue
            # 符号链接可能指向词典目录之外，不跟着走
            if child.is_symlink() or not child.is_file():
                continue

            target = resource_dir / child.name
            if target.exists():
                continue
            temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
            try:
                resource_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, temporary)
                os.replace(temporary, target)
            except OSError:
                # 单个文件失败不该连累整次导入，也不留临时文件
                logger.warning("复制附属资源失败 %s", child, exc_info=True)
                temporary.unlink(missing_ok=True)
                continue
            count += 1
    return count


def _split_suffix(raw: str) -> tuple[str, str]:
    """把 ?query 与 #fragment 从路径里拆出来，返回 (路径, 后缀)。"""
    path, sep, fragment = raw.partition("#")
    path, qsep, query = path.partition("?")
    suffix = ""
    if qsep:
        suffix = "?" + query
    if sep:
        suffix += "#" + fragment
    return path, suffix


def _to_resource_url(raw: str, dictionary_id: int) -> str | None:
    """把资源相对路径拼成 /dict-res/ 绝对 URL；无法规范化（越权等）时返回 None。"""
    path, suffix = _split_suffix(raw)
    try:
        normalized = normalize_resource_path(path)
    except ValueError:
        return None
    if not normalized:
        return None
    return f"/dict-res/{dictionary_id}/res/{normalized}{suffix}"


def _rewrite_value(raw: str, dictionary_id: int) -> str:
    """单条属性值的改写规则；返回原值时表示「不改写」。"""
    # file:///down/x.gif 指的是词典资源根目录下的 down/x.gif（实测汉典、千篇汉语词典、
    # 说文解字段注、大辭海、朗文 LDOCE5、新世纪日汉双解等 7 部词典在用），与 sound:// 同类
    if _FILE_PREFIX_RE.match(raw):
        return _to_resource_url(_FILE_PREFIX_RE.sub("", raw), dictionary_id) or raw

    if _SKIP_PREFIX_RE.match(raw):
        return raw

    # sound://audio/x.spx -> /dict-res/{id}/res/audio/x.spx，前端据此播放
    if _SOUND_PREFIX_RE.match(raw):
        return _to_resource_url(_SOUND_PREFIX_RE.sub("", raw), dictionary_id) or raw

    # 其余任何带 scheme 的引用都不属于「词典内部资源」，保守留下
    if _SCHEME_RE.match(raw):
        return raw

    # 无扩展名的裸相对路径在 MDX 里基本都是词条链接（entry:// 的简写），
    # 补成 /dict-res/ 只会得到一个 404 —— 这里不动它。
    head = raw.split("#", 1)[0].split("?", 1)[0]
    if "." not in head.rsplit("/", 1)[-1]:
        return raw

    return _to_resource_url(raw, dictionary_id) or raw


def rewrite_resource_refs(html: str, dictionary_id: int) -> str:
    """把释义 HTML 中的相对资源引用改写为 /dict-res/{dictionary_id}/res/... 绝对 URL。

    entry:// 词条链接与外部链接原样保留：前者由前端点击时拦截并发起新查询，
    后者本就该指向站外；`sound://` 与 `file:///` 都是指向词典内部资源，一并改写。
    """

    def _replace(match: re.Match[str]) -> str:
        value = match.group("path")
        rewritten = _rewrite_value(value, dictionary_id)
        if rewritten == value:
            return match.group(0)
        quote = match.group("quote")
        return f"{match.group('attr')}{quote}{rewritten}{quote}"

    return _RESOURCE_REF_RE.sub(_replace, html)
