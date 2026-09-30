# MyDict Web API 参考（Token 接口）

本文说明 MyDict 对外提供的 `/api/v1` 接口：用 API Token 查词、联想、获取词典列表，以及读写生词本。内容以 `backend/app/api/v1/` 下的路由代码为准；接口有新增或修改时，需同步更新本文与《技术方案设计.md》第 4 节接口表。

- 基础地址：`http(s)://<host>:<port>`，下文路径均相对于此。
- 编码：请求与响应均为 UTF-8；请求体和响应体都是 JSON（`Content-Type: application/json`）。
- 时间字段：ISO 8601 字符串（如 `2026-09-30T02:15:00`），为 UTC 时间，**不带时区后缀**。

## 接口一览

| 方法 | 路径 | 说明 | 必须带 Token |
|---|---|---|---|
| GET | [`/api/v1/query`](#get-apiv1query) | 查询单词释义 | 否（服务端开启「开放使用」时） |
| GET | [`/api/v1/suggest`](#get-apiv1suggest) | 前缀联想 | 否（同上） |
| GET | [`/api/v1/dictionaries`](#get-apiv1dictionaries) | 可用词典列表 | 否（同上） |
| GET | [`/api/v1/vocab`](#get-apiv1vocab) | 生词本列表 | 是 |
| POST | [`/api/v1/vocab`](#post-apiv1vocab) | 收藏单词 | 是 |
| DELETE | [`/api/v1/vocab/{item_id}`](#delete-apiv1vocabitem_id) | 删除生词 | 是 |

---

## 通用约定

### 鉴权

在请求头中携带 API Token：

```
Authorization: Bearer sk-xxxxxxxxxxxxxxxx
```

API Token 以 `sk-` 开头，长期有效，直到被禁用、重新生成或删除。获取方式：

- **用户 Token**：登录网页后在「个人设置」中自助分配。它以该用户的身份调用：可用词典跟随该用户的设置，生词本就是该用户在网页上的生词本。
- **普通 Token**：由管理员在后台创建。它有自己独立的可用词典设置和独立的生词本，与任何网页用户都不相通。

重新分配或重新生成 Token 后，旧值立即失效。

### 「开放使用」模式

服务端管理员可以开启「开放使用」（默认关闭）：

- 开启时，查询类接口（`query`、`suggest`、`dictionaries`）可以不带 Token 调用，按 IP 限流，可查全部已启用的词典。
- 关闭时，不带 Token 调用这些接口返回 `401`。
- 生词本接口（`/api/v1/vocab*`）**始终**要求 Token，不受此设置影响。

### 错误响应格式

业务错误统一返回：

```json
{
  "code": "not_found",
  "message": "生词不存在",
  "detail": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | string | 机器可读的错误码，见[错误码速查](#错误码速查) |
| `message` | string | 面向用户的中文说明，可直接展示 |
| `detail` | string \| null | 补充信息，多数情况为 `null` |

请求参数校验失败（缺少必填参数、类型不对、超出长度）时由框架返回 `422`，格式不同：

```json
{ "detail": [ { "loc": ["query", "word"], "msg": "Field required", "type": "missing" } ] }
```

### 通用错误

以下错误适用于所有接口，后文各接口的「错误」一栏不再重复列出：

| 状态码 | code | 触发条件 |
|---|---|---|
| 401 | `unauthorized` | 生词本接口未携带 Token；Token 无效（不存在或已被重新生成）；「开放使用」关闭时匿名调用查询接口 |
| 403 | `forbidden` | Token 已被禁用；用户 Token 所属账号已被禁用 |
| 422 | —（框架格式） | 请求参数校验失败 |
| 503 | `maintenance` | 服务正在启动或升级，响应头带 `Retry-After: 5`，稍后重试即可 |

### 限流

查询类接口（`query`、`suggest`、`dictionaries`）共用一个计数，超出后返回 `429 rate_limited`，响应头 `Retry-After` 给出建议等待的秒数。生词本接口不限流。

| 调用方式 | 计数方式 | 默认限额 | `Retry-After` |
|---|---|---|---|
| 带 Token | 每个 Token 每天 | 1000 次/天；管理员为该 Token 单独设置了上限时以它为准 | 距离次日零点的秒数 |
| 匿名（开放使用） | 每个 IP 每分钟 | 60 次/分 | 距离下一分钟的秒数 |

默认限额可由管理员在系统设置中调整。

### 分页

分页接口使用 `page`（从 1 开始，默认 1）与 `page_size`（默认 20，上限 100，超出按 100 处理），返回：

```json
{ "items": [ ... ], "total": 57, "page": 1, "page_size": 20 }
```

注意返回的 `page_size` 是请求里传入的原值，不是截断后的值。

### 数据结构

#### VocabItem（生词）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 生词 ID |
| `word` | string | 单词 |
| `phonetic` | string \| null | 音标 |
| `definition` | string \| null | 收藏当时的释义快照（HTML）。词典之后被修改或删除都不影响它 |
| `note` | string \| null | 备注 |
| `dictionary_id` | int \| null | 来源词典 ID；词典被删除后为 `null` |
| `dictionary_name` | string \| null | 来源词典名快照，词典被删除后仍保留 |
| `created_at` | datetime | 收藏时间 |

#### Dictionary（词典简要信息）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 词典 ID |
| `name` | string | 词典名称 |
| `lang_from` | string | 源语言（如 `en`、`zh-Hans`、`ja`） |
| `lang_to` | string | 目标语言 |

---

## GET `/api/v1/query`

查询单词，返回各词典的释义。

**鉴权**：API Token；服务端开启「开放使用」时可匿名。

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `word` | string | 是 | — | 要查询的词 |
| `dict` | string | 否 | — | 逗号分隔的词典 ID，如 `3,7`。非数字项被忽略；全部无效时视为不限制 |
| `from` | string | 否 | — | 源语言，只查该源语言的词典（配合 `to` 可进一步限定目标语言） |
| `to` | string | 否 | — | 目标语言，仅在指定了 `from` 时生效 |
| `full_style` | bool | 否 | `false` | `true` 返回词典原始 HTML 释义；`false` 返回去掉 HTML 的纯文本 |
| `all_langs` | bool | 否 | `false` | `true` 时全部可用词典一起参与查询，不做语言路由 |

**词典选取规则**：

1. 只在已启用、且在调用方「可用词典」范围内的词典中查询。
2. 指定了 `dict` 时只查这些词典；否则指定了 `from` 时按语言过滤。
3. 两者都没指定时自动识别输入语言：先查语言一致的词典，都没命中时再查其他语言的词典，这类结果的 `lang_match` 为 `false`。
4. 繁简、全角半角变体会一并查询；精确查不到时回退为前缀匹配。

**返回**

```json
{
  "results": [
    {
      "id": 1024,
      "dictionary_id": 3,
      "dictionary_name": "牛津高阶英汉双解词典",
      "word": "apple",
      "phonetic": "ˈæpl",
      "definition": "n. 苹果 ...",
      "extra": null,
      "lang_from": "en",
      "lang_match": true
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 词条 ID（同一词典中可能有多条同名词条） |
| `dictionary_id` / `dictionary_name` | int / string | 来源词典 |
| `word` | string | 词头 |
| `phonetic` | string \| null | 音标 |
| `definition` | string | 释义（纯文本或 HTML，取决于 `full_style`） |
| `extra` | object \| null | 词典格式特有的附加数据（如 ECDICT 的标签、词频） |
| `lang_from` | string \| null | 该词典的源语言 |
| `lang_match` | bool | 该词典语言是否与输入一致，见上文规则 3 |

查不到时返回 `{"results": []}`，状态码仍为 200。

`full_style=true` 时，HTML 释义中的图片、音频、CSS 等资源以 `/dict-res/{dictionary_id}/res/...` 形式的**站内绝对路径**引用，不带域名；在其他页面或客户端中渲染时，需要拼上服务的基础地址。这些资源无需鉴权即可访问，并允许跨域加载。生词的 `definition` 快照同理。

**错误**：`429 rate_limited`（超出 Token 每日次数或匿名每分钟次数）。

## GET `/api/v1/suggest`

按前缀联想词头。

**鉴权**：同 `/api/v1/query`，并与它共用限流计数。

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `prefix` | string | 是 | — | 前缀 |
| `limit` | int | 否 | 10 | 返回数量，上限 50 |
| `dict` | string | 否 | — | 逗号分隔的词典 ID |

**返回**：`{"words": ["apple", "applet", "application"]}`

**错误**：`429 rate_limited`。

## GET `/api/v1/dictionaries`

调用方可用的已启用词典列表，按后台排序返回。

**鉴权**：同 `/api/v1/query`，并与它共用限流计数。

**返回**：`Dictionary[]`

**错误**：`429 rate_limited`。

## GET `/api/v1/vocab`

当前 Token 的生词本列表，按收藏时间倒序。

**鉴权**：API Token（必须，不受「开放使用」影响）。用户 Token 读取该用户的网页生词本，普通 Token 读取自己独立的生词本。

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `search` | string | 否 | — | 按单词模糊搜索 |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数，上限 100 |

**返回**：分页结构，`items` 为 `VocabItem[]`。

## POST `/api/v1/vocab`

收藏单词。服务端从词典中查出当前释义与音标，作为快照保存；客户端不能自行提交释义。

**鉴权**：API Token（必须）。

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `word` | string | 是 | 1–255 字符 |
| `dictionary_id` | int | 否 | 来源词典。省略时按查询规则取第一个命中的词典 |
| `note` | string | 否 | 备注 |

**返回**：新建的 `VocabItem`。

**错误**

| 状态码 | code | 触发条件 |
|---|---|---|
| 404 | `not_found` | 指定词典中找不到该词（「该词典下未找到该单词，无法收藏」）；未指定词典且所有词典都找不到（「未找到该单词的释义，无法收藏」） |
| 409 | `conflict` | 同一词典的同一个词已收藏过；生词本已达管理员设置的条数上限 |

## DELETE `/api/v1/vocab/{item_id}`

删除一条生词。

**鉴权**：API Token（必须）。

**返回**：`{"ok": true}`

**错误**：`404 not_found`（生词不存在，或不属于当前 Token）。

---

## 错误码速查

| HTTP 状态码 | code | 含义 |
|---|---|---|
| 401 | `unauthorized` | 缺少 Token、Token 无效，或「开放使用」关闭时匿名调用 |
| 403 | `forbidden` | Token 或其所属账号已被禁用 |
| 404 | `not_found` | 找不到要收藏的单词；生词不存在或不属于当前 Token |
| 409 | `conflict` | 重复收藏；生词本已达上限 |
| 422 | —（框架格式） | 请求参数校验失败，响应体为 `{"detail": [...]}` |
| 429 | `rate_limited` | 超出调用次数限制，参考 `Retry-After` 响应头 |
| 503 | `maintenance` | 服务启动或升级中，参考 `Retry-After` 响应头（5 秒） |
