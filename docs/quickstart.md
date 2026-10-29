# Windows 命令行快速上手

这些命令从**仓库根目录**运行，面向 Windows PowerShell 与 Python 3.10+。先复制或克隆仓库；模组工作文件放到本地 `work`，不要提交到 Git。安装 skill 与准备构建工具是两个步骤；[README](../README.md)提供 Codex 安装方式。

## 1. 准备 Python

```powershell
git clone https://github.com/divineyl/ark-asa-localization-skill.git
Set-Location -LiteralPath .\ark-asa-localization-skill
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\skills\ark-asa-localization\scripts\requirements-build.txt
$asaPython = (Resolve-Path -LiteralPath .\.venv\Scripts\python.exe).Path
$asaCli = '.\skills\ark-asa-localization\scripts\asa_localize.py'
& $asaPython -B $asaCli --help
```

无需激活 venv。`-B` 避免 Python 在 skill 源码旁写入缓存。安装失败时保留 pip 的实际错误，先确认 Python 版本和可用构建依赖。

## 2. 准备外部工具清单

基础 ZIP 检查和候选扫描不需要 repak 或 UnrealLocres。执行 `build` / `package` 时需要两者；处理 IoStore 时还可能需要 retoc。

- repak：查看[本项目已验证的 v0.2.3 上游发布页](https://github.com/trumank/repak/releases/tag/v0.2.3)。
- UnrealLocres：查看[上游仓库](https://github.com/akintos/UnrealLocres)。本项目用其独立导出能力；未确认可再分发许可，因此不附带该程序。
- retoc：查看[本项目已验证的 v0.1.5 上游发布页](https://github.com/trumank/retoc/releases/tag/v0.1.5)。其处理压缩数据时可能另需 Oodle DLL；本项目不分发该 DLL。

这些是历史已验证版本，不是“最新版本”承诺。自行检查来源和许可，将可信程序放在仓库外，或本地忽略的 `local-tools` 目录。不要执行来源不明的下载脚本。

创建本地 `tools.json`。下面是**模板，必须替换路径和 SHA-256**；路径可以相对当前工作目录，建议使用 `/` 避免 JSON 反斜线转义：

```json
{
  "repak": {
    "path": "local-tools/repak.exe",
    "version": "0.2.3",
    "source_url": "https://github.com/trumank/repak/releases/tag/v0.2.3",
    "sha256": "替换为实际文件的64位SHA256"
  },
  "unreal_locres": {
    "path": "local-tools/UnrealLocres-1.1.1.exe",
    "version": "release-1.1.1",
    "source_url": "https://github.com/akintos/UnrealLocres",
    "sha256": "替换为实际文件的64位SHA256"
  }
}
```

读取本地哈希：

```powershell
(Get-FileHash -LiteralPath .\local-tools\repak.exe -Algorithm SHA256).Hash.ToLowerInvariant()
(Get-FileHash -LiteralPath .\local-tools\UnrealLocres-1.1.1.exe -Algorithm SHA256).Hash.ToLowerInvariant()
```

哈希一致只证明文件身份；还应核对可信来源和版本。工具实际执行前会再次核验哈希。详细工具记录见[来源与分发边界](../skills/ark-asa-localization/references/provenance.md)。

仓库也提供可复制的 [tools.example.json](../examples/tools.example.json)，同样需要填写自己的路径。测试准备脚本不是构建命令的自动前置步骤；阅读第三方说明后，自行决定是否获取外部工具。

### 先用合成示例跑通流程

无需真实模组即可检查本地工具链。示例仅包含项目生成的 `Help` 显示文本和 `帮助` 译文，不是可在 ASA 中使用的模组：

```powershell
& $asaPython -B .\examples\create_demo.py --output .\work\demo
& $asaPython -B $asaCli build --source .\work\demo\source --plan .\work\demo\plan.json --target Demo123456 --tools .\tools.json --output .\work\demo-build
& $asaPython -B $asaCli package --build .\work\demo-build --tools .\tools.json --mod-id 123456 --mod-version synthetic-v1 --mod-name '离线合成示例，不能安装到真实游戏（Synthetic demo）' --output .\work\demo-delivery
```

此包只供离线演示，不安装到真实游戏。原模组仍按以下步骤独立核验和审稿。

## 3. 检查 ZIP 并识别格式

把自己获得的模组 ZIP 放到 `work/input/mod.zip`，然后执行：

```powershell
& $asaPython -B $asaCli inspect-zip --input .\work\input\mod.zip --output .\work\source.json --extract .\work\original
```

输出包含 ZIP 哈希、CRC、成员和插件信息；`original` 是完整解压副本，原 ZIP 不变。提取目录必须不存在。拒绝路径逃逸、冲突文件名、加密 ZIP、超限展开等输入；默认展开量上限 4 GiB，合法的大模组需要先审查再按[工作流说明](../skills/ark-asa-localization/references/workflow.md)处理。

根据实际内容选择下一步：

- 已有 `.uasset/.umap`：可从相应目录开始扫描；后缀不证明它是 ASE legacy 格式。
- 有 `.utoc/.ucas`：保持容器配套，先解出工作副本。以实际文件路径替换下面的 `mod.utoc`。
- 只有 PAK：先查工具是否支持其实际版本。不能因为输出使用 repak V11，就认为它支持任意 ASA 原始 PAK；不要改包头强行解析。

IoStore 参考命令（工具路径与文件名按实际情况替换）：

```powershell
& .\local-tools\retoc.exe info .\work\original\mod.utoc
& .\local-tools\retoc.exe verify .\work\original\mod.utoc
& .\local-tools\retoc.exe unpack .\work\original\mod.utoc .\work\extracted
```

保存 info、verify、工具版本及文件哈希。遇到不支持的容器、加密或缺少配套数据时，保留错误与原件，先解决输入条件。

## 4. 扫描、翻译并审稿

下面假设已解出的资产位于 `work/extracted`。如果 ZIP 本来就是散装资产，将 `$asaSource` 改为 `work/original` 下实际资产目录。

```powershell
$asaSource = '.\work\extracted'
& $asaPython -B $asaCli inventory --input $asaSource --output .\work\plan.json
```

所有条目最初为 `display: false`。检查上下文后，仅对真正的显示文本添加以下字段，保留原记录的路径、哈希、位置、类型、原文及 namespace/key：

```json
{"display": true, "translation": "帮助", "review_note": "确认这是 HUD 帮助按钮显示文本"}
```

这是现有条目的增补示例，不能用它替换完整 plan。不要把全部英文候选批量设成显示项；配置键、事件名、对象路径和按键绑定 ID 应保持不变。数值、百分比、占位符、换行、标签和必要空格需要保留。全文审稿要求见[工作流](../skills/ark-asa-localization/references/workflow.md)。

```powershell
& $asaPython -B $asaCli validate-plan --source $asaSource --plan .\work\plan.json
```

校验会重新检查实际源文件和位置。输出的审稿条数不等于游戏覆盖条数；源文件更新后应重新扫描，不能修改旧哈希绕过检查。

## 5. 构建并交付小包

从 `.uplugin` 核实模组 ID、版本和名称，然后填写以下变量。`123456` 和 `Example` 只是示例；目标名应为该模组专用的 ASCII 标识。

```powershell
$asaModId = 123456
$asaModVersion = '替换为uplugin中实际VersionName'
$asaModName = 'Example'
$asaTarget = 'Mod123456'
& $asaPython -B $asaCli build --source $asaSource --plan .\work\plan.json --target $asaTarget --tools .\tools.json --output .\work\build-v1
& $asaPython -B $asaCli package --build .\work\build-v1 --tools .\tools.json --mod-id $asaModId --mod-version $asaModVersion --mod-name $asaModName --output .\work\delivery-v1
```

输出目录必须是新的；重试用 `build-v2` / `delivery-v2`，保留失败输出便于排错。默认只构建审稿后的显式身份。无键文本不会自动变成确定身份；仅在明确研究候选匹配时使用 `--crc-candidates` 或 `--namespace-aliases`，阅读[格式边界](../skills/ark-asa-localization/references/formats.md)并单独统计。

`build` 独立导出 LocRes、比较内容、封装 V11 PAK、解包逐字节核对，并检查原件哈希。`package` 会再次验证当前文件，输出 `delivery-v1` 文件夹及 `delivery-v1.zip`，包含 PAK、manifest、安装/卸载/检测入口、译文和离线验证记录。

**先交付包。** 这些命令不修改真实游戏。生成的 `runtime_tested=false` 是真实状态；不能手工改成 `true` 充当游戏测试。独立目标能否加载、动态文本是否命中、中文显示和功能都需要[游戏实测](../skills/ark-asa-localization/references/validation.md)。

## 6. 在临时目录运行测试

仓库根目录下运行：

```powershell
& $asaPython -B -m unittest discover -s .\skills\ark-asa-localization\tests -v
```

未设置外部工具清单时，完整管线测试会显示 `skipped`。配置后重跑以验证独立工具及打包 BAT：

```powershell
$env:ASA_TEST_TOOLS = (Resolve-Path -LiteralPath .\tools.json).Path
& $asaPython -B -m unittest discover -s .\skills\ark-asa-localization\tests -v
Remove-Item Env:ASA_TEST_TOOLS
```

测试使用合成资产和临时模拟客户端，检查实际文件/配置变化，包括重复安装、卸载、回退、多包共存与 BAT 入口；它们不是游戏测试。请如实记录运行、失败和跳过数量，见[验证说明](../skills/ark-asa-localization/references/validation.md)。

仓库自身的格式、引用与发布文件检查：

```powershell
& $asaPython -B .\tools\verify_repo.py
```

在 Windows 上，准备好外部工具后执行包含仓库检查的完整验证，并要求没有跳过：

```powershell
$env:ASA_TEST_TOOLS = (Resolve-Path -LiteralPath .\tools.json).Path
& $asaPython -B .\tools\verify_repo.py --full --require-no-skips
Remove-Item Env:ASA_TEST_TOOLS
```

维护者可运行 `python -B tools/build_release.py --output dist/ark-asa-localization.zip` 构建源码发布 ZIP 及校验文件。它与为某个模组生成的汉化交付包是不同产物，不包含外部工具或游戏资产。

## 7. 用户授权后安装

用户明确要求安装到真实游戏时，完整解压成品 ZIP，退出飞升，先双击 `detect.bat`。检测报告确认已安装模组；多个客户端需选择目标。然后使用 `install.bat` 安装，`uninstall.bat` 卸载；也可把游戏目录拖到 BAT 上。

需要显式目录时，在解压后的成品包目录运行：

```powershell
$asaGamePath = '填写自己的ASA客户端完整路径'
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Action Detect -GamePath $asaGamePath
```

确认授权和目标后才把 `Detect` 改为 `Install`。安装器保留备份、编码和自有文件记录；详情见[安装器说明](../skills/ark-asa-localization/references/installer.md)。不要把旧 `Game.ini` 整体覆盖回去，也不要因未命中译文而删除官方 PAK。

升级同一模组的小包时，安装记录会核对旧 PAK 哈希，不能用新版清单直接覆盖。保留旧包和备份，获准升级后先用旧包的 `uninstall.bat` 卸载自有内容，再安装新版。若旧文件被手工改过或记录不一致，应先核对差异，不删除记录来绕过保护。
