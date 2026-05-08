# pdf-epub

一个简单好用的 **PDF -> EPUB** 转换工具,基于 PyMuPDF + EbookLib。

- 命令行 (`pdf2epub`) + 图形界面 (`pdf2epub-gui`)
- 自动按 PDF 大纲生成章节与目录
- 提取并嵌入图片
- 自动从首页生成封面(可自定义)
- 一键 PyInstaller 打包,Win/Mac/Linux 通吃
- 打 tag 自动出三平台 Release

## 快速开始

    pip install -r requirements.txt
    python pdf2epub.py book.pdf -o book.epub -t "书名" -a "作者"
    # 或 GUI
    python pdf2epub_gui.py

## 打包成可执行文件

Windows: `build.bat`
macOS / Linux: `chmod +x build.sh && ./build.sh`

产物在 `dist/pdf2epub/`,包含 CLI 与 GUI 两个可执行文件。

## 自动发布

    git tag v1.0.0
    git push origin v1.0.0

几分钟后 Releases 页会出现三平台压缩包。
