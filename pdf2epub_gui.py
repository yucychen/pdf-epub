"""GUI:批量转换多个 PDF -> EPUB(美化版,基于 tkinter)"""
import multiprocessing
import os
import platform
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pdf2epub import convert

# ============ 主题配色(浅色现代风) ============
COLORS = {
    "bg":          "#F5F7FA",   # 主背景
    "card":        "#FFFFFF",   # 卡片背景
    "border":      "#E1E5EB",   # 边框
    "text":        "#1F2937",   # 主文字
    "muted":       "#6B7280",   # 次要文字
    "primary":     "#2563EB",   # 主操作蓝
    "primary_hi":  "#1D4ED8",   # 悬停
    "success":     "#16A34A",
    "danger":      "#DC2626",
    "warning":     "#F59E0B",
    "running":     "#2563EB",
    "title":       "#0F172A",
}

FONT_FAMILY = "Microsoft YaHei UI" if platform.system() == "Windows" else (
    "PingFang SC" if platform.system() == "Darwin" else "Sans")


def apply_style(root):
    """配置 ttk 全局样式"""
    style = ttk.Style(root)
    # 选一个底色干净的主题做基底
    for theme in ("clam", "alt", "default"):
        if theme in style.theme_names():
            style.theme_use(theme)
            break

    root.configure(bg=COLORS["bg"])

    style.configure(".", background=COLORS["bg"], foreground=COLORS["text"],
                    font=(FONT_FAMILY, 10))

    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["card"], relief="flat",
                    borderwidth=1)
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("Title.TLabel", background=COLORS["bg"],
                    foreground=COLORS["title"], font=(FONT_FAMILY, 18, "bold"))
    style.configure("Subtitle.TLabel", background=COLORS["bg"],
                    foreground=COLORS["muted"], font=(FONT_FAMILY, 9))
    style.configure("Section.TLabel", background=COLORS["card"],
                    foreground=COLORS["title"], font=(FONT_FAMILY, 11, "bold"))
    style.configure("Muted.TLabel", background=COLORS["card"],
                    foreground=COLORS["muted"], font=(FONT_FAMILY, 9))
    style.configure("Status.TLabel", background=COLORS["bg"],
                    foreground=COLORS["muted"], font=(FONT_FAMILY, 9))

    # 按钮:默认(次要)
    style.configure("TButton", background=COLORS["card"],
                    foreground=COLORS["text"], borderwidth=1,
                    focusthickness=0, padding=(12, 6),
                    font=(FONT_FAMILY, 10))
    style.map("TButton",
              background=[("active", "#EEF2F7"), ("pressed", "#E5E9F0")],
              bordercolor=[("active", COLORS["primary"])])

    # 主按钮(强调)
    style.configure("Accent.TButton", background=COLORS["primary"],
                    foreground="#FFFFFF", borderwidth=0,
                    padding=(20, 10),
                    font=(FONT_FAMILY, 11, "bold"))
    style.map("Accent.TButton",
              background=[("active", COLORS["primary_hi"]),
                          ("pressed", COLORS["primary_hi"]),
                          ("disabled", "#9CA3AF")],
              foreground=[("disabled", "#E5E7EB")])

    # 输入框
    style.configure("TEntry", fieldbackground=COLORS["card"],
                    bordercolor=COLORS["border"], lightcolor=COLORS["border"],
                    darkcolor=COLORS["border"], padding=4)
    style.configure("TCombobox", fieldbackground=COLORS["card"], padding=4)

    # 单选 / 复选
    style.configure("TRadiobutton", background=COLORS["card"],
                    foreground=COLORS["text"], font=(FONT_FAMILY, 10))
    style.map("TRadiobutton",
              background=[("active", COLORS["card"])])

    # LabelFrame(卡片标题)
    style.configure("Card.TLabelframe", background=COLORS["card"],
                    bordercolor=COLORS["border"], borderwidth=1, relief="solid")
    style.configure("Card.TLabelframe.Label", background=COLORS["card"],
                    foreground=COLORS["title"],
                    font=(FONT_FAMILY, 10, "bold"))

    # 进度条
    style.configure("TProgressbar", background=COLORS["primary"],
                    troughcolor="#E5E7EB", borderwidth=0, thickness=10)


