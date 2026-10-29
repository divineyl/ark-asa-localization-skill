# 来源、依赖与分发范围

本仓库原创脚本、文档和合成测试数据按 [MIT License](LICENSE) 发布。MIT 授权不覆盖游戏、模组、字体、社区语言底包、外部工具或其名称和商标。项目与 Studio Wildcard、Epic Games 及模组作者没有官方关联。

## 外部依赖，不随仓库或技能 ZIP 分发

- [python-cityhash](https://github.com/escherba/python-cityhash)：构建依赖固定 `cityhash==0.4.10`；上游 [MIT LICENSE](https://github.com/escherba/python-cityhash/blob/master/LICENSE) 同时提示嵌套代码的独立版权。本项目调用公开 API，没有复制实现。
- [repak v0.2.3](https://github.com/trumank/repak/releases/tag/v0.2.3)：上游 MIT / Apache-2.0。用作 PAK 封装和独立回读工具，没有把可执行文件、库或源码收入项目。
- [retoc v0.1.5](https://github.com/trumank/retoc/releases/tag/v0.1.5)：上游 MIT，Copyright 2025 Truman Kilen and Archengius。仅在处理 IoStore 时自行取得并调用。其运行时可能取得 Oodle DLL；本项目不分发该 DLL，也不把 retoc 许可扩展到该 DLL。
- [UnrealLocres 1.1.1](https://github.com/akintos/UnrealLocres/releases/tag/1.1.1)：用于独立读取 LocRes。2026-10-28 审查根目录未发现 LICENSE；本项目没有确认可再分发许可，故不附带它的源码或程序。需要外部工具整链验证时从上游获取；普通源码测试可在缺少工具时明确报告跳过。

版本、输入来源与校验值见 [工具来源](https://github.com/divineyl/ark-asa-localization-skill/blob/main/skills/ark-asa-localization/references/provenance.md)。CI 中下载的外部程序只在临时测试环境调用，不进入 release ZIP 或测试产物。

## 格式参考与案例

资源格式参考包括 Epic 文档、UE 参考实现和独立工具读写结果。`asa_resources.py` 是本项目独立编写的序列化实现，不含 UE 源码，也未复制许可未确认的 `ark-ascended-fr` 研究脚本。ASA 定制运行时的加载行为仍需实测。

Awesome Teleporters! 与 Barsboldia 仅提供历史审计统计、版本和哈希；原 ZIP、模组资源、全量译文和社区语言基线均不在仓库内。测试运行时自行合成最小二进制样本，不包含游戏素材。历史案例统计不是可由公开仓库单独重跑的证明；需要自行取得对应版本输入后核验。

用户制作的汉化包应保留本工具脚本的 MIT 许可。模组资产与翻译内容的分享权限需依据各自来源；本仓库许可证不授予这些第三方内容的再分发权。
