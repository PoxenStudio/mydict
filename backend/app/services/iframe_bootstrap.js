/*
 * 注入到每个词条 iframe 里的引导脚本。
 *
 * 词条 iframe 用 sandbox="allow-scripts"（**不含** allow-same-origin）加载，因此它是一个
 * 不透明源：既能继续跑词典自带 JS、保留各词典自己的排版，又拿不到父页面（token 存在
 * localStorage 里，不能被第三方词典的脚本读走）。代价是不透明源下若干浏览器能力会抛异常，
 * 这里逐个补上，并承担三件事：
 *   1. 把词条文档的高度报给父页（无 allow-same-origin 时父页读不到 contentDocument）
 *   2. 拦截词条内跳转（entry://）与发音（sound://）链接，转成消息交给父页处理
 *   3. 把外链、弹窗、危险协议收敛到受控路径
 *
 * 与父页的协议（父页用 event.source === iframe.contentWindow 认证，不看 origin，
 * 因为不透明源发出来的 origin 恒为 "null"）：
 *   子 -> 父  mydict:ready / mydict:height / mydict:entry / mydict:open
 *             mydict:audio-unsupported / mydict:audio-error / mydict:title
 *   父 -> 子  mydict:cmd {cmd: 'anchor'|'ping'|'theme'}
 */
