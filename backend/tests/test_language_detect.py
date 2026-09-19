from app.parsers.base import ParsedEntry
from app.services.language_detect import detect_language


def _sample(pairs: list[tuple[str, str]], repeat: int = 60) -> list[ParsedEntry]:
    """把少量真实词条重复成足够大的样本：识别只看字符构成，重复不改变结论。"""
    return [
        ParsedEntry(word=word, definition=definition)
        for _ in range(repeat)
        for word, definition in pairs
    ]


def test_detect_english_to_chinese() -> None:
    entries = _sample(
        [
            ("apple", "苹果，一种水果"),
            ("apricot", "杏子，蔷薇科植物的果实"),
            ("banana", "香蕉，热带水果"),
            ("computer", "计算机，电子计算设备"),
        ]
    )
    assert detect_language(entries) == ("en", "zh-Hans")


def test_detect_chinese_to_english() -> None:
    entries = _sample(
        [
            ("苹果", "apple, a round fruit"),
            ("杏子", "apricot, a small orange fruit"),
            ("香蕉", "banana, a long curved fruit"),
            ("计算机", "computer, an electronic device"),
        ]
    )
    assert detect_language(entries) == ("zh-Hans", "en")


def test_detect_chinese_monolingual() -> None:
    entries = _sample(
        [
            ("苹果", "一种水果，落叶乔木的果实"),
            ("杏子", "蔷薇科植物的果实，味酸甜"),
            ("香蕉", "热带水果，果实细长"),
            ("计算机", "电子计算设备，可进行数值计算"),
        ]
    )
    assert detect_language(entries) == ("zh-Hans", "zh-Hans")


def test_detect_traditional_chinese() -> None:
    entries = _sample(
        [
            ("蘋果", "一種水果，落葉喬木的果實"),
            ("電腦", "電子計算設備，可進行數值計算"),
            ("詞典", "收錄詞語的工具書"),
            ("漢語", "漢族的語言文字"),
        ]
    )
    assert detect_language(entries) == ("zh-Hant", "zh-Hant")


def test_detect_english_monolingual() -> None:
    entries = _sample(
        [
            ("apple", "a round fruit with red or green skin"),
            ("apricot", "a small orange fruit"),
            ("banana", "a long curved fruit"),
        ]
    )
    assert detect_language(entries) == ("en", "en")


def test_detect_japanese_kana() -> None:
    entries = _sample(
        [
            ("りんご", "リンゴ，果物の一種"),
            ("ばなな", "バナナ，熱帯の果実"),
            ("でんし", "電子計算機，数値計算を行う装置"),
        ]
    )
    assert detect_language(entries) == ("ja", "ja")


def test_html_tags_in_definitions_do_not_skew_detection() -> None:
    """MDict 的释义是 HTML，标签名与属性名全是拉丁字母。

    不剥掉的话拉丁占比会被显著拉高，英汉词典的释义侧就可能被判成英文。
    """
    entries = _sample(
        [
            ("apple", '<div class="entry"><span class="pos">n.</span>苹果，一种水果</div>'),
            ("banana", '<div class="entry"><span class="pos">n.</span>香蕉，热带水果</div>'),
        ]
    )
    assert detect_language(entries) == ("en", "zh-Hans")


def test_detect_returns_none_when_sample_too_small() -> None:
    entries = [
        ParsedEntry(word="apple", definition="苹果"),
        ParsedEntry(word="pear", definition="梨"),
    ]
    assert detect_language([]) == (None, None)
    assert detect_language(entries) == (None, None)


def test_detect_sides_are_independent() -> None:
    """只有一侧（这里是没有释义）时，另一侧仍应给出结论。"""
    entries = _sample([("apple", ""), ("banana", "")])
    lang_from, lang_to = detect_language(entries)
    assert lang_from == "en"
    assert lang_to is None