def main():
    root = tk.Tk()
    root.title("PDF → EPUB 批量转换器")
    root.geometry("820x700")
    root.minsize(720, 600)

    apply_style(root)

    files = []
    author_var = tk.StringVar(value="Unknown")
    lang_var = tk.StringVar(value="zh")
    mode_var = tk.StringVar(value="auto")
    ocr_var = tk.StringVar(value="off")
    ocr_lang_var = tk.StringVar(value="chi_sim+eng")
    status_var = tk.StringVar(value="点「添加文件」选择一个或多个 PDF")
    count_var = tk.StringVar(value="共 0 个文件")

    # ============ 顶部标题 ============
    header = ttk.Frame(root, padding=(20, 16, 20, 8))
    header.pack(fill="x")
    ttk.Label(header, text="📚  PDF → EPUB 转换器",
              style="Title.TLabel").pack(anchor="w")
    ttk.Label(header,
              text="批量转换 · 自动识别扫描书 · 支持 OCR",
              style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

    # ============ 主体容器 ============
    body = ttk.Frame(root, padding=(20, 4, 20, 12))
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=2)
    body.rowconfigure(2, weight=1)

    # ============ 卡片 1:文件列表 ============
    card_files = ttk.LabelFrame(body, text="  待转换文件  ",
                                style="Card.TLabelframe", padding=12)
    card_files.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
    card_files.columnconfigure(0, weight=1)
    card_files.rowconfigure(1, weight=1)

    # 工具栏
    toolbar = ttk.Frame(card_files, style="Card.TFrame")
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    toolbar.configure(style="Card.TFrame")

    def add_files():
        paths = filedialog.askopenfilenames(
            title="选择一个或多个 PDF(可按住 Ctrl/Shift 多选)",
            filetypes=[("PDF 文件", "*.pdf")])
        added = 0
        for p in paths:
            if p not in files:
                files.append(p)
                listbox.insert("end", "  " + os.path.basename(p))
                added += 1
        if added:
            status_var.set("已添加 {} 个文件".format(added))
        update_count()

    def remove_selected():
        for idx in reversed(listbox.curselection()):
            listbox.delete(idx)
            del files[idx]
        status_var.set("已移除选中文件")
        update_count()

    def clear_all():
        if files and not messagebox.askyesno("确认", "清空所有文件?"):
            return
        listbox.delete(0, "end")
        files.clear()
        status_var.set("已清空")
        update_count()

    def update_count():
        count_var.set("共 {} 个文件".format(len(files)))

    ttk.Button(toolbar, text="➕  添加文件", command=add_files).pack(side="left")
    ttk.Button(toolbar, text="➖  移除选中",
               command=remove_selected).pack(side="left", padx=6)
    ttk.Button(toolbar, text="🗑  清空", command=clear_all).pack(side="left")
    ttk.Label(toolbar, textvariable=count_var,
              style="Muted.TLabel").pack(side="right")

    # 列表
    list_wrap = tk.Frame(card_files, bg=COLORS["card"],
                         highlightthickness=1, highlightcolor=COLORS["border"],
                         highlightbackground=COLORS["border"])
    list_wrap.grid(row=1, column=0, sticky="nsew")
    list_wrap.columnconfigure(0, weight=1)
    list_wrap.rowconfigure(0, weight=1)

    listbox = tk.Listbox(list_wrap, selectmode="extended",
                         activestyle="none",
                         bg=COLORS["card"], fg=COLORS["text"],
                         selectbackground=COLORS["primary"],
                         selectforeground="#FFFFFF",
                         highlightthickness=0, borderwidth=0,
                         font=(FONT_FAMILY, 10), height=8)
    sb = ttk.Scrollbar(list_wrap, orient="vertical", command=listbox.yview)
    listbox.config(yscrollcommand=sb.set)
    listbox.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)
    sb.grid(row=0, column=1, sticky="ns")

    # 拖放提示
    placeholder = ttk.Label(list_wrap,
                            text="📥  点上方「添加文件」按钮加入 PDF",
                            background=COLORS["card"],
                            foreground=COLORS["muted"],
                            font=(FONT_FAMILY, 11))
    placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def update_placeholder(*_):
        if listbox.size() == 0:
            placeholder.place(relx=0.5, rely=0.5, anchor="center")
        else:
            placeholder.place_forget()
    listbox.bind("<<ListboxSelect>>", update_placeholder)

    # ============ 卡片 2:选项 ============
    card_opts = ttk.LabelFrame(body, text="  转换选项  ",
                               style="Card.TLabelframe", padding=14)
    card_opts.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    card_opts.columnconfigure(1, weight=1)
    card_opts.columnconfigure(3, weight=1)

    def opt_label(parent, text, r, c):
        ttk.Label(parent, text=text, style="Card.TLabel",
                  font=(FONT_FAMILY, 10)).grid(
            row=r, column=c, sticky="w", padx=(0, 8), pady=6)

    opt_label(card_opts, "作者", 0, 0)
    ttk.Entry(card_opts, textvariable=author_var, width=18).grid(
        row=0, column=1, sticky="w", padx=(0, 16))
    opt_label(card_opts, "语言", 0, 2)
    ttk.Entry(card_opts, textvariable=lang_var, width=10).grid(
        row=0, column=3, sticky="w")

    opt_label(card_opts, "转换模式", 1, 0)
    mode_box = ttk.Frame(card_opts, style="Card.TFrame")
    mode_box.grid(row=1, column=1, columnspan=3, sticky="w")
    for txt, val in [("🪄 自动", "auto"),
                     ("📝 文字", "text"),
                     ("🖼 图片(扫描书)", "image")]:
        ttk.Radiobutton(mode_box, text=txt, value=val,
                        variable=mode_var).pack(side="left", padx=(0, 14))

    opt_label(card_opts, "OCR", 2, 0)
    ocr_box = ttk.Frame(card_opts, style="Card.TFrame")
    ocr_box.grid(row=2, column=1, columnspan=3, sticky="w")
    for txt, val in [("关闭", "off"), ("自动", "auto"), ("强制", "force")]:
        ttk.Radiobutton(ocr_box, text=txt, value=val,
                        variable=ocr_var).pack(side="left", padx=(0, 14))

    opt_label(card_opts, "OCR 语言", 3, 0)
    ttk.Combobox(card_opts, textvariable=ocr_lang_var, width=20,
                 state="readonly",
                 values=["chi_sim+eng", "chi_tra+eng", "eng",
                         "jpn+eng", "kor+eng"]).grid(
        row=3, column=1, sticky="w")

    # ============ 卡片 3:进度 + 日志 ============
    card_log = ttk.LabelFrame(body, text="  转换进度  ",
                              style="Card.TLabelframe", padding=12)
    card_log.grid(row=2, column=0, sticky="nsew")
    card_log.columnconfigure(0, weight=1)
    card_log.rowconfigure(2, weight=1)

    progress = ttk.Progressbar(card_log, mode="determinate")
    progress.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    ttk.Label(card_log, textvariable=status_var,
              style="Muted.TLabel").grid(row=1, column=0, sticky="w",
                                         pady=(0, 6))

    log_wrap = tk.Frame(card_log, bg=COLORS["card"],
                        highlightthickness=1,
                        highlightcolor=COLORS["border"],
                        highlightbackground=COLORS["border"])
    log_wrap.grid(row=2, column=0, sticky="nsew")
    log_wrap.columnconfigure(0, weight=1)
    log_wrap.rowconfigure(0, weight=1)

    log_text = tk.Text(log_wrap, height=5,
                       font=("Consolas", 9),
                       bg="#0F172A", fg="#E5E7EB",
                       insertbackground="#FFFFFF",
                       borderwidth=0, highlightthickness=0,
                       padx=10, pady=8, wrap="word")
    log_sb = ttk.Scrollbar(log_wrap, orient="vertical",
                           command=log_text.yview)
    log_text.config(yscrollcommand=log_sb.set)
    log_text.grid(row=0, column=0, sticky="nsew")
    log_sb.grid(row=0, column=1, sticky="ns")

    # 日志颜色 tag
    log_text.tag_config("ok", foreground="#4ADE80")
    log_text.tag_config("err", foreground="#F87171")
    log_text.tag_config("info", foreground="#60A5FA")
    log_text.tag_config("muted", foreground="#9CA3AF")

    def log(line, tag="muted"):
        log_text.insert("end", line + "\n", tag)
        log_text.see("end")

    # ============ 底部操作栏 ============
    footer = ttk.Frame(root, padding=(20, 8, 20, 16))
    footer.pack(fill="x")

    ttk.Label(footer,
              text="💡 扫描书/漫画选「图片」模式 · EPUB 输出到 PDF 同目录同名",
              style="Status.TLabel").pack(side="left")

    def start():
        if not files:
            messagebox.showwarning("提示", "请先添加至少一个 PDF 文件")
            return
        opts = dict(author=author_var.get() or "Unknown",
                    lang=lang_var.get() or "zh",
                    mode=mode_var.get(),
                    ocr_mode=ocr_var.get(),
                    ocr_lang=ocr_lang_var.get() or "chi_sim+eng")
        log_text.delete("1.0", "end")
        threading.Thread(target=run_batch, daemon=True,
                         args=(list(files), opts, start_btn,
                               status_var, progress, listbox, log)).start()

    start_btn = ttk.Button(footer, text="▶  开始批量转换",
                           style="Accent.TButton", command=start)
    start_btn.pack(side="right")

    update_placeholder()
    root.mainloop()