(function () {
  'use strict'
  if (window.__mydictBooted) return
  window.__mydictBooted = true

  var DICT_ID = __MYDICT_DICT_ID__
  var RES_PREFIX = '/dict-res/' + DICT_ID + '/res/'
  // 是否启用「选中文字 → 查词」菜单。由服务端按渲染路径决定：只有前台查询页有查词框，
  // 生词本与管理端预览传 false（在那里点了也没人能接住这个查询）。
  var ALLOW_LOOKUP = __MYDICT_LOOKUP__

  /* ------------------------------------------------------------------ 主题 */

  /* ----------------------------------------- 暗色下过暗的文字自动提亮 */

  // 词典常把颜色写死，深蓝是重灾区：浅色底上够看，一到暗色底几乎看不见。写死的颜色值五花
  // 八门，靠 CSS 属性选择器枚举不完，而 CSS 自己算不了亮度，所以这里换个思路——读渲染后的
  // 计算颜色，太暗就按同色相提亮（蓝的还是蓝的，只是变亮），并记下原值以便切回浅色时还原。
  //
  // 灰阶的深色（#111/#333 之类）没有色相，提亮成主题前景色——样式表里的这些值此前漏网，
  // 暗色下正文直接看不见（搜韵诗词全文检索版）。
  var TEXT_MIN_LUMINANCE = 0.45
  var TEXT_BOOST_LIGHTNESS = 66
  // 大词条可能有上万个元素，逐个读计算样式要花时间，超过这个数就只处理前一批
  var TEXT_SCAN_LIMIT = 5000
  var boostedText = []

  function parseRgb(value) {
    var match = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(value || '')
    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null
  }

  function relativeLuminance(rgb) {
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
  }

  function restoreTextColors() {
    for (var i = 0; i < boostedText.length; i++) {
      boostedText[i][0].style.color = boostedText[i][1]
    }
    boostedText = []
  }

  /* ------------------------------------- 暗色下过亮的背景自动压暗 */

  // 与上面「提亮暗字」是对称的另一半：词典同样常把背景写死成浅色（千篇汉语词典的正文容器
  // `.mcon` 就是 `#ebeee9`），暗色下文字被提亮成浅色，浅底配浅字等于什么都看不见。
  //
  // 和文字那边一样枚举不完，所以也走运行时读计算颜色这条路：**太亮就按同色相压暗**
  // （浅绿底变深绿底），而不是直接改透明——直接透明会把 `<hr>` 这类本来就靠背景色显示的
  // 分隔线一起弄没。
  var BG_MAX_LUMINANCE = 0.75
  var BG_TAME_LIGHTNESS = 18
  var tamedBackgrounds = []

  function restoreBackgrounds() {
    for (var i = 0; i < tamedBackgrounds.length; i++) {
      tamedBackgrounds[i][0].style.backgroundColor = tamedBackgrounds[i][1]
    }
    tamedBackgrounds = []
  }

  function tameLightBackgrounds() {
    restoreBackgrounds()
    if (document.documentElement.getAttribute('data-mydict-theme') !== 'dark') return
    // 与提亮文字共用同一个能力判断：不支持相对颜色语法就整段跳过
    if (!window.CSS || !CSS.supports || !CSS.supports('color', 'hsl(from red h s 50%)')) return
    if (!document.body) return

    var nodes = document.body.querySelectorAll('*')
    var count = Math.min(nodes.length, TEXT_SCAN_LIMIT)
    for (var i = 0; i < count; i++) {
      var el = nodes[i]
      var rgb = parseRgb(window.getComputedStyle(el).backgroundColor)
      // 透明背景算出的 rgb 是 0,0,0，亮度最低，自然不会被判定为「过亮」
      if (!rgb || relativeLuminance(rgb) <= BG_MAX_LUMINANCE) continue
      tamedBackgrounds.push([el, el.style.backgroundColor])
      el.style.backgroundColor =
        'hsl(from rgb(' + rgb.join(',') + ') h s ' + BG_TAME_LIGHTNESS + '%)'
    }
  }

  function boostDarkText() {
    restoreTextColors()
    if (document.documentElement.getAttribute('data-mydict-theme') !== 'dark') return
    // hsl(from …) 是相对颜色语法，太老的浏览器不认；不支持就整段跳过，别写出无效声明
    if (!window.CSS || !CSS.supports || !CSS.supports('color', 'hsl(from red h s 50%)')) return
    if (!document.body) return

    var nodes = document.body.querySelectorAll('*')
    var count = Math.min(nodes.length, TEXT_SCAN_LIMIT)
    for (var i = 0; i < count; i++) {
      var el = nodes[i]
      var rgb = parseRgb(window.getComputedStyle(el).color)
      if (!rgb || relativeLuminance(rgb) >= TEXT_MIN_LUMINANCE) continue
      var isGray = rgb[0] === rgb[1] && rgb[1] === rgb[2]
      boostedText.push([el, el.style.color])
      if (isGray) {
        // 灰阶没有色相，提亮成主题前景色。此前刻意跳过灰阶、指望注入的 CSS 规则兜底，
        // 但那些规则只覆盖 #000 精确值与内联样式——词典样式表里的 #111/#333（搜韵诗词
        // 正文的 div.content{color:#111111}）漏网，暗色下深灰字配深底直接看不见。
        el.style.color = '#eaf1ee'
      } else {
        el.style.color =
          'hsl(from rgb(' + rgb.join(',') + ') h s ' + TEXT_BOOST_LIGHTNESS + '%)'
      }
    }
  }

  /**
   * 切换词条内容的明暗。样式侧全部门控在 html[data-mydict-theme='dark'] 上，这里只写属性。
   *
   * 显式写 'light'（而不是移除属性）是必需的：文档开头可能已按系统偏好设成了 dark，
   * 移除属性并不能把它改回浅色。
   */
  function applyTheme(theme) {
    try {
      document.documentElement.setAttribute(
        'data-mydict-theme',
        theme === 'dark' ? 'dark' : 'light'
      )
    } catch (e) {
      /* 拿不到 documentElement 就算了，不值得为它打断整个引导脚本 */
    }
    if (theme === 'dark') {
      boostDarkText()
      tameLightBackgrounds()
    } else {
      restoreTextColors()
      restoreBackgrounds()
    }
  }

  // 首屏兜底：文档里没有主题初值（调用方没带 theme 参数）时先跟随系统偏好，
  // 免得暗色下闪一帧白底。父页随后发来的 mydict:cmd 会把它纠正过来。
  try {
    if (
      !document.documentElement.getAttribute('data-mydict-theme') &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
    ) {
      applyTheme('dark')
    }
  } catch (e) {
    /* 忽略 */
  }

  /* ------------------------------------------------------------------ 通信 */

  function send(type, payload) {
    var msg = { type: 'mydict:' + type }
    if (payload) {
      for (var key in payload) {
        if (Object.prototype.hasOwnProperty.call(payload, key)) msg[key] = payload[key]
      }
    }
    try {
      parent.postMessage(msg, '*')
    } catch (e) {
      /* 父页可能已销毁 */
    }
  }

  /* --------------------------------------------------- 不透明源下的能力补齐 */

  // localStorage/sessionStorage 在不透明源里访问即抛 SecurityError。
  // 词典里用到的场景（记住折叠状态之类）只需要「不报错、本次会话内有效」。
  function memoryStorage() {
    var data = Object.create(null)
    return {
      getItem: function (k) {
        k = String(k)
        return k in data ? data[k] : null
      },
      setItem: function (k, v) {
        data[String(k)] = String(v)
      },
      removeItem: function (k) {
        delete data[String(k)]
      },
      clear: function () {
        data = Object.create(null)
      },
      key: function (i) {
        return Object.keys(data)[i] || null
      },
      get length() {
        return Object.keys(data).length
      }
    }
  }
  function installStorage(name) {
    var slot = '__mydict_' + name
    try {
      Object.defineProperty(window, name, {
        configurable: true,
        get: function () {
          if (!this[slot]) this[slot] = memoryStorage()
          return this[slot]
        }
      })
    } catch (e) {
      /* 定义失败就让它继续抛，词典自己通常会 try/catch */
    }
  }
  installStorage('localStorage')
  installStorage('sessionStorage')

  try {
    var jar = {}
    Object.defineProperty(Document.prototype, 'cookie', {
      configurable: true,
      get: function () {
        return Object.keys(jar)
          .map(function (k) {
            return k + '=' + jar[k]
          })
          .join('; ')
      },
      set: function (value) {
        var pair = String(value).split(';')[0].split('=')
        if (pair.length >= 2) jar[pair[0].trim()] = pair.slice(1).join('=')
      }
    })
  } catch (e) {
    /* 忽略 */
  }

  // 不透明源下 pushState/replaceState 抛 SecurityError，词典多半只是拿它做无刷新导航
  try {
    history.pushState = function () {}
    history.replaceState = function () {}
  } catch (e) {
    /* 忽略 */
  }

  // 没有 allow-popups，window.open 会被拦掉。转给父页开新标签。
  window.open = function (url) {
    if (url) send('open', { url: String(url) })
    return null
  }

  /* ------------------------------------------------------------ 高度上报 */

  var lastHeight = -1
  var pending = false
  var ticks = 0

  // 测量哨兵：0 高度的块元素，钉在 body 末尾。它的底边天然位于「全部内容 + 末元素
  // 外距」之后——Range 边界盒不含外距（body 默认 8px + 末元素外距，实测少 8~24px），
  // 盒子比内容矮一截，词条右侧就会出现滚动条；scrollHeight 又有「视口托底」（见下）
  // 不能用。词典自己的脚本可能往 body 追加元素，所以每次测量前都把哨兵重新挪到末尾。
  function ensureSentinel(doc) {
    var sentinel = doc.getElementById('mydict-measure-end')
    if (!sentinel) {
      sentinel = doc.createElement('div')
      sentinel.id = 'mydict-measure-end'
      sentinel.style.cssText =
        'display:block;height:0;margin:0;padding:0;border:0;visibility:hidden'
    }
    if (sentinel.parentElement !== doc.body) doc.body.appendChild(sentinel)
    return sentinel
  }

  function measure() {
    var docEl = document.documentElement
    var body = document.body
    if (!body) return 0
    var height = 0
    try {
      var sentinel = ensureSentinel(document)
      var docTop = docEl.getBoundingClientRect().top
      var bodyStyle = window.getComputedStyle(body)
      height =
        sentinel.getBoundingClientRect().bottom - docTop +
        (parseFloat(bodyStyle.paddingBottom) || 0) +
        (parseFloat(bodyStyle.marginBottom) || 0)
    } catch (e) {
      /* 哨兵不可用时退回 scrollHeight（有视口托底，虚高但不会丢内容） */
    }
    if (height <= 0) {
      height = Math.max(body.scrollHeight, body.offsetHeight)
      if (docEl) height = Math.max(height, docEl.scrollHeight, docEl.offsetHeight)
    }
    return height
  }

  function flush() {
    pending = false
    var height = measure()
    if (height <= 0) return
    // 2px 迟滞：避免亚像素抖动导致父页反复重排、进而又触发这里，形成增长死循环
    if (lastHeight >= 0 && Math.abs(height - lastHeight) < 2) return
    lastHeight = height
    send('height', { height: height })
  }

  function report() {
    if (pending) return
    pending = true
    if (window.requestAnimationFrame) window.requestAnimationFrame(flush)
    else setTimeout(flush, 16)
  }

  function observeHeight() {
    try {
      if (window.ResizeObserver && document.documentElement) {
        var observer = new ResizeObserver(report)
        observer.observe(document.documentElement)
        if (document.body) observer.observe(document.body)
      }
    } catch (e) {
      /* 忽略 */
    }
    try {
      // 词典自带的折叠/切换 JS 会改 DOM 但不改根元素尺寸，MutationObserver 兜住这类
      if (window.MutationObserver && document.documentElement) {
        new MutationObserver(report).observe(document.documentElement, {
          childList: true,
          subtree: true,
          attributes: true,
          characterData: true
        })
      }
    } catch (e) {
      /* 忽略 */
    }
    window.addEventListener('load', report)
    window.addEventListener('resize', report)
    window.addEventListener('error', report, true)
    // 图片/音频是异步解码的，加载完成后高度会变
    window.addEventListener(
      'load',
      function (event) {
        var target = event.target
        if (target && target.tagName && /^(IMG|AUDIO|VIDEO|SOURCE|IFRAME|OBJECT|EMBED)$/.test(target.tagName)) {
          report()
        }
      },
      true
    )
    // 部分词典的首屏内容由延迟脚本填充，定时补几次；有上限，不做无限轮询。
    // 最早一档 200ms：更早的测量会撞上「CSS 还没加载完、按 300px 默认宽度排版」
    // 的虚高（见 measure 注释），把盒子一次性锁死在大值上。
    ;[200, 600, 1500, 3000].forEach(function (delay) {
      setTimeout(report, delay)
    })
    var tail = setInterval(function () {
      ticks++
      report()
      if (ticks > 20) clearInterval(tail)
    }, 1000)
  }

  /* --------------------------------------------------------- 链接与音频 */

  // .spx 必须在列表里：导入时词条里的 sound://…spx 已被改写成 /dict-res/…/x.spx，
  // 拦不住的话点击会直接让 iframe 导航到 spx 文件，浏览器弹出解不了的内置播放器，
  // 词条整个被换掉（实测 NHK 发音词典）。.spx 由 playAudio 走 JS 解码播放。
  var AUDIO_EXT_RE = /\.(mp3|wav|ogg|oga|opus|m4a|aac|flac|wma|spx)(?:[?#].*)?$/i
  var SPX_EXT_RE = /\.spx(?:[?#].*)?$/i

  // 遗留坏链接：早期导入代码把 entry://x 改成了 /dict-res/N/res/entry:/x（旧库里还有
  // 数百万行）。修复命令跑完之前先在这里兼容，用户不必等迁移就能点。
  var LEGACY_RE = /^\/dict-res\/\d+\/res\/(entry|sound):\/(.*)$/i

  function resourceUrl(raw) {
    var path = String(raw).replace(/^[\\/]+/, '')
    return RES_PREFIX + path
  }

  // .spx（Ogg Speex）浏览器的原生解码器都不支持，但 libspeex 编译成的 JS 解码器可以
  // 在浏览器里解（django-mdict 项目就是这么做的，实测可行）。所以候选顺序是
  // `.mp3` → `.opus`（词典自带的或历史转码产物，原生 audio 直接放）→ 原 `.spx`
  //（走 JS 解码）。全都失败再报错，父页据此提示而不是静默失败。
  function audioCandidates(url) {
    if (!SPX_EXT_RE.test(url)) return [url]
    return [url.replace(SPX_EXT_RE, '.mp3'), url.replace(SPX_EXT_RE, '.opus'), url]
  }

  /* ------------------------------------------------ Speex 的 JS 解码播放 */

  // 解码器从父页的静态资源加载。srcdoc iframe 里相对 URL 以父页地址为 base
  //（与上面 /dict-res 的解析同理），所以绝对路径 /speex/... 就能命中。
  var SPEEX_SCRIPTS = [
    '/speex/bitstring.min.js',
    '/speex/pcmdata.min.js',
    '/speex/speex.min.js'
  ]
  var speexLoader = null

  function loadSpeexDecoder() {
    if (speexLoader) return speexLoader
    speexLoader = new Promise(function (resolve, reject) {
      var loaded = 0
      SPEEX_SCRIPTS.forEach(function (src) {
        var el = document.createElement('script')
        el.src = src
        el.onload = function () {
          loaded += 1
          if (loaded === SPEEX_SCRIPTS.length) resolve()
        }
        el.onerror = function () {
          speexLoader = null // 允许下次重试
          reject(new Error('解码器脚本加载失败: ' + src))
        }
        ;(document.head || document.documentElement).appendChild(el)
      })
    })
    return speexLoader
  }

  function binaryString(bytes) {
    // Uint8Array → 二进制字符串。必须分块：apply 的参数个数有上限，大文件会爆栈
    var CHUNK = 8192
    var out = ''
    for (var i = 0; i < bytes.length; i += CHUNK) {
      out += String.fromCharCode.apply(
        null,
        bytes.subarray(i, Math.min(i + CHUNK, bytes.length))
      )
    }
    return out
  }

  // 解码规则与 django-mdict 的 mdict.js 一致（含那条经验修正：双声道时采样率减半，
  // 否则 NHK 的 32kHz 双声道 spx 会播放过快）
  function decodeSpeex(bytes) {
    var ogg = new Ogg(binaryString(bytes), { file: true })
    ogg.demux()
    var header = Speex.parseHeader(ogg.frames[0])
    if (header.nb_channels == 2) header.rate = header.rate / 2
    var spx = new Speex({ quality: 8, mode: header.mode, rate: header.rate })
    var wave = PCMData.encode({
      sampleRate: header.rate,
      channelCount: header.nb_channels,
      bytesPerSample: 2,
      data: spx.decode(ogg.bitstream(), ogg.segments)
    })
    return new Blob([Speex.util.str2ab(wave)], { type: 'audio/wav' })
  }

  // 每个 audio 元素只留一份解码结果：换源时释放上一份。不在 ended 时释放——词典自带的
  // <audio controls> 还要能重播
  function setDecodedSource(el, blob) {
    if (el.__mydictBlobUrl) URL.revokeObjectURL(el.__mydictBlobUrl)
    el.__mydictBlobUrl = URL.createObjectURL(blob)
    el.src = el.__mydictBlobUrl
  }

  /** 把 spx 解码成 WAV 并塞给 `el` 播放；失败走 `fail`。 */
  function playSpeexDecoded(el, spxUrl, fail) {
    loadSpeexDecoder()
      .then(function () {
        return fetch(spxUrl).then(function (resp) {
          if (!resp.ok) throw new Error('HTTP ' + resp.status)
          return resp.arrayBuffer()
        })
      })
      .then(function (buf) {
        setDecodedSource(el, decodeSpeex(new Uint8Array(buf)))
        var played = el.play()
        if (played && played.catch) played.catch(fail)
      })
      .catch(fail)
  }

  function ensureAudioEl() {
    if (!audioEl) {
      audioEl = document.createElement('audio')
      audioEl.setAttribute('data-mydict-player', '1')
      audioEl.style.display = 'none'
      ;(document.body || document.documentElement).appendChild(audioEl)
    }
    return audioEl
  }

  var audioEl = null
  function playAudio(url) {
    var candidates = audioCandidates(url)
    var index = 0
    function fail() {
      send(candidates.length > 1 ? 'audio-unsupported' : 'audio-error', { url: url })
    }
    function attempt() {
      if (index >= candidates.length) {
        fail()
        return
      }
      var current = candidates[index++]
      var el = ensureAudioEl()
      el.onended = function () {
        send('audio-ended', { url: url })
      }
      // mp3/opus 这类 404 的候选会**同时**触发 error 事件与 play() 的 reject，两边
      // 各推进一次会跳级、还多出一次越界 attempt —— 表现为音频明明解码成功播出来了，
      // 却仍弹「发音不存在」（实测大辞泉、韦氏大学词典，都是纯 spx 词典）。每次
      // attempt 只许推进一次。
      var advanced = false
      function advance() {
        if (advanced) return
        advanced = true
        attempt()
      }
      // 走到原 .spx 这一步：原生放不了，交给 JS 解码。先摘掉上一个候选挂的 onerror，
      // 否则解码结果播放失败时会再触发一次 attempt，重复上报
      if (SPX_EXT_RE.test(current)) {
        el.onerror = null
        playSpeexDecoded(el, current, fail)
        return
      }
      el.onerror = advance
      el.src = current
      var played = el.play()
      if (played && played.catch) {
        played.catch(advance)
      }
    }
    attempt()
  }

  function scrollToAnchor(anchor) {
    if (!anchor) return
    var target = null
    try {
      target = document.getElementById(anchor) || document.getElementsByName(anchor)[0]
    } catch (e) {
      target = null
    }
    if (target && target.scrollIntoView) target.scrollIntoView(true)
    report()
  }

  function findAnchor(event) {
    var node = event.target
    while (node && node !== document && node.tagName !== 'A') node = node.parentNode
    return node && node.tagName === 'A' ? node : null
  }

  // 返回 true 表示这次点击已被接管，不应再交给词典自带的处理器
  function handleLink(href) {
    if (href === null || href === undefined) return false
    var raw = String(href).trim()
    if (!raw) return false

    var hashIndex = raw.indexOf('#')
    var anchor = hashIndex >= 0 ? raw.slice(hashIndex + 1) : ''
    var base = hashIndex >= 0 ? raw.slice(0, hashIndex) : raw

    if (base.slice(0, 8).toLowerCase() === 'entry://') {
      var word = base.slice(8)
      if (word) send('entry', { word: word, anchor: anchor })
      else scrollToAnchor(anchor) // entry://#anchor 是页内跳转
      return true
    }

    if (base.slice(0, 8).toLowerCase() === 'sound://') {
      playAudio(resourceUrl(base.slice(8)))
      return true
    }

    var legacy = LEGACY_RE.exec(base)
    if (legacy) {
      var kind = legacy[1].toLowerCase()
      var rest = legacy[2]
      if (kind === 'entry') {
        if (rest) send('entry', { word: rest, anchor: anchor })
        else scrollToAnchor(anchor)
      } else {
        playAudio(RES_PREFIX + rest)
      }
      return true
    }

    if (base.charAt(0) === '#') {
      scrollToAnchor(anchor)
      return true
    }

    // 危险协议：不导航、也不交给词典的处理器
    if (/^(javascript|vbscript|file|blob|data):/i.test(base)) return true

    if (/^(https?:)?\/\//i.test(base) || /^www\./i.test(base) || /^mailto:/i.test(base)) {
      send('open', { url: base })
      return true
    }

    if (base.slice(0, RES_PREFIX.length) === RES_PREFIX && AUDIO_EXT_RE.test(base)) {
      playAudio(base)
      return true
    }
    return false
  }

  // 扫描版词典（如辞海）的整页图片按容器宽度显示后，一页上的多栏小字根本读不了，
  // 所以点大图时交给父页弹一个可缩放的大图查看器。
  //
  // 用**渲染尺寸**而不是 naturalWidth 判「够大」：各词典正文里到处是 16px 的小图标
  // （发音按钮、词性括号、派生語图标），点它们弹大图会很烦；而一张大图若被 CSS 缩成
  // 16px 当图标用，同样不该弹。
  var IMAGE_MIN_SIZE = 160

  // 同一词条里可能有多张大图（扫描版词典常把连续几页放在一起），点开后要能在它们之间翻，
  // 所以把「够大」的图按文档顺序收集成一张表一起发给父页。
  function collectLargeImages() {
    var urls = []
    var seen = {}
    var nodes
    try {
      nodes = document.querySelectorAll('img')
    } catch (e) {
      return urls
    }
    for (var i = 0; i < nodes.length; i++) {
      var box = nodes[i].getBoundingClientRect()
      if (box.width < IMAGE_MIN_SIZE && box.height < IMAGE_MIN_SIZE) continue
      var url = nodes[i].currentSrc || nodes[i].src
      // 同一张图在正文里出现多次时只留一个
      if (!url || seen[url]) continue
      seen[url] = 1
      urls.push(url)
    }
    return urls
  }

  /* ------------------------------------- 评注面板点击展开/折叠 */

  // 搜韵诗词全文检索版的词条里，「评注（点击查看或隐藏评注）」是 div.commentPanel，
  // 紧跟其后的 div#comment_xxx.comment 才是评注正文——词条里没有任何脚本，这个开关在
  // MDict 客户端/django-mdict 里是靠词典环境补的，这里用委托点击实现同样的效果。
  // 匹配放宽到「class 含 comment」：同一部词典还有 div.allusionNote 之类的变体结构，
  // 但面板后第一个带 comment 的块就是正文，往前找不到 id 也不至于误伤别的块。
  function commentBlockAfter(panel) {
    var node = panel.nextElementSibling
    while (node) {
      var id = node.id || ''
      var className = ' ' + (node.className || '') + ' '
      if (id.indexOf('comment_') === 0 || className.indexOf(' comment ') >= 0) return node
      node = node.nextElementSibling
    }
    return null
  }

  // 评注默认折叠：搜韵原站也是收起的（「点击查看或隐藏评注」），全展开会把词条顶得
  // 很长。在文档就绪时统一把面板后的评注块藏掉，点击面板时再由上面的开关恢复。
  function collapseCommentPanels() {
    var panels
    try {
      panels = document.querySelectorAll('.commentPanel')
    } catch (e) {
      return
    }
    for (var i = 0; i < panels.length; i++) {
      var block = commentBlockAfter(panels[i])
      if (block) block.style.display = 'none'
    }
  }

  document.addEventListener(
    'click',
    function (event) {
      var node = event.target
      if (!node || !node.closest) return
      var panel = node.closest('.commentPanel')
      if (!panel) return
      var block = commentBlockAfter(panel)
      if (!block) return
      block.style.display = block.style.display === 'none' ? '' : 'none'
      report()
    },
    true
  )

  // 让面板看起来可点（词典自己的 CSS 没写 cursor）
  try {
    var panelStyle = document.createElement('style')
    panelStyle.textContent = '.commentPanel{cursor:pointer}'
    ;(document.head || document.documentElement).appendChild(panelStyle)
  } catch (e) {
    /* 忽略 */
  }

  document.addEventListener(
    'click',
    function (event) {
      var anchorEl = findAnchor(event)
      var href = anchorEl ? anchorEl.getAttribute('href') : null
      // 包在 <a href> 里的图仍走链接逻辑（有些词典把图做成链接）
      if (!href && event.target && event.target.tagName === 'IMG') {
        var clicked = event.target
        var box = clicked.getBoundingClientRect()
        if (box.width >= IMAGE_MIN_SIZE || box.height >= IMAGE_MIN_SIZE) {
          event.preventDefault()
          var current = clicked.currentSrc || clicked.src
          var urls = collectLargeImages()
          var index = urls.indexOf(current)
          // 理论上点中的这张一定在表里（它刚被判为「够大」）；万一因为还没布局出来而漏了，
          // 退化成单张，总比翻到一张空白好
          if (index < 0) {
            urls = [current]
            index = 0
          }
          send('image', {
            src: current,
            alt: clicked.alt || '',
            urls: urls,
            index: index
          })
          return
        }
      }
      if (!anchorEl) return
      var target = (anchorEl.getAttribute('target') || '').toLowerCase()
      if (target === '_top' || target === '_parent') {
        // 没有 allow-top-navigation，跳出去会失败并可能报错，直接吞掉
        event.preventDefault()
        return
      }
      if (handleLink(anchorEl.getAttribute('href'))) {
        event.preventDefault()
        event.stopPropagation()
        return
      }
      if ((event.ctrlKey || event.metaKey) && anchorEl.getAttribute('href')) {
        // 没有 allow-popups，浏览器开不了新标签，转给父页
        event.preventDefault()
        send('open', { url: anchorEl.getAttribute('href') })
      }
    },
    true
  )

  document.addEventListener(
    'auxclick',
    function (event) {
      if (event.button !== 1) return
      var anchorEl = findAnchor(event)
      if (!anchorEl) return
      event.preventDefault()
      send('open', { url: anchorEl.getAttribute('href') || '' })
    },
    true
  )

  // <audio src="sound://..."> 这类不是链接、点不到，需要在文档就绪后直接改写属性。
  // 只扫媒体元素（数量很少），不做全文档遍历。
  // 媒体元素没法像 playAudio 那样自己逐个试，所以挂 error 事件按候选顺序换源。
  function attachAudioFallback(el, candidates) {
    var index = 0
    function attempt() {
      if (index >= candidates.length) return
      var current = candidates[index++]
      if (SPX_EXT_RE.test(current)) {
        // 词典自带的 <audio src="...spx">：原生放不了，解码成 WAV 后仍用它播
        playSpeexDecoded(el, current, function () {})
        return
      }
      el.setAttribute('src', current)
    }
    el.addEventListener('error', attempt)
    attempt()
  }

  function fixMediaSources() {
    var nodes
    try {
      nodes = document.querySelectorAll('audio,source,video,embed,object')
    } catch (e) {
      return
    }
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i]
      var mediaLike = /^(AUDIO|VIDEO|SOURCE)$/.test(el.tagName)
      ;['src', 'data'].forEach(function (attr) {
        var value = el.getAttribute && el.getAttribute(attr)
        if (!value) return
        var fixed = null
        if (value.slice(0, 8).toLowerCase() === 'sound://') fixed = resourceUrl(value.slice(8))
        else {
          var legacy = LEGACY_RE.exec(value)
          if (legacy && legacy[1].toLowerCase() === 'sound') fixed = RES_PREFIX + legacy[2]
        }
        if (!fixed) return
        if (attr === 'src' && mediaLike) {
          attachAudioFallback(el, audioCandidates(fixed))
        } else {
          el.setAttribute(attr, audioCandidates(fixed)[0])
        }
      })
    }
  }

  window.addEventListener('message', function (event) {
    var data = event.data
    if (!data || data.type !== 'mydict:cmd') return
    if (data.cmd === 'anchor') scrollToAnchor(data.anchor)
    else if (data.cmd === 'theme') applyTheme(data.theme)
    else if (data.cmd === 'ping') {
      report()
      send('ready', {})
    }
  })

  /* -------------------------------------------------------- 选中文字查词 */

  // 选中词条里的文字时，在选区旁边弹一个【查词】，点了把选中文字交给父页去查。
  //
  // 菜单画在 iframe **内部**而不是父页：iframe 是不透明源，内部点击不会冒泡到父页，画在
  // 父页得做坐标换算，而且 iframe 内容长高时要重定位（高度上报会反复触发）。画在这里，
  // 点击直接复用既有的 mydict:entry 消息，父页一行都不用改。
  var LOOKUP_MIN_CHARS = 1
  // 超过这个长度基本是整行/整段拖选，不是要查的词
  var LOOKUP_MAX_CHARS = 30
  var lookupMenu = null
  var lookupText = ''

  function hideLookupMenu() {
    if (lookupMenu && lookupMenu.parentNode) lookupMenu.parentNode.removeChild(lookupMenu)
    lookupMenu = null
    lookupText = ''
  }

  function selectedText() {
    var selection = window.getSelection && window.getSelection()
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null
    var text = selection.toString().replace(/\s+/g, ' ').trim()
    if (text.length < LOOKUP_MIN_CHARS || text.length > LOOKUP_MAX_CHARS) return null
    return text
  }

  function showLookupMenu(range, text) {
    hideLookupMenu()
    lookupText = text
    var rect = range.getBoundingClientRect()

    lookupMenu = document.createElement('div')
    lookupMenu.className = 'mydict-lookup'
    lookupMenu.setAttribute('role', 'button')
    lookupMenu.textContent = '查词'
    // 先藏起来挂上去，量完尺寸再定位，免得在左上角闪一下
    lookupMenu.style.visibility = 'hidden'
    ;(document.documentElement || document.body).appendChild(lookupMenu)

    var width = lookupMenu.offsetWidth
    var height = lookupMenu.offsetHeight
    var gap = 6
    var top = rect.bottom + gap
    // 底边放不下就翻到选区上方，再放不下就贴顶
    if (top + height > window.innerHeight) top = Math.max(0, rect.top - height - gap)
    var left = Math.max(0, Math.min(rect.left + rect.width / 2 - width / 2,
                                  window.innerWidth - width))
    lookupMenu.style.top = top + 'px'
    lookupMenu.style.left = left + 'px'
    lookupMenu.style.visibility = 'visible'

    // mousedown 必须拦：不拦的话点按钮会先把选区清掉，然后才轮到 click，查词就查了个空
    lookupMenu.addEventListener('mousedown', function (event) {
      event.preventDefault()
      event.stopPropagation()
    })
    lookupMenu.addEventListener('click', function (event) {
      event.preventDefault()
      event.stopPropagation()
      if (lookupText) send('entry', { word: lookupText })
      hideLookupMenu()
    })
  }

  function onLookupMouseUp(event) {
    if (event.button !== 0) return
    if (lookupMenu && lookupMenu.contains(event.target)) return
    var text = selectedText()
    var selection = window.getSelection && window.getSelection()
    if (!text || !selection || !selection.rangeCount) {
      hideLookupMenu()
      return
    }
    showLookupMenu(selection.getRangeAt(0), text)
  }

  function onLookupSelectionChange() {
    // 只在菜单已经显示时才管——拖选过程中这个事件会疯狂触发
    if (lookupMenu && selectedText() !== lookupText) hideLookupMenu()
  }

  function onLookupMouseDown(event) {
    if (lookupMenu && lookupMenu.contains(event.target)) return
    hideLookupMenu()
  }

  function onLookupKeyDown(event) {
    if (event.key === 'Escape') hideLookupMenu()
  }

  function installLookupMenu() {
    if (!ALLOW_LOOKUP) return
    document.addEventListener('mouseup', onLookupMouseUp)
    // capture 阶段：要在选区被清掉之前知道「这一下点的是菜单还是别处」
    document.addEventListener('mousedown', onLookupMouseDown, true)
    document.addEventListener('selectionchange', onLookupSelectionChange)
    document.addEventListener('keydown', onLookupKeyDown)
    // capture 的 scroll 能同时覆盖 window 滚动与 iframe 内部的滚动容器
    window.addEventListener('scroll', hideLookupMenu, true)
    window.addEventListener('resize', hideLookupMenu)
  }

  function onReady() {
    fixMediaSources()
    collapseCommentPanels()
    // 首屏就是暗色时，正文已经解析完了，这时才做得了提亮
    boostDarkText()
    installLookupMenu()
    observeHeight()
    report()
    send('ready', {})
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady)
  } else {
    onReady()
  }
})()
