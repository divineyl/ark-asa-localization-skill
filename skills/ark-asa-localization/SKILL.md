---
name: ark-asa-localization
description: "Use when localizing ARK: Survival Ascended (ASA, 方舟：生存飞升) Windows Steam mods: inspect cooked text, review display strings, build Chinese LocRes targets, package a research-test PAK, or diagnose a translation installer. Triggers include 汉化, 模组翻译, LocRes, and Game.ini localization paths. Not for ASE (方舟：生存进化) legacy asset patching, gameplay edits, font DLL injection, or claiming in-game success without a client test."
---

# 方舟飞升模组汉化

将用户提供的 ASA 模组制作成可追溯的中文语言小包；保留原始资产、内部标识和玩法逻辑。先核对证据，再承诺覆盖范围。附带工具验证文件处理与安装行为，**没有证明 ASA 客户端一定加载独立目标或命中动态文本**。

## 先决定路线

1. **识别输入**：检查 ZIP 安全路径/CRC/SHA-256、`.uplugin` 的模组 ID 和版本、PAK/IoStore 布局。只有 `.uasset` 扩展名不能确认 ASE 格式；未知容器保留原件，报告缺少的工具/数据，不改头伪装格式。下载 ZIP 不是已安装模组。见 [提取与审稿](references/workflow.md)。
2. **提取并审查**：扫描结果均为候选。按文件哈希、位置和类型复核显示项；记录原文、namespace/key 与上下文。保留资源路径、配置键、事件名和按键占位符。不要用原文词典全局覆盖资产；同一句话的不同身份可以有不同译文。
3. **选择身份**：优先采用实际观察并审查的 FText 键。无键文本不能凭空获得确定身份；若任务允许探索，可显式启用 CRC/命名空间别名候选，并分别计数。见 [格式与匹配边界](references/formats.md)。
4. **构建并独立验证**：LocRes v3 + LocMeta v1，独立目标目录，`en/zh/zh-Hans`。原文指纹、目标名、元数据、资源名和文化目录一致；先独立导出再封包回读。V11 PAK 校验通过只是工具结果。见 [工具与来源](references/provenance.md)。
5. **交付与实测**：制作包不自动授权安装到真实游戏。授权安装后退出游戏，检测已安装模组、备份并运行清单驱动安装器；保留个人配置与其他小包。见 [安装清单](references/installer.md) 与 [验证和游戏测试](references/validation.md)。

## 证据不能合并成一个“成功”

- `observed-key`：资产中的键已观察；还不表示游戏使用该显示路径。
- `source-crc-candidate` / `namespace-alias-candidate`：匹配假设，不能按命中数汇报。
- `offline_checks`：文件、独立导出、封包和源件检查通过。
- 游戏实测：须另记 ASA/模组版本、语言、挂载/加载证据、逐项显示和功能结果。脚本始终输出 `runtime_tested=false`，不得手动改成 true 代替测试。

两个历史案例都缺少游戏实测。具体数字、复核路径与适用限制见 [案例证据](references/evidence.md)。遇到字体缺字、服务器直接发送英文、其他覆盖包、存档自定义文本，应分别诊断，不能自动归因于词条遗漏。

## 硬性约束

这些限制来自当前脚本。不要发明参数，也不要手工改报告来绕过。

