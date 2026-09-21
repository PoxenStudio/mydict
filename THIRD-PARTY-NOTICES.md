# 第三方依赖声明（THIRD-PARTY-NOTICES）

本项目代码以 [MIT License](./LICENSE) 开源。以下列出运行时实际随镜像分发的直接依赖及其许可证类型，供合规审计参考。版本号对应 `backend/requirements.txt` 与 `frontend/package.json` 中锁定的版本；间接依赖遵循 pip/npm 各自的依赖解析，未逐一列出——如需完整依赖闭环（SBOM），可用 `pip-licenses`（后端）、`license-checker`（前端）重新生成。

## 后端运行时依赖（Python，见 `backend/requirements.txt`）

| 包 | 版本 | 许可证 |
|---|---|---|
| APScheduler | 3.11.3 | MIT |
| Mako | 1.4.1 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| PyJWT | 2.13.0 | MIT |
| PyYAML | 6.0.3 | MIT |
| SQLAlchemy | 2.0.52 | MIT |
| alembic | 1.13.3 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| bcrypt | 4.3.0 | Apache-2.0 |
| cachetools | 5.5.2 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD-3-Clause |
| dnspython | 2.8.0 | ISC |
| email-validator | 2.3.0 | Unlicense |
| fastapi | 0.115.14 | MIT |
| greenlet | 3.5.5 | MIT AND PSF-2.0 |
| h11 | 0.16.0 | MIT |
| httptools | 0.8.0 | MIT |
| idna | 3.19 | BSD-3-Clause |
| mdict-utils | 1.3.14 | MIT |
| opencc-python-reimplemented | 0.1.7 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pydantic_core | 2.46.5 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| starlette | 0.46.2 | BSD-3-Clause |
| tqdm | 4.70.0 | MPL-2.0 AND MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.3 | Apache-2.0 |
| tzlocal | 5.4.4 | MIT |
| uvicorn | 0.32.1 | BSD-3-Clause |
| watchfiles | 1.2.0 | MIT |
| websockets | 17.1 | BSD-3-Clause |
| xxhash | 4.0.1 | BSD-2-Clause |

## 前端运行时依赖（打包进构建产物，见 `frontend/package.json` dependencies）

| 包 | 版本 | 许可证 |
|---|---|---|
| axios | 1.20.0 | MIT |
| element-plus | 2.14.5 | MIT |
| pinia | 4.0.3 | MIT |
| vue | 3.5.42 | MIT |
| vue-router | 4.6.4 | MIT |

前端 `devDependencies`（Vite、TypeScript、ESLint、Prettier 等构建期工具）不随构建产物分发，未在此列出。

## 词典数据（不随代码仓库分发）

- 项目本身不打包任何词典数据文件；管理员通过后台"导入词典"自行下载并导入 MDict/StarDict/ECDICT 格式的词典文件，数据版权与许可由各自来源约束。
- [ECDICT](https://github.com/skywind3000/ECDICT)（skywind3000）：CC-BY-4.0，使用时需按其仓库要求署名。
- MDict/StarDict 词典文件版权归各自制作者/出版方所有，部署方需自行确认下载来源的授权范围。
- `scripts/chinese_dictionary_to_ecdict.py` 转换脚本面向 [mapull/chinese-dictionary](https://github.com/mapull/chinese-dictionary)（MIT License）的公开 JSON 数据结构编写，脚本本身随本仓库以 MIT 发布；是否使用该数据源、以及转换产出数据的后续分发，由部署方自行决定并遵循原数据源的许可条款。
