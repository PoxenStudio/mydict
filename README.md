# My Dictionary Service
[![GitHub License](https://img.shields.io/github/license/poxenstudio/mydict)](https://github.com/poxenstudio/mydict/blob/main/LICENSE)
![GitHub stars](https://img.shields.io/github/stars/PoxenStudio/mydict.svg?logo=github)
![GitHub commit activity](https://img.shields.io/github/commit-activity/w/PoxenStudio/mydict?logo=github)

<p align="center">
  <img src="document/logo.png" alt="logo" />
</p>

一个可用 Docker 一键部署的自托管词典服务：既提供带 Token 鉴权的查询/收藏 API 给第三方调用，也提供一个开箱即用的 Vue3 网页词典——查询、生词本、深浅主题都有；管理员可在后台导入 MDict/StarDict/ECDICT 三种格式的词典（含英汉、汉英、汉语单语词典），管理 Token/用户、查看用量统计、调整系统设置。

## UI

用户UI
<p align="center">
  <img src="document/main_ui.png" alt="User UI" />
</p>

后台管理UI
<p align="center">
  <img src="document/admin_ui.png" alt="Admin UI" />
</p>

## 功能特性

- **词典导入**：支持 MDict（`.mdx`+`.mdd`）、StarDict（`.ifo/.idx/.dict`）、ECDICT（CSV）三种格式；网页上传或服务器目录导入两种方式，后者适合 GB 级大文件。
- **对外 API**：`Authorization: Bearer <token>` 鉴权，查询/联想/词典列表/生词本增删查；管理员可开启「开放使用」允许匿名查询（按 IP 限流）。
- **网页词典**：标准查询体验，登录后可收藏生词、查看生词本；访客模式可配置。
- **管理后台**：Token 管理、用户管理、用量统计（按 Token/用户/日期/来源，支持 CSV 导出）、系统设置（限流阈值、开放使用开关等）。
- **单容器部署**：前端构建产物由后端 FastAPI 直接托管，SQLite 内置数据库，无需额外部署数据库/缓存服务。

## 推荐词典数据源

项目本身不附带任何词典数据，需要部署后自行下载并在后台导入：

| 方向 | 推荐来源 | 说明 |
|---|---|---|
| 英汉 | [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)（CC-BY-4.0） | 直接是 ECDICT 格式 CSV，后台选择「ECDICT」格式即可导入 |
| 汉英 | [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict) | 社区有多种 MDict/StarDict 格式转制版本，按对应格式导入 |
| 汉语（单语） | [mapull/chinese-dictionary](https://github.com/mapull/chinese-dictionary)（MIT License） | 字/词/成语 JSON 语料，需先用仓库自带的 `scripts/chinese_dictionary_to_ecdict.py` 转换成 ECDICT 格式 CSV 再导入，用法见脚本内说明 |

## Docker 部署

```bash
# 1. 构建镜像
docker build -t mydict .

# 2. 启动（数据全部持久化在宿主机 ./data 目录）
docker run -d --name mydict -p 8000:8000 -v $(pwd)/data:/data mydict
```

或使用 `docker compose up -d`（等价于上面两步，配置见 `docker-compose.yml`）。

所有配置项均有合理默认值，无需任何 `.env` 文件即可直接运行。如需覆盖（如自定义限流阈值），执行 `cp .env.example .env` 后取消对应行注释修改，再启动时加上 `--env-file .env`（`docker compose` 会自动读取同目录下的 `.env`，存在则用，不存在则跳过)。

启动后访问 `http://<host>:8000` 即可。

## 首次初始化

1. 访问 `http://<host>:8000/admin/setup`，设置管理员用户名密码（仅首次部署会出现该页面）。
2. 用管理员账号登录后台 → 「词典管理」导入至少一部词典 → 「启用」。
3. 如需给第三方调用方分配 API Token：「Token 管理」→「新建 Token」，创建后立即复制保存（明文只展示一次）。
4. 如需允许未登录访客直接查询：「系统设置」→ 打开「开放使用」。

## 词典导入的两种方式

- **网页上传**：后台「词典管理」→「导入词典」→「上传文件」，适合中小体积文件（可多选，如 `.mdx`+`.mdd`）。
- **服务器目录导入**：把词典文件通过 `docker cp`（或挂载卷）放进容器的 `/data/dicts` 目录，再到「导入词典」→「从服务器目录导入」勾选文件名即可，不经过浏览器上传，适合 GB 级大文件。

```bash
docker cp ./oxford.mdx mydict:/data/dicts/
docker cp ./oxford.mdd mydict:/data/dicts/
```

## 常见问题

**忘记管理员密码怎么办？**

```bash
docker exec -it mydict python -m app.cli reset-admin-password --username admin
```

按提示输入新密码即可（不接入邮件服务，找回密码均走此命令行方式）。

**数据存在哪里，怎么备份？**

容器内 `/data` 目录（SQLite 数据库、词典文件、自动生成的 JWT 密钥、运行日志均在其中），备份/迁移只需复制该目录（如启动命令中挂载的宿主机 `./data`）。运行日志在 `/data/logs/mydict.log`，按 5MB 自动滚动、保留最近 5 份，登录成功/失败等事件也会写进去，容器内 `docker logs` 能看到同样的内容。

**升级镜像会不会丢数据？**

不会。`/data` 是独立的挂载卷，重新构建/替换镜像并用相同的 `-v` 挂载启动即可，容器启动时会自动执行数据库迁移。

**查询接口一直返回 401？**

默认「开放使用」是关闭的，查询类接口必须携带有效 Token（或以登录用户身份访问网页版）；如需允许匿名查询，去后台「系统设置」打开「开放使用」。

## License

代码以 [MIT License](./LICENSE) 开源，第三方依赖许可证清单见 [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md)。词典数据本身不随本仓库分发，版权与许可以各自数据源为准。
