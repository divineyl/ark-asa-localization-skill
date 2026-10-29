# ark-asa-localization

用于 **Windows Steam 版《方舟：生存飞升》（ARK: Survival Ascended，ASA）模组汉化**的 Codex skill。它把文本提取、翻译审稿、语言资源构建、离线验证和安装排查整理成可复用流程，并提供实际可运行的脚本与测试。

**当前是实验性版本。** Awesome Teleporters!（950914）和 Barsboldia（1056795）提供了真实格式与离线验证依据，两个案例均未完成 ASA 游戏内验证。PAK 回读成功、安装器测试通过，都不等于游戏已加载译文。请根据证据判断能交付什么，保留尚未验证的范围。

## 适合做什么

- 检查模组 ZIP、文件哈希与 `.uplugin`，识别已解出的 Zen 资产、PAK 和 IoStore。
- 提取 FText、FString、部分 Blueprint 文本候选，保留来源、位置与显式 namespace/key，辅助人工筛选和翻译。
- 制作独立 LocRes / LocMeta 语言目标，经独立读取、V11 PAK 封包及解包核对后，交付研究测试版小包。
- 使用同一份清单驱动安装器检测客户端和已安装模组，执行备份、安装、卸载与失败回退。

这不是《方舟：生存进化》（ASE）的旧版资产修补工具，也不改玩法逻辑。安装器面向 Windows Steam ASA 客户端；其他商店、主机版、服务器部署不在已验证范围。扫描器不是完整 Unreal 解析器，CRC 与命名空间别名仅是候选匹配。

## 在 Codex 中安装

将下面这段发送给 Codex：

```text
使用 $skill-installer，从 https://github.com/divineyl/ark-asa-localization-skill
安装 skills/ark-asa-localization 子目录中的 skill。
先检查是否已有同名 skill；若已安装，保留本地修改并说明版本差异。
```

**安装的是 `skills/ark-asa-localization` 文件夹，不是整个仓库根目录。** 安装器会选择当前 Codex 的技能位置；本项目开发环境使用 `$CODEX_HOME/skills`，未设置时为 `~/.codex/skills`。安装后尝试调用 `$ark-asa-localization`；若未出现，可重启 Codex。官方说明见 [Build skills](https://learn.chatgpt.com/docs/build-skills)。

安装 skill 只提供流程和脚本，构建依赖需要另行准备。没有 Codex 也可按[命令行快速上手](docs/quickstart.md)使用工具。

## 复制这段，开始汉化

先把方括号内容替换成自己的路径与偏好：

```text
使用 $ark-asa-localization 汉化 Windows Steam 版 ASA 模组。
输入 ZIP：[模组 ZIP 的完整路径]
输出工作目录：[一个新的目录]
语言：简体中文。术语要求：[填写术语表，或写“无，优先沿用游戏常见译名”]。

先检查原件、模组 ID/版本和资源格式，再提取并审查真正的显示文本。
保留 namespace/key、数值、百分比、占位符、换行与富文本标签；不修改内部标识或玩法。
优先显式 FText 身份。无法确定的文本另列，CRC/别名只能标为实验候选。
使用可核验来源和 SHA-256 的工具，独立读取 LocRes 并封包/解包核对。
交付小包、译文对照、工具及源文件证据、离线验证记录、安装/卸载说明和游戏测试清单。
本次只制作交付包，不修改真实游戏目录。没有实际客户端证据时明确写“尚未游戏验证”。
```

更完整的制作、授权安装、排查、模组更新与实测贡献提示词见 [usage-prompts.md](docs/usage-prompts.md)。

## 依赖与验证

- Python 3.10+；检查与候选提取使用标准库。构建使用 `cityhash==0.4.10`，见 [requirements-build.txt](skills/ark-asa-localization/scripts/requirements-build.txt)。
- repak、UnrealLocres 为外部工具；IoStore 解包按需要使用 retoc。自行核验来源、版本和 SHA-256，按[快速上手](docs/quickstart.md)提供 `tools.json`。
- Windows 安装器使用 Windows PowerShell；用户拿到成品包后无需安装 Python。
- 本仓库不携带模组原始资产、完整语言底包、字体、第三方可执行程序或 DLL。[第三方说明](THIRD_PARTY_NOTICES.md)记录许可与使用边界。

测试会真正运行文件处理和安装脚本，在临时模拟目录中检查结果；不会安装到真实游戏。外部工具未配置时，相关测试会显示跳过，不能把它报告成通过。

- [快速上手与测试命令](docs/quickstart.md)
- [测试源码](skills/ark-asa-localization/tests)
- [验证方法与游戏实测清单](skills/ark-asa-localization/references/validation.md)
- [历史案例证据](skills/ark-asa-localization/references/evidence.md)与[本地验证记录](skills/ark-asa-localization/references/validation-results.json)
- [GitHub Actions](https://github.com/divineyl/ark-asa-localization-skill/actions)
- [v0.1.0-alpha.1 发布验证记录](docs/release-validation.md)

## 开源与贡献

项目自有代码和文档采用 [MIT License](LICENSE)。第三方工具、游戏和模组资产仍受各自许可约束。项目与 Studio Wildcard、模组作者及 OpenAI 无隶属关系。

欢迎提交能复现的问题、文本审查改进和带版本信息的真实游戏测试记录。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，不要上传账号凭据、私人路径、存档或未获许可的完整模组资产。
