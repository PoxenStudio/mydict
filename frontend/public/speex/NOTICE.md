# Speex 解码器（第三方组件）

`speex.min.js` / `bitstring.min.js` / `pcmdata.min.js` 来自
[jpemartins/speex.js](https://github.com/jpemartins/speex.js)（用 emscripten 把
[libspeex](https://www.speex.org/) 1.2.0RC 编译成 JavaScript 的移植，libspeex 本身为
BSD 许可）。用于在浏览器里解码 MDict 词典自带的 Ogg Speex 发音文件。

这三个 min 构建产物自身未携带许可头；引入时请在 PR 里向上游确认，若上游要求更严格的
许可声明，需要替换为带完整许可文本的版本。
