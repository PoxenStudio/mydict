from app.services.language_detect import detect_language


def _detect(pairs: list[tuple[str, str]], repeat: int = 60) -> tuple[str | None, str | None]:
    """把少量真实词条重复成足够大的样本：识别只看字符构成，重复不改变结论。

    词头与释义是分开传入的（词头能跨整部词典均匀取样、释义只能顺序取），所以这里也
    分成两个列表。
    """
    headwords = [word for _ in range(repeat) for word, _ in pairs]
    definitions = [definition for _ in range(repeat) for _, definition in pairs]
    return detect_language(headwords, definitions)


def test_detect_english_to_chinese() -> None:
    assert _detect(
        [
            ("apple", "苹果，一种水果"),
            ("apricot", "杏子，蔷薇科植物的果实"),
            ("banana", "香蕉，热带水果"),
            ("computer", "计算机，电子计算设备"),
        ]
    ) == ("en", "zh-Hans")


def test_detect_chinese_to_english() -> None:
    assert _detect(
        [
            ("苹果", "apple, a round fruit"),
            ("杏子", "apricot, a small orange fruit"),
            ("香蕉", "banana, a long curved fruit"),
            ("计算机", "computer, an electronic device"),
        ]
    ) == ("zh-Hans", "en")


def test_detect_chinese_monolingual() -> None:
    assert _detect(
        [
            ("苹果", "一种水果，落叶乔木的果实"),
            ("杏子", "蔷薇科植物的果实，味酸甜"),
            ("香蕉", "热带水果，果实细长"),
            ("计算机", "电子计算设备，可进行数值计算"),
        ]
    ) == ("zh-Hans", "zh-Hans")


def test_detect_traditional_chinese() -> None:
    assert _detect(
        [
            ("蘋果", "一種水果，落葉喬木的果實"),
            ("電腦", "電子計算設備，可進行數值計算"),
            ("詞典", "收錄詞語的工具書"),
            ("漢語", "漢族的語言文字"),
        ]
    ) == ("zh-Hant", "zh-Hant")


def test_detect_english_monolingual() -> None:
    assert _detect(
        [
            ("apple", "a round fruit with red or green skin"),
            ("apricot", "a small orange fruit"),
            ("banana", "a long curved fruit"),
        ]
    ) == ("en", "en")


def test_detect_japanese_kana() -> None:
    assert _detect(
        [
            ("りんご", "リンゴ，果物の一種"),
            ("ばなな", "バナナ，熱帯の果実"),
            ("でんし", "電子計算機，数値計算を行う装置"),
        ]
    ) == ("ja", "ja")


def test_html_tags_in_definitions_do_not_skew_detection() -> None:
    """MDict 的释义是 HTML，标签名与属性名全是拉丁字母。

    不剥掉的话拉丁占比会被显著拉高，英汉词典的释义侧就可能被判成英文。
    """
    assert _detect(
        [
            ("apple", '<div class="entry"><span class="pos">n.</span>苹果，一种水果</div>'),
            ("banana", '<div class="entry"><span class="pos">n.</span>香蕉，热带水果</div>'),
        ]
    ) == ("en", "zh-Hans")


def test_html_entities_do_not_skew_detection() -> None:
    """`&nbsp;` 这类实体不剥掉会被算成 4 个拉丁字母。

    MDict 释义里排版用的实体很密集（每行缩进都是若干个 &nbsp;），足以把中文释义的
    拉丁占比拉过汉字，判成 en。
    """
    assert _detect(
        [
            ("苹果", "&nbsp;&nbsp;&nbsp;&nbsp;一种水果，落叶乔木的果实"),
            ("香蕉", "&nbsp;&nbsp;&nbsp;&nbsp;热带水果，果实细长"),
            ("计算机", "&nbsp;&nbsp;&nbsp;&nbsp;电子计算设备，可进行数值计算"),
        ]
    ) == ("zh-Hans", "zh-Hans")


def test_entity_only_definitions_are_not_text() -> None:
    """整条释义只有排版实体时，等于没有正文，不该作为判断依据。"""
    headwords, _ = [], []
    for _ in range(60):
        headwords.extend(["apple", "banana"])
    assert detect_language(headwords, ["&nbsp;", "&nbsp;"])[1] is None


def test_detect_returns_none_when_sample_too_small() -> None:
    assert detect_language([], []) == (None, None)
    assert detect_language(["apple", "pear"], ["苹果", "梨"]) == (None, None)


def test_detect_sides_are_independent() -> None:
    """只有一侧（这里是没有释义）时，另一侧仍应给出结论。"""
    headwords = [word for _ in range(60) for word in ("apple", "banana")]
    lang_from, lang_to = detect_language(headwords, [])
    assert lang_from == "en"
    assert lang_to is None
