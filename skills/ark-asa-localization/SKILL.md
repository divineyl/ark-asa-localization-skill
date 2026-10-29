---
name: ark-asa-localization
description: "Use when localizing ARK Survival Ascended (ASA) Windows mods, inspecting their cooked text, building Chinese localization targets or diagnosing translation packages and installers. Not for ASE legacy asset patching or gameplay changes."
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

默认构建只采用显式键；探索无键文本时，在 build 中显式增加 `--crc-candidates`，必要时增加 `--namespace-aliases`，并将包标为研究测试版。非 ASCII 原文 CRC 尚无案例证明；需提供有依据的源指纹，不能用译文生成指纹。详细输入字段见格式参考。

用户交付包含 `install.ps1`、`manifest.json`、`install/uninstall/detect.bat`、译文及离线记录。不会修改原模组，也不会附带 V9.9 底包、字体或 DLL。无需为每个模组替换脚本源码。
