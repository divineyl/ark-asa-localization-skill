# 贡献指南

欢迎帮助本项目在更多真实输入和 ASA 版本上建立可复现的证据。优先提交具体问题、最小复现、修复和实测记录；“所有界面都成功”“应该兼容 UE5”不能代替观察结果。

## 报告问题

使用 [问题模板](.github/ISSUE_TEMPLATE/bug_report.md)，提供仓库 commit、Python/PowerShell/Windows 版本、实际命令、脱敏错误及复现步骤。外部工具要附版本、上游来源和 SHA-256。

尽可能用合成的最小输入复现。原模组通常不属于本项目，未经许可不要提交 `.uasset/.umap/.pak/.utoc/.ucas`、完整 ZIP、底包、字体或 DLL。不要公开令牌、账号、服务器口令、存档、私人用户名/绝对路径。截图和日志也需要检查。

## 提交代码或文档

1. 从当前默认分支创建自己的分支，解释具体问题、触发条件与预期行为。
2. 保持 `skills/ark-asa-localization/SKILL.md` 简洁，把格式和条件细节放入 references，把重复处理放入 scripts。
3. 脚本不能依赖维护者本机的目录、原模组或私人缓存。修复有意义的行为问题时，补充能运行真实脚本、检查结果的测试。
4. 按[快速上手](docs/quickstart.md)运行相关测试，并执行 `python -B tools/verify_repo.py`。Windows 上设置 `ASA_TEST_TOOLS` 后可用 `python -B tools/verify_repo.py --full --require-no-skips` 检查完整链路。明确报告平台与外部工具导致的跳过，不能只给一个模糊的“全通过”。
5. PR 描述说明变化、验证方式和局限；如果使用了外部代码，附来源与可兼容的许可，不粘贴许可不明的研究代码。

以小而独立的改动为宜。不要借语言修复改变 gameplay、事件绑定或资产身份。安装器变化必须复核备份、所有权、个人修改保留和失败回退，不能在测试时偷偷使用真实游戏目录。

提交贡献表示你有权按仓库 [MIT License](LICENSE) 许可该贡献。第三方依赖的原有许可仍然适用，参见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 贡献真实游戏测试

使用 [游戏实测模板](.github/ISSUE_TEMPLATE/runtime_report.md)，记录：

- 仓库版本/commit、汉化包 SHA-256、ASA build、模组 ID 和 VersionName。
- 语言、地图、单机/服务器、其他覆盖包和具体触发操作。
- PAK 挂载、目标加载、每条实际显示、相关功能、重启与卸载的观察证据。
- 显式键、CRC 候选和命名空间别名各自的命中、未命中和未测项。

`runtime_tested=false` 的生成报告保持原样。将实测写成额外报告，关联到原包哈希；不要编辑构建报告来制造已测试状态。没有日志就写“未观察到加载日志”，没有测试到的界面就写“未测”。

真实客户端的一次成功只覆盖该版本与场景。维护者会复核证据后更新适用说明，继续保留不同模组和版本的未知项。