- 写出的 JSON 和目录必须尚不存在。这包括 `inspect-zip` 的 `--output` 与 `--extract`、`inventory --output`、`build --output`、`package --output`，以及由目录名替换最后一个后缀得到的同级 `.zip`。目录名不要包含 `.`，否则 `delivery.v1` 会变成 `delivery.zip`。失败结果留在原处，换新路径重试。
- 没有 `--max-unpacked`。ZIP 展开上限是 4 GiB；更大的合法包只能在审过清单后调用 Python API。
- `inspect-zip` 会校验 CRC，失败即拒绝。JSON 不含 CRC，也不含整包字节大小。成员字段是 `path`、`size`、`sha256`；插件字段是 `path`、`mod_id`、`name`、`version`、`sdk`。
- `inventory` 只扫描 `.uasset` 和 `.umap`。要进入构建，同一条必须同时有布尔值 `display: true`、非空 `translation` 和 `review_note`，并保留定位字段。只改 `display`，或把它写成字符串 `"true"`，该条会被跳过。若因此没有任何审稿条目，命令失败，不会生成空包。
- `validate-plan` 不写文件。成功时向标准输出打印 `{"reviewed": N}`。可捕获的失败写到标准错误，前缀为 `Error:`。
- 脚本不自动下载工具。`tools.json` 只检查 `repak` 与 `unreal_locres`；路径相对当前工作目录，不是相对脚本文件。retoc 按参考命令手工调用，不写入该清单。
- 省略 `-Action` 时 `install.ps1` 默认执行 Install。未授权不运行；授权后命令行也先写 `-Action Detect`。成品 `说明.txt` 要求先检测，不能代替这条参数。
- 构建拒绝名为 ShooterGame 或 Engine 的目标（忽略大小写）。始终保留脚本写出的 `runtime_tested=false`。

## 工具入口

Python 3.10+；检查/提取仅用标准库。构建还需外部 `cityhash==0.4.10`、repak、UnrealLocres。二进制与第三方实现不随 skill 分发。外部工具由本地 `tools.json` 指定路径、版本、上游 URL 和 SHA-256，脚本不自动下载。

从 skill 目录运行以下命令，输出使用新的工作目录：

```powershell
python -B scripts/asa_localize.py inspect-zip --input "mod.zip" --output "work/source.json" --extract "work/original"
python -B scripts/asa_localize.py inventory --input "work/extracted" --output "work/plan.json"
python -B scripts/asa_localize.py validate-plan --source "work/extracted" --plan "work/plan.json"
python -B scripts/asa_localize.py build --source "work/extracted" --plan "work/plan.json" --target Mod123456 --tools "tools.json" --output "work/build"
python -B scripts/asa_localize.py package --build "work/build" --tools "tools.json" --mod-id 123456 --mod-version "observed-version" --mod-name "Example" --output "work/delivery"
```

`original` 为完整解压副本；`extracted` 是已解出的 cooked chunks。若 ZIP 内已有 `.uasset`，可直接对相应原件目录扫描；若只有 IoStore，先按工具参考解包。审稿时仅在确认显示项上添加 `display: true`、`translation`、`review_note`，保留定位字段和原文。无需翻译所有提取结果。

默认构建只采用显式键；探索无键文本时，在 build 中显式增加 `--crc-candidates`，必要时增加 `--namespace-aliases`，并将包标为研究测试版。`--namespace-aliases` 只给空 namespace 的显式键附加 GraphLiteral 别名。非 ASCII 原文 CRC 尚无案例证明；需提供有依据的源指纹，不能用译文生成指纹。plan 字段见[工作流](references/workflow.md)，源指纹见[格式说明](references/formats.md)。

用户交付包含 `install.ps1`、`manifest.json`、`install/uninstall/detect.bat`、译文及离线记录。不会修改原模组，也不会附带 V9.9 底包、字体或 DLL。无需为每个模组替换脚本源码。

## 技能包里各文件做什么

- [workflow.md](references/workflow.md)：ZIP 字段、扫描范围和 plan 审稿。
- [formats.md](references/formats.md)：身份、LocRes/LocMeta 和实验边界。
- [provenance.md](references/provenance.md)：外部工具版本、上游和 SHA-256。
- [installer.md](references/installer.md)：清单、默认动作和所有权。
- [validation.md](references/validation.md)：离线测试与游戏实测清单。
- [evidence.md](references/evidence.md)：两个历史案例；都没有游戏实测。
- `scripts/asa_localize.py`：命令入口。`asa_core.py` 只用标准库。`asa_resources.py` 写语言资源，构建时需要 `cityhash==0.4.10`。
- `scripts/install.ps1`：放进用户交付包；制作包时不运行。
