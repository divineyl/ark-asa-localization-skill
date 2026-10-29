# v0.1.0-alpha.1 发布验证

本记录日期：2026-10-29。验证平台为 Windows、Python 3.12、Windows PowerShell 5.1。当前版本仍为实验版，未进行 ASA 客户端游戏验证。

## 本地执行结果

- skill-creator `quick_validate.py`：通过。
- `python -B tools/verify_repo.py --full --require-no-skips`：31 项通过，0 失败、0 错误、0 跳过。其中 skill 行为测试 24 项，公开仓库与发布工具测试 7 项。
- 外部工具使用 repak v0.2.3、UnrealLocres 1.1.1；独立读取、PAK 封装回读和已打包 BAT 的检测/安装/卸载均实际执行。
- 在相同源码上构建两份发布 ZIP，成员内容、CRC 和整个 ZIP 的 SHA-256 一致。
- 模拟客户端均为临时目录；没有修改真实游戏目录。ZIP 仅包含 skill 源码、参考文档、测试和许可文件。

本次公开发布前补充了两项安装所有权回归测试和一项显式身份优先测试：预先存在的配置块不因标记而被认领；重新复制的缺失 PAK 被正确记录为自有；同一个身份的真实观察证据优先于生成别名。这三项均先复现错误，再验证修复结果。

发布工具测试覆盖确定性 ZIP、拒绝缓存/二进制、禁止覆盖已有产物、损坏链接/语法、个人路径泄露、根目录工作文件隔离、合成示例及工具下载哈希。合成示例的插件 ID/版本也由实际检查输出核对。

## 可复现范围

公开测试只需仓库源码和自行取得的外部工具，不依赖维护者的案例目录。准备方法见[快速上手](quickstart.md)。外部工具缺失时必须记录跳过；严格发布验证使用 `--require-no-skips` 拒绝把跳过当成通过。

[历史案例审计](../skills/ark-asa-localization/references/evidence.md)需要相同版本的模组原件，公开仓库不附带这些原件；历史报告不等同于 CI 复现。

GitHub 托管环境的实际结果以 [Actions](https://github.com/divineyl/ark-asa-localization-skill/actions/workflows/verify.yml) 为准。工作流从上游获取并核对固定版本的外部程序，只上传源码 ZIP 与校验文件。

## 未验证内容

ASA 是否挂载该输出 PAK、是否加载独立语言目标、CRC/命名空间别名是否命中、实际中文字体/布局、服务器文本及玩法功能仍需游戏实测。离线测试通过不支持“适配全部 ASA 模组”或“游戏汉化成功”的结论。
