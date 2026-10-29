# 工具、格式来源与分发边界

工具版本是本次实测版本，不宣称为最新或支持所有 ASA 版本。依赖更新后重跑相同校验。以下程序均从外部路径调用，**skill 不携带二进制、DLL、底包或第三方源码**。

## 已用工具

- [repak v0.2.3](https://github.com/trumank/repak/releases/tag/v0.2.3)：本地 LICENSE-MIT/LICENSE-APACHE 已读；新小包用 V11、mount `../../../` 封包/list/unpack。exe SHA-256 `fcd538e5994b9bb833622d425ae346f4e0692f02d4b0025114a559f9b6286022`。它不能据此被认为支持 Wildcard 输入 PAK V12。
- [UnrealLocres release 1.1.1](https://github.com/akintos/UnrealLocres)：仅用 export 独立读取。exe SHA-256 `b961927f92a8bca928d378a8430e5ea36fed300500b228b184b8d6b61ebb22a1`；发布标签与程序 banner 可能不同，记录二者。2026-10-28 根目录列表未发现 LICENSE，`LICENSE` 请求 404；不推断可分发许可，不复制源码或 exe 到 skill/用户包。
- [retoc v0.1.5](https://github.com/trumank/retoc/releases/tag/v0.1.5)：MIT，Copyright 2025 Truman Kilen and Archengius。Windows release ZIP SHA-256 `cc036b06ad3bdcf7003690b00d82719980c374e48a95bf0654f9959148d263aa`。Barsboldia 解包/verify 通过；报告 ReplaceIoChunkHashWithIoHash、SoftPackageReferences、Oodle、354 packages。工具运行时可能获取或加载 Oodle DLL；本 skill 未审定该 DLL 的分发权，因此也不携带它。
- [python-cityhash](https://github.com/escherba/python-cityhash)，外部构建依赖固定 `cityhash==0.4.10`；[上游 LICENSE](https://github.com/escherba/python-cityhash/blob/master/LICENSE) 为 MIT，并注明嵌套源码可能有各自版权。仅调用 CityHash64 bytes API，不复制库实现。测试时安装在工作 venv，用户交付包不依赖 Python/CityHash。

`asa_resources.py` 为本次新写的资源序列化实现；使用已独立回读的字段布局和外部 hash API。未复制研究目录中 `valentin-gosselin/ark-ascended-fr` 的 locres.py/cityhash.py：该研究副本未确认根许可，不能因可读取就放入可复用 skill。ASE 脚本虽然标 MIT，但其 whole-asset 写入器未迁移到 ASA。

## 本地工具清单

自行获取并核验可信来源的程序，再填写本地路径；哈希只能确认文件身份，不能代替来源审查。

```json
{
  "repak": {
    "path":"X:/tools/repak.exe",
    "version":"0.2.3",
    "source_url":"https://github.com/trumank/repak/releases/tag/v0.2.3",
    "sha256":"fcd538e5994b9bb833622d425ae346f4e0692f02d4b0025114a559f9b6286022"
  },
  "unreal_locres": {
    "path":"X:/tools/UnrealLocres-1.1.1.exe",
    "version":"release-1.1.1",
    "source_url":"https://github.com/akintos/UnrealLocres",
    "sha256":"b961927f92a8bca928d378a8430e5ea36fed300500b228b184b8d6b61ebb22a1"
  }
}
```

脚本以 argv 调用工具，不经 shell 拼接；执行前核对 hash、版本字段及上游 URL。版本字段是 provenance，独立导出和封包测试才验证本次处理结果。脚本不自动安装工具或执行远程安装脚本。

## 引擎参考与证据范围

- [Epic 文本本地化](https://dev.epicgames.com/documentation/en-us/unreal-engine/text-localization-in-unreal-engine)
- [Epic 配置文件](https://dev.epicgames.com/documentation/unreal-engine/configuration-files-in-unreal-engine)
- [UE5.3 LocalizationResourceTextSource.cpp 参考实现](https://github.com/chenyong2github/UnrealEngine/blob/5.3/Engine/Source/Runtime/Core/Private/Internationalization/LocalizationResourceTextSource.cpp)
- [UE5.3 Paths.cpp](https://github.com/chenyong2github/UnrealEngine/blob/5.3/Engine/Source/Runtime/Core/Private/Misc/Paths.cpp)
- [UE5.3 ConfigCacheIni.cpp](https://github.com/chenyong2github/UnrealEngine/blob/5.3/Engine/Source/Runtime/Core/Private/Misc/ConfigCacheIni.cpp)
- [Wildcard DevKit changelog](https://devkit.studiowildcard.com/changelog)：引擎版本会变化，不能把早期 UE5.2 说明当成当前恒定规格。

公开镜像里的引擎实现用于解释格式和加载假设，不是 ASA 定制实现的直接证据；不将引擎源码拷贝进 skill。模组作者的原始包和社区底包也只作用户授权范围内的本地输入，不并入 skill 或冒称本技能资产。
