"""按字符脚本推断词典的语言方向。

词典自身的元数据里没有可靠的语言字段（StarDict 的 .ifo、MDict 的 header 都没有），
所以改为从样本「词头用什么文字写、释义用什么文字写」来推断：拉丁字母基本就是英文、
汉字就是中文、假名就是日文。这个方法区分不了同用拉丁字母的语言（法语/德语/西班牙语
都会被判成 en），这是已知且可接受的取舍——识别结果只是默认值，管理员可以在词典列表里
随时改。
"""

import re

from app.parsers.base import ParsedEntry

# 有效字符少于这个数时任何占比都是噪声，宁可返回 None 交给调用方兜底。
_MIN_CHARS = 20

# 假名太少说明只是词源里混进来的零星字符，不足以判定为日文。
_MIN_KANA = 10

# 简体文本里传统字形是零出现，所以只要传统字形占到 1% 就足以判定为繁体。
_TRADITIONAL_RATIO = 0.01

# 释义可能是 HTML（MDict 的释义整段是 HTML），标签名与属性名全是拉丁字母，
# 不剥掉会把拉丁占比显著拉高、把中英判断带偏。
_TAG_RE = re.compile(r"<[^>]+>")

_LATIN_RE = re.compile(r"[A-Za-z]")
# CJK 统一表意文字（含扩展 A 与兼容表意文字）
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# 平假名 + 片假名
_KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")

# 只在繁体文本里出现的字形。这里刻意只收「繁体独有」的字，不做简繁对照表——
# 像 制/製、里/裡、并/並、于/於 这类简体字形本身也通用于繁体的字必须排除，
# 否则会把繁体文本误判成简体。
_TRADITIONAL_ONLY = frozenset(
    "後國學語詞漢義發說這個們為會來時過對開關門問間見現電車長萬與書頭買賣錢銀鐵鳥馬魚龍"
    "風雲聲聽讀寫記認識話請謝誰愛歡樂覺習樣點熱讓應該經濟織級紅綠紙線練結給統絲麗嚴豐臨"
    "舉麼烏喬鄉亂爭虧亞產畝親億僅從倉儀價眾優偉傳傷倫偽體俠債傾償儲兒兌蘭興養獸內軍農衝"
    "決況凍淨減鳳憑凱擊劉則剛創刪劑劍劇勸辦務動勵勞勢勳區醫華協單衛廠廳歷厲壓厭縣參雙變"
    "號嘆嚇呂嗎噸啟員嗚詠響啞喚噴團園圍圖圓聖場壞塊堅壩墳墜壘殼處備復夠夾奪奮獎妝婦媽娛"
    "嬰孫寧寶實審宮寬賓尋導盡層嘗屬歲豈崗島嶺峽幣帥師帳幫帶廣莊慶庫廢異棄張彌彎彈強歸當"
    "錄徹徑憶憂懷態憐總戀懇惡惱懸驚懼慘懲慣願戲戰戶撲執擴掃揚擾拋護報擔擬擇掛損換據撿擲"
    "撐擺攝攤敵數斷無舊顯曉暫術機殺雜權條楊極構槍檔橋夢檢樓歐殲殘毆毀畢氣匯湯溝沒淪滬淚"
    "潑澤潔灑淺漿濁測瀏渾濃塗濤潤漲漸漁溫灣濕滿滾滯濾濱灘潛滅燈靈災燦爐煉爛煩燒煥爺牽犧"
    "猶狽獅獨獄狹環責敗貨質販貪貧貴貸貿費賀賊資賦賭賞賠賴賺賽讚贈贏趙趨躍蹤軌軒轉輪軟轟"
    "軸輕載較輔輛輩輝輸辭辯邊遼達遷運還進遠違連遲選遞邏遺鄧郵鄰鄭釋針釘釣鐘鋼鑰欽鉤鑽鈴"
    "鉛銅鋁鏟鋪鏈銷鎖鍋鋒銳錯錫鑼錘錦鍵鎮鏡閉閒悶閘鬧聞閥閣閱隊陽陰陣階際陸陳險隨隱難雛"
    "雞離霧頁頂項順須頑顧頓頒預領頻顆題顏額飛飯飲館驅駁驗騎騙魯鮮鳴鴉鴨鴿鵝鷹麥黃齊齒齡龜"
)


def _classify(text: str) -> str | None:
    """判断一段文本对应的语言代码；样本不足或无法判断时返回 None。"""
    if not text:
        return None
    cjk_chars = _CJK_RE.findall(text)
    latin = len(_LATIN_RE.findall(text))
    # 假名同样算有效字符，否则纯假名（片假名外来语）的日文词头会被当成样本不足。
    kana = len(_KANA_RE.findall(text))
    if len(cjk_chars) + latin + kana < _MIN_CHARS:
        return None

    # 假名是日文排他性的判据（中英文文本都不会出现），优先于中英判断。要求假名数量
    # 至少是汉字的三分之一：真实日文里假名占比通常与汉字相当，而中文词典偶尔在词源里
    # 夹几个假名远达不到这个比例。漏判成中文比误判成日文更糟——汉字字形会被顺势认成
    # 繁体，所以这里宁松勿严。
    if kana >= _MIN_KANA and kana * 3 >= len(cjk_chars):
        return "ja"

    if len(cjk_chars) >= latin:
        traditional = len([ch for ch in cjk_chars if ch in _TRADITIONAL_ONLY])
        threshold = max(1, int(len(cjk_chars) * _TRADITIONAL_RATIO))
        return "zh-Hant" if traditional >= threshold else "zh-Hans"
    return "en"


def detect_language(entries: list[ParsedEntry]) -> tuple[str | None, str | None]:
    """返回 (lang_from, lang_to)；任一侧判定不了时该侧为 None。

    lang_from 看词头用什么文字写，lang_to 看释义用什么文字写，于是英汉、汉英、
    汉语单语、英英四种常见情形都能区分开。
    """
    headwords = "\n".join(entry.word for entry in entries)
    definitions = "\n".join(_TAG_RE.sub(" ", entry.definition or "") for entry in entries)
    return _classify(headwords), _classify(definitions)
