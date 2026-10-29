# 实际案例和可复核材料（2026-10-28）

以下为维护者在 2026-10-28 完成的历史离线审计记录。公开仓库保留输入哈希、版本、统计及材料文件名，原模组、语言基线和完整私人工作目录不随项目分发。历史记录不能仅凭仓库内容独立重跑；取得对应版本的合法输入后可按流程重新核验。仓库自动测试使用合成样本。**两个案例均未进行 ASA 客户端游戏测试。**

## Awesome Teleporters! 950914

历史案例标识：`ASA_950914_AwesomeTeleporters_20261027`。

原件 `950914_6897263.zip`，SHA-256 `34c684d90fb3d872e6640aac414d5fd331647660bcaa05f4a0642184cbdad585`；197 文件。VersionName `59BF457549EC3637972B7D9578D19F6F`、SDKVersion 742496。ZIP 中有已解出 Zen chunks 及 PAK/IoStore 资源。ASE whole-asset profile 不适用。

复核材料：`source_manifest.json`、`inventory/ftext_raw.json`、`inventory/ftext_bytecode.json`、`translations.json`、`build_standalone.py`、`standalone-v1/verification.json` 与 `records.json`、`installer/install.ps1` 和 `test_installer.py`。

独立目标 AT950914：129 条不同原文、343 个身份，其中 74 observed-key、74 namespace alias、195 source CRC 候选。原文翻译总表 136 条，独立目标省略一部分通用身份，因此不能把表条数直接当成包内不同原文数。三个 LocRes 及一个 LocMeta；PAK 50,022 bytes。

早期约 127 MB 的 ZIP 包含 V9.9 底包；约 5.7 MB 的追加 ZIP 仍带全量语言基线。它们说明体积组成，不证明独立目标必然在 ASA 加载。不能把社区 V9.9 称作游戏必需的通用底包。

## Barsboldia 1056795

历史案例标识：`ASA_1056795_Barsboldia_20261027`。

原件 `Barsboldia.zip`，SHA-256 `10bdc70663ef04f5b5c8ec77ec481c6690b1059707b326f8b833cd154c430a13`；6 文件。VersionName `55DCDB1F4F7D9F45A187F9B0AAAC75CE`、SDKVersion 805383。ZIP 主体是 .ucas/.utoc，retoc verify 通过，354 packages 解出供只读检查。

复核材料：`source_manifest.json`、`inspect_source.py`、`inventory_text.py`、`inventory/*.json`、`translations.json`、`build_localization.py`、`test_localization.py`、`build-v1/verification.json` 与 `records.json`、`package_release.py`、`installer/test_installer.py`。

52 条不同原文、148 个身份：8 observed-key、8 namespace alias、132 source CRC 候选。8 条带键帮助在 HUD 中；另外 44 条生成候选。目标 Bars1056795，PAK 19,147 bytes。原有 Bars 构建/安装测试 3+13 项记录通过；它们不是游戏加载测试。

扫描时非重叠零字节模式曾漏掉 HUD FText；重叠扫描后找到。不能把“第一次扫描 0 个键”当作不存在键的证明。原文中数值百分比需要专门校验，不能用支持空格 flag 的 printf 正则误判英文 prose。

## 本 skill 的复核

历史开发审计标识：`ASA_skill_20261028`。维护者的 `audit_cases.py` 和 `case-audit.json` 记录本地复核过程；它们依赖未公开的案例原件，不属于公开仓库的可移植测试集。

- 原 ZIP 哈希和 197 + 6 个原文件逐字节对照，保持不变。
- 新外部 CityHash API 对照两例三个文化共 1,029 + 444 个身份的原 key/namespace hash；另比较 50,332 个已有基线身份。基线只读，未复制进 skill。
- 新 CLI 对 Barsboldia 重新扫描、建立定位审稿清单并构建；52/148 与旧 records 的 namespace/key/source/translation 完全一致，独立导出和封包回读通过。
- Windows 临时目录的通用清单安装/卸载与 BAT 整链测试通过；真实游戏目录没有被安装或改动。
- 基线行为演练已经正确拒绝将 runtime_tested=false 的包宣称正式可用；新 skill 的价值是提供可执行、可迁移且明确边界的工具，不伪造“无 skill 必然失败”。最终演练与测试结果另见 [本次验证记录](validation-results.json)。

上述 hash 相同、文件可解析和语义清单相同，均不能代替实际 ASA 的挂载、目标加载、字体和屏幕文本验证。
