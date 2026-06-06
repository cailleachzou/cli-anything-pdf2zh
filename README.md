# cli-anything-pdf2zh

> **PDF 原文原地翻译** — 保留排版、公式、图表，从脚本和 AI Agent 调用。

## 关于上游软件

核心翻译引擎是 **PDFMathTranslate**（`pdf2zh`）— 一个开源的 PDF 文档原地翻译工具，能在保留原始排版、数学公式、图片和表格的同时，将 PDF 内容翻译为目标语言。支持单语输出（`*-mono.pdf`）和双语对照输出（`*-dual.pdf`）。

| 资源 | 链接 |
|------|------|
| 原仓库 | <https://github.com/PDFMathTranslate/PDFMathTranslate> |
| 发行版（EXE 安装包） | <https://github.com/PDFMathTranslate/PDFMathTranslate/releases> |
| 文档 | <https://pdf2zh.readthedocs.io/> |

### `build/` 目录

`build/` 目录（已 git-ignore）包含从上游发行版下载的 **Windows EXE 安装包**，内含：

- `pdf2zh.exe` — 独立入口（PyStand 打包）
- `runtime/` — 内置 Python 解释器
- `site-packages/` — 全部 Python 依赖包（含 `pdf2zh`）

请从 [PDFMathTranslate/releases](https://github.com/PDFMathTranslate/PDFMathTranslate/releases) 下载发行版，解压到 `build/` 目录即可。

---

## 本仓库做了什么

在上游 EXE 之上，本仓库提供了：

- **一键翻译** — `cli-anything-pdf2zh translate paper.pdf -o out/`
- **交互式 REPL** — 支持 `pdf / lang / use / translate / save` 等命令
- **JSON 输出** — 所有命令支持 `--json`，方便 Agent 消费
- **23 种翻译服务** — Google、OpenAI、MiniMax、DeepL 等一键切换
- **配置管理** — 读写 `~/.config/PDFMathTranslate/config.json`
- **缓存查看** — 检查 `~/.cache/pdf2zh/cache.v1.db` 翻译缓存
- **MiniMax 补丁** — 一键注入 MiniMax 翻译器到 EXE 中

---

## 快速开始

```bash
# 1. 安装 harness
cd agent-harness
pip install -e .

# 2.（可选）安装 MiniMax 翻译器补丁
cli-anything-pdf2zh patch install

# 3. 翻译 PDF
cli-anything-pdf2zh translate paper.pdf -o out/ --service google
```

完整文档见 [`agent-harness/cli_anything/pdf2zh/README.md`](agent-harness/cli_anything/pdf2zh/README.md)。

---

## 许可证

MIT.