def run_batch(files, opts, btn, status, progress, listbox, log):
    """依次转换 files 列表里的所有 PDF"""
    total = len(files)
    ok, fail = 0, 0
    btn.config(state="disabled")
    progress["maximum"] = total
    progress["value"] = 0

    for i, pdf in enumerate(files, 1):
        name = os.path.basename(pdf)
        status.set("[{}/{}] 转换中: {}".format(i, total, name))
        listbox.itemconfig(i - 1, foreground=COLORS["running"])
        listbox.see(i - 1)
        prefix = "[{}/{}]  {} ... ".format(i, total, name)
        try:
            out = os.path.splitext(pdf)[0] + ".epub"
            title = os.path.splitext(name)[0]
            convert(pdf_path=pdf, epub_path=out,
                    title=title, author=opts["author"], lang=opts["lang"],
                    mode=opts["mode"], ocr_mode=opts["ocr_mode"],
                    ocr_lang=opts["ocr_lang"])
            listbox.itemconfig(i - 1, foreground=COLORS["success"])
            log(prefix + "✓ 成功 → " + os.path.basename(out), "ok")
            ok += 1
        except Exception as e:
            listbox.itemconfig(i - 1, foreground=COLORS["danger"])
            log(prefix + "✗ 失败: " + str(e), "err")
            fail += 1
        progress["value"] = i

    status.set("✓ 全部完成   成功 {} · 失败 {}".format(ok, fail))
    btn.config(state="normal")
    messagebox.showinfo("批量转换完成",
                        "总计 {} 个\n✓ 成功 {}\n✗ 失败 {}".format(total, ok, fail))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
