"""GUI:批量转换多个 PDF -> EPUB(基于 tkinter)"""
import multiprocessing
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pdf2epub import convert


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
        listbox.itemconfig(i - 1, foreground="blue")
        listbox.see(i - 1)
        log_line = "[{}/{}] {} ... ".format(i, total, name)
        try:
            out = os.path.splitext(pdf)[0] + ".epub"
            title = os.path.splitext(name)[0]
            convert(pdf_path=pdf, epub_path=out,
                    title=title, author=opts["author"], lang=opts["lang"],
                    mode=opts["mode"], ocr_mode=opts["ocr_mode"],
                    ocr_lang=opts["ocr_lang"])
            listbox.itemconfig(i - 1, foreground="green")
            log(log_line + "OK -> " + os.path.basename(out))
            ok += 1
        except Exception as e:
            listbox.itemconfig(i - 1, foreground="red")
            log(log_line + "FAIL: " + str(e))
            fail += 1
        progress["value"] = i

    status.set("全部完成 ✓ 成功 {} / 失败 {}".format(ok, fail))
    btn.config(state="normal")
    messagebox.showinfo("批量转换完成",
                        "总计 {} 个\n成功 {}\n失败 {}".format(total, ok, fail))


def main():
    root = tk.Tk()
    root.title("PDF -> EPUB 批量转换器")
    root.geometry("720x600")

    files = []  # 待转换文件列表
    author_var = tk.StringVar(value="Unknown")
    lang_var = tk.StringVar(value="zh")
    mode_var = tk.StringVar(value="auto")
    ocr_var = tk.StringVar(value="off")
    ocr_lang_var = tk.StringVar(value="chi_sim+eng")
    status_var = tk.StringVar(value="点「添加文件」选择一个或多个 PDF")

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="both", expand=True)

    # ---- 文件列表 ----
    ttk.Label(frm, text="待转换文件(EPUB 与原 PDF 同目录同名):").grid(
        row=0, column=0, columnspan=4, sticky="w")

    list_frame = ttk.Frame(frm)
    list_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=4)
    frm.rowconfigure(1, weight=1)
    frm.columnconfigure(3, weight=1)

    listbox = tk.Listbox(list_frame, height=10, selectmode="extended",
                         activestyle="dotbox")
    sb = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
    listbox.config(yscrollcommand=sb.set)
    listbox.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def add_files():
        paths = filedialog.askopenfilenames(
            title="选择一个或多个 PDF(可按住 Ctrl/Shift 多选)",
            filetypes=[("PDF", "*.pdf")])
        added = 0
        for p in paths:
            if p not in files:
                files.append(p)
                listbox.insert("end", p)
                added += 1
        if added:
            status_var.set("已添加 {} 个,共 {} 个待转换".format(added, len(files)))

    def remove_selected():
        for idx in reversed(listbox.curselection()):
            listbox.delete(idx)
            del files[idx]
        status_var.set("剩余 {} 个待转换".format(len(files)))

    def clear_all():
        listbox.delete(0, "end")
        files.clear()
        status_var.set("已清空")

    btn_bar = ttk.Frame(frm)
    btn_bar.grid(row=2, column=0, columnspan=4, sticky="w", pady=4)
    ttk.Button(btn_bar, text="➕ 添加文件", command=add_files).pack(side="left", padx=2)
    ttk.Button(btn_bar, text="➖ 移除选中", command=remove_selected).pack(side="left", padx=2)
    ttk.Button(btn_bar, text="🗑 清空", command=clear_all).pack(side="left", padx=2)

    # ---- 共享选项(对所有文件生效) ----
    opts_frame = ttk.LabelFrame(frm, text="共享选项(应用于所有文件)", padding=8)
    opts_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=8)

    ttk.Label(opts_frame, text="作者:").grid(row=0, column=0, sticky="w", pady=2)
    ttk.Entry(opts_frame, textvariable=author_var, width=20).grid(row=0, column=1, sticky="w", padx=4)
    ttk.Label(opts_frame, text="语言:").grid(row=0, column=2, sticky="w", padx=8)
    ttk.Entry(opts_frame, textvariable=lang_var, width=8).grid(row=0, column=3, sticky="w")

    ttk.Label(opts_frame, text="转换模式:").grid(row=1, column=0, sticky="w", pady=2)
    mode_box = ttk.Frame(opts_frame)
    mode_box.grid(row=1, column=1, columnspan=3, sticky="w")
    ttk.Radiobutton(mode_box, text="自动", variable=mode_var, value="auto").pack(side="left")
    ttk.Radiobutton(mode_box, text="文字", variable=mode_var, value="text").pack(side="left")
    ttk.Radiobutton(mode_box, text="图片(扫描书)", variable=mode_var, value="image").pack(side="left")

    ttk.Label(opts_frame, text="OCR:").grid(row=2, column=0, sticky="w", pady=2)
    ocr_box = ttk.Frame(opts_frame)
    ocr_box.grid(row=2, column=1, columnspan=3, sticky="w")
    ttk.Radiobutton(ocr_box, text="关闭", variable=ocr_var, value="off").pack(side="left")
    ttk.Radiobutton(ocr_box, text="自动", variable=ocr_var, value="auto").pack(side="left")
    ttk.Radiobutton(ocr_box, text="强制", variable=ocr_var, value="force").pack(side="left")

    ttk.Label(opts_frame, text="OCR 语言:").grid(row=3, column=0, sticky="w", pady=2)
    ttk.Combobox(opts_frame, textvariable=ocr_lang_var, width=18,
                 values=["chi_sim+eng", "chi_tra+eng", "eng",
                         "jpn+eng", "kor+eng"]).grid(row=3, column=1, sticky="w")

    # ---- 进度 + 日志 ----
    progress = ttk.Progressbar(frm, mode="determinate")
    progress.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 2))

    ttk.Label(frm, textvariable=status_var, foreground="gray").grid(
        row=5, column=0, columnspan=4, sticky="w")

    log_frame = ttk.Frame(frm)
    log_frame.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=4)
    frm.rowconfigure(6, weight=1)
    log_text = tk.Text(log_frame, height=6, font=("Consolas", 9))
    log_sb = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
    log_text.config(yscrollcommand=log_sb.set)
    log_text.pack(side="left", fill="both", expand=True)
    log_sb.pack(side="right", fill="y")

    def log(line):
        log_text.insert("end", line + "\n")
        log_text.see("end")

    # ---- 开始按钮 ----
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

    start_btn = ttk.Button(frm, text="▶ 开始批量转换", command=start)
    start_btn.grid(row=7, column=0, columnspan=4, pady=8)

    ttk.Label(frm,
              text="提示:扫描书/漫画选「图片模式」效果最好;EPUB 输出到 PDF 同目录同名",
              foreground="#888").grid(row=8, column=0, columnspan=4, sticky="w")

    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
