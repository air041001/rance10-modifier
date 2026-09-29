# 第三方组件与游戏资源

本项目自己的 Python 与 C# 源代码按 MIT 许可发布。

Windows 应用包含 Python、Tcl/Tk、Pillow，以及 PyInstaller 引导程序及其依赖。
构建脚本会从构建环境收集相应许可文本，放入发布包的 `_internal/licenses`。
其中 Pillow 的许可文本包含其图像库依赖的许可。
PyInstaller 引导程序适用该项目的许可与应用分发例外，见所附完整许可。

图鉴准备功能调用独立的 [alice-tools](https://github.com/nunuhara/alice-tools)，
固定使用官方 0.13.0 版本并校验 `alice.exe` 的 SHA-256。
本仓库和应用下载包不包含 alice-tools 二进制或源代码。
用户可自行选择本地副本，或在应用中主动从原项目官方发布页下载；
下载组件时同时保存原项目的 COPYING.txt。alice-tools 按 GPL-2.0-or-later 发布。

本项目不发布游戏程序、卡牌图像、游戏数据库、存档或补丁。
图鉴数据与卡面由用户自己的本机游戏生成，仅存储在本机缓存中；
游戏及其素材的权利归相应权利人所有。本项目与游戏开发商无隶属关系。
