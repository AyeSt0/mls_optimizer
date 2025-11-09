# -*- coding: utf-8 -*-
import os, sys, json, subprocess, threading, time, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import webbrowser

APP_TITLE = "MLS Optimizer GUI"
I18N = {
    "zh": {
        "file":"文件", "open_excel":"选择 Excel", "open_glossary":"选择术语表",
        "recent":"最近打开", "excel":"Excel 文件", "glossary":"术语表",
        "config":"配置", "view":"视图", "help":"帮助",
        "run":"开始", "stop":"停止", "dryrun":"仅预览",
        "overwrite":"覆盖已有译文（重译）",
        "row_range":"行号范围(1-based)", "speaker_like":"Speaker 过滤(支持 *)",
        "target_lang":"目标语言", "provider":"提供商",
        "open_output":"打开输出", "open_artifacts":"打开 artifacts",
        "postfix20":"术语预占位到第4列（20）", "postfix21":"翻译后术语再统一（21）",
        "sheet_index":"表索引", "sheet_name":"表名",
        "rpm":"RPM (可留空自动)", "workers":"初始并发", "minmax":"最小/最大并发",
        "log_level":"日志级别", "all":"全部","info":"信息","warn":"警告","error":"错误",
        "start_pipeline":"开始运行流水线…", "done":"完成",
        "readme":"打开 README", "issues":"打开 Issues",
        "provider_note":"（请在 config/settings.local.yaml 填好 API）",
    },
    "en": {
        "file":"File", "open_excel":"Pick Excel", "open_glossary":"Pick Glossary",
        "recent":"Recent", "excel":"Excel", "glossary":"Glossary",
        "config":"Config", "view":"View", "help":"Help",
        "run":"Run", "stop":"Stop", "dryrun":"Dry run",
        "overwrite":"Overwrite existing (re-translate)",
        "row_range":"Row range (1-based)", "speaker_like":"Speaker filter (* supported)",
        "target_lang":"Target language", "provider":"Provider",
        "open_output":"Open Output", "open_artifacts":"Open artifacts",
        "postfix20":"Pre-guard to Col4 (20)", "postfix21":"Post-unify terms (21)",
        "sheet_index":"Sheet index", "sheet_name":"Sheet name",
        "rpm":"RPM (leave blank = auto)", "workers":"Init workers", "minmax":"Min/Max workers",
        "log_level":"Log level", "all":"ALL","info":"INFO","warn":"WARN","error":"ERROR",
        "start_pipeline":"Starting pipeline…", "done":"Done",
        "readme":"Open README", "issues":"Open Issues",
        "provider_note":"(Fill API in config/settings.local.yaml)",
    }
}

RECENT_FILE = "artifacts/recent.json"

class ProcRunner:
    def __init__(self, log_cb, done_cb):
        self.proc=None
        self.log_cb=log_cb
        self.done_cb=done_cb
        self._stop=False
    def run(self, cmd, cwd=None, tag=None):
        self._stop=False
        def _target():
            self.log_cb(f"$ {' '.join(cmd)}\n","info")
            try:
                self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True)
                for line in self.proc.stdout:
                    self.log_cb(line, None)   # 不贴标签，由解析器上色
                    if self._stop: break
                rc=self.proc.wait()
            except Exception as e:
                self.log_cb(f"[ERROR] {e}\n","error")
                rc=1
            finally:
                self.proc=None
                self.done_cb(rc, tag)
        threading.Thread(target=_target, daemon=True).start()
    def stop(self):
        self._stop=True
        if self.proc:
            try: self.proc.terminate()
            except: pass

class App:
    def __init__(self, root:tk.Tk):
        self.root=root
        self.lang="zh"
        self.root.title(APP_TITLE)
        self.root.geometry("980x680")
        self.root.minsize(900,600)

        self.excel_path=tk.StringVar(value="data/MLS Chinese.xlsx")
        self.glossary_path=tk.StringVar(value="data/name_map.json")
        self.target_lang=tk.StringVar(value="zh-CN")
        self.provider=tk.StringVar(value="deepseek")
        self.sheet_index=tk.StringVar(value="0")
        self.sheet_name=tk.StringVar(value="")
        self.rpm=tk.StringVar(value="")  # 自动
        self.workers=tk.StringVar(value="8")
        self.min_workers=tk.StringVar(value="2")
        self.max_workers=tk.StringVar(value="32")
        self.row_range=tk.StringVar(value="")
        self.speaker_like=tk.StringVar(value="")
        self.overwrite=tk.BooleanVar(value=False)
        self.enable_20=tk.BooleanVar(value=True)
        self.enable_21=tk.BooleanVar(value=True)
        self.dryrun=tk.BooleanVar(value=False)
        self.last_output=tk.StringVar(value="")

        self.runner = ProcRunner(self.append_log, self.on_done)
        self._building=False
        self._build_ui()
        self._load_recent()
        self._apply_i18n()

    def _build_ui(self):
        self._build_menubar()

        # 顶部工具条
        top=ttk.Frame(self.root); top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top,text="Excel").grid(row=0,column=0,sticky="w")
        ttk.Entry(top,textvariable=self.excel_path,width=48).grid(row=0,column=1,sticky="we",padx=4)
        ttk.Button(top,text="…", command=self.pick_excel, width=3).grid(row=0,column=2,sticky="w")
        ttk.Label(top,text="Glossary").grid(row=1,column=0,sticky="w")
        ttk.Entry(top,textvariable=self.glossary_path,width=48).grid(row=1,column=1,sticky="we",padx=4)
        ttk.Button(top,text="…", command=self.pick_glossary, width=3).grid(row=1,column=2,sticky="w")

        col3=ttk.Frame(top); col3.grid(row=0,column=3,rowspan=2, sticky="e", padx=8)
        ttk.Button(col3,text="EN/中文", command=self.toggle_lang).pack(side="left", padx=4)
        ttk.Label(col3,text=" ").pack(side="left")

        p2=ttk.LabelFrame(self.root,text="Options"); p2.pack(fill="x", padx=8, pady=4)
        ttk.Checkbutton(p2,text="覆盖已有译文（重译）",variable=self.overwrite).grid(row=0,column=0,sticky="w",padx=4,pady=2)
        ttk.Checkbutton(p2,text="术语预占位到第4列（20）",variable=self.enable_20).grid(row=0,column=1,sticky="w",padx=4,pady=2)
        ttk.Checkbutton(p2,text="翻译后术语再统一（21）",variable=self.enable_21).grid(row=0,column=2,sticky="w",padx=4,pady=2)
        ttk.Checkbutton(p2,text="仅预览(Dry-run)",variable=self.dryrun).grid(row=0,column=3,sticky="w",padx=4,pady=2)

        ttk.Label(p2,text="目标语言").grid(row=1,column=0,sticky="w",padx=4)
        ttk.Entry(p2,textvariable=self.target_lang,width=14).grid(row=1,column=1,sticky="w")
        ttk.Label(p2,text="Provider").grid(row=1,column=2,sticky="w",padx=4)
        ttk.Entry(p2,textvariable=self.provider,width=10).grid(row=1,column=3,sticky="w")
        ttk.Label(p2,text="Sheet idx").grid(row=1,column=4,sticky="e")
        ttk.Entry(p2,textvariable=self.sheet_index,width=6).grid(row=1,column=5,sticky="w")
        ttk.Label(p2,text="Sheet name").grid(row=1,column=6,sticky="e")
        ttk.Entry(p2,textvariable=self.sheet_name,width=12).grid(row=1,column=7,sticky="w")

        ttk.Label(p2,text="行号范围").grid(row=2,column=0,sticky="w",padx=4)
        ttk.Entry(p2,textvariable=self.row_range,width=16).grid(row=2,column=1,sticky="w")
        ttk.Label(p2,text="Speaker 过滤").grid(row=2,column=2,sticky="w",padx=4)
        ttk.Entry(p2,textvariable=self.speaker_like,width=16).grid(row=2,column=3,sticky="w")
        ttk.Label(p2,text="RPM").grid(row=2,column=4,sticky="e")
        ttk.Entry(p2,textvariable=self.rpm,width=8).grid(row=2,column=5,sticky="w")
        ttk.Label(p2,text="并发").grid(row=2,column=6,sticky="e")
        ttk.Entry(p2,textvariable=self.workers,width=6).grid(row=2,column=7,sticky="w")
        ttk.Label(p2,text="Min/Max").grid(row=2,column=8,sticky="e")
        ttk.Entry(p2,textvariable=self.min_workers,width=4).grid(row=2,column=9,sticky="w")
        ttk.Entry(p2,textvariable=self.max_workers,width=4).grid(row=2,column=10,sticky="w")

        # 运行与路径
        ctrl=ttk.Frame(self.root); ctrl.pack(fill="x", padx=8, pady=4)
        ttk.Button(ctrl,text="开始", command=self.run_pipeline, width=12).pack(side="left",padx=4)
        self.btn_stop=ttk.Button(ctrl,text="停止", command=self.stop_pipeline, width=12, state=tk.DISABLED)
        self.btn_stop.pack(side="left",padx=4)
        self.btn_open=ttk.Button(ctrl,text="打开输出", command=self.open_last_output, width=14, state=tk.DISABLED)
        self.btn_open.pack(side="left",padx=4)
        ttk.Button(ctrl,text="打开 artifacts", command=self.open_artifacts, width=14).pack(side="left",padx=4)
        ttk.Label(ctrl,textvariable=self.last_output).pack(side="right")

        # 进度
        self.pb=ttk.Progressbar(self.root,mode="indeterminate")
        self.pb.pack(fill="x", padx=8, pady=2)

        # 日志
        logf=ttk.Frame(self.root); logf.pack(fill="both", expand=True, padx=8, pady=4)
        self.log=ScrolledText(logf, height=18, wrap=tk.WORD)
        self.log.pack(fill="both", expand=True)
        self._init_log_tags()

        self.root.grid_columnconfigure(0, weight=1)

    def _build_menubar(self):
        m=tk.Menu(self.root)
        self.root.config(menu=m)
        self.mbar=m

        self.mnu_file=tk.Menu(m, tearoff=False)
        m.add_cascade(label="文件", menu=self.mnu_file)
        self.mnu_file.add_command(label="选择 Excel", command=self.pick_excel)
        self.mnu_file.add_command(label="选择术语表", command=self.pick_glossary)
        self.mnu_recent_excel=tk.Menu(self.mnu_file, tearoff=False)
        self.mnu_file.add_cascade(label="最近 Excel", menu=self.mnu_recent_excel)
        self.mnu_recent_gloss=tk.Menu(self.mnu_file, tearoff=False)
        self.mnu_file.add_cascade(label="最近 术语表", menu=self.mnu_recent_gloss)

        self.mnu_cfg=tk.Menu(m, tearoff=False)
        m.add_cascade(label="配置", menu=self.mnu_cfg)
        self.mnu_cfg.add_command(label="打开 settings.local.yaml", command=self.open_settings)

        self.mnu_view=tk.Menu(m, tearoff=False)
        m.add_cascade(label="视图", menu=self.mnu_view)
        self.log_level=tk.StringVar(value="ALL")
        for lv in ["ALL","INFO","WARN","ERROR"]:
            self.mnu_view.add_radiobutton(label=lv, variable=self.log_level, value=lv)

        self.mnu_help=tk.Menu(m, tearoff=False)
        m.add_cascade(label="帮助", menu=self.mnu_help)
        self.mnu_help.add_command(label="打开 README", command=lambda: webbrowser.open("https://github.com/"))
        self.mnu_help.add_command(label="打开 Issues", command=lambda: webbrowser.open("https://github.com/"))

    def _init_log_tags(self):
        self.log.tag_configure("ERROR", foreground="#ff4d4f")
        self.log.tag_configure("WARN", foreground="#faad14")
        self.log.tag_configure("INFO", foreground="#91d5ff")
        self.log.tag_configure("DIM", foreground="#aaaaaa")

    # i18n
    def _apply_i18n(self):
        t=I18N[self.lang]
        self.root.title(APP_TITLE)
        # 菜单文本
        self.mbar.entryconfig(0, label=t["file"])
        self.mbar.entryconfig(1, label=t["config"])
        self.mbar.entryconfig(2, label=t["view"])
        self.mbar.entryconfig(3, label=t["help"])

    def toggle_lang(self):
        self.lang="en" if self.lang=="zh" else "zh"
        self._apply_i18n()

    # recent
    def _load_recent(self):
        try:
            with open(RECENT_FILE,'r',encoding='utf-8') as f:
                obj=json.load(f) or {}
        except:
            obj={}
        self.recent_excel = obj.get("excel", [])
        self.recent_gloss = obj.get("glossary", [])
        # rebuild recent menus
        self.mnu_recent_excel.delete(0, tk.END)
        for p in self.recent_excel[:10]:
            self.mnu_recent_excel.add_command(label=p, command=lambda path=p: self.excel_path.set(path))
        self.mnu_recent_gloss.delete(0, tk.END)
        for p in self.recent_gloss[:10]:
            self.mnu_recent_gloss.add_command(label=p, command=lambda path=p: self.glossary_path.set(path))

    def _save_recent(self):
        os.makedirs("artifacts", exist_ok=True)
        obj={"excel": [self.excel_path.get()]+[p for p in self.recent_excel if p!=self.excel_path.get()],
             "glossary": [self.glossary_path.get()]+[p for p in self.recent_gloss if p!=self.glossary_path.get()]}
        with open(RECENT_FILE,'w',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2)
        self._load_recent()

    # file pickers
    def pick_excel(self):
        p=filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")])
        if p: self.excel_path.set(p); self._save_recent()
    def pick_glossary(self):
        p=filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if p: self.glossary_path.set(p); self._save_recent()
    def open_settings(self):
        p="config/settings.local.yaml"
        if os.path.exists(p): os.startfile(os.path.abspath(p))
        else: messagebox.showinfo("提示","未找到 config/settings.local.yaml")

    # open dirs
    def open_artifacts(self):
        os.makedirs("artifacts", exist_ok=True)
        os.startfile(os.path.abspath("artifacts"))
    def open_last_output(self):
        p=self.last_output.get()
        if p and os.path.exists(p): os.startfile(os.path.abspath(p))

    # logging
    def append_log(self, s:str, level=None):
        # 解析并着色
        tag=None
        if level: tag=level.upper()
        else:
            if "[ERROR]" in s or "Traceback" in s: tag="ERROR"
            elif "[WARN]" in s or "WARNING" in s: tag="WARN"
            elif "[INFO]" in s or s.startswith("$ "): tag="INFO"
        self.log.insert(tk.END, s, tag)
        self.log.see(tk.END)

    # pipeline
    def run_pipeline(self):
        if self.runner.proc:
            return
        self.append_log(f"[INFO] {I18N[self.lang]['start_pipeline']}\n","INFO")
        self.btn_stop.config(state=tk.NORMAL)
        self.pb.start(10)

        # Step 1 场景切分（为了后续按场景构造上下文，12中已轻量使用）
        idx = self.sheet_index.get().strip()
        name= self.sheet_name.get().strip()
        step1 = [sys.executable,"-u","-m","scripts.05_segment_context","--excel", self.excel_path.get()]
        if name: step1 += ["--sheet-name", name]
        else:    step1 += ["--sheet-index", idx or "0"]

        def after_step1(rc, tag):
            if rc!=0:
                self.on_done(rc,"step1"); return
            # Step 2 流水线：20 -> 12 -> (21?)
            tasks=[]
            if self.enable_20.get():
                out20 = self.excel_path.get().replace(".xlsx",".guard.xlsx")
                step20=[sys.executable,"-u","-m","scripts.20_enforce_terms",
                        "--excel", self.excel_path.get(),
                        "--glossary", self.glossary_path.get(),
                        "--out", out20]
                if self.overwrite.get(): step20.append("--overwrite")
                tasks.append(("step20", step20, out20))
                src_for_12 = out20
            else:
                src_for_12 = self.excel_path.get()

            out12 = src_for_12.replace(".xlsx",".llm.xlsx")
            step12=[sys.executable,"-u","-m","scripts.12_llm_translate",
                    "--excel", src_for_12,
                    "--target-lang", self.target_lang.get(),
                    "--glossary", self.glossary_path.get(),
                    "--out", out12]
            # provider/rpm/workers
            if self.provider.get(): step12 += ["--provider", self.provider.get()]
            if self.rpm.get(): step12 += ["--rpm", self.rpm.get()]
            step12 += ["--workers", self.workers.get() or "8",
                       "--min-workers", self.min_workers.get() or "2",
                       "--max-workers", self.max_workers.get() or "32"]
            # sheet
            if self.sheet_name.get().strip():
                step12 += ["--sheet-name", self.sheet_name.get().strip()]
            else:
                step12 += ["--sheet-index", self.sheet_index.get().strip() or "0"]
            # filter
            if self.overwrite.get(): step12.append("--overwrite")
            if self.row_range.get().strip(): step12 += ["--row-range", self.row_range.get().strip()]
            if self.speaker_like.get().strip(): step12 += ["--speaker-like", self.speaker_like.get().strip()]
            if self.dryrun.get(): step12.append("--dry-run")

            tasks.append(("step12", step12, out12))

            if self.enable_21.get():
                out21 = out12.replace(".xlsx",".terms.xlsx")
                step21=[sys.executable,"-u","-m","scripts.21_enforce_terms_again",
                        "--excel", out12,
                        "--glossary", self.glossary_path.get(),
                        "--out", out21]
                tasks.append(("step21", step21, out21))

            self._run_tasks_chain(tasks, 0)

        # 先跑 step1
        self.runner.run(step1, tag="step1")
        self._wait_then(after_step1, "step1")

    def _run_tasks_chain(self, tasks, i):
        if i>=len(tasks):
            self.append_log(f"[OK] {I18N[self.lang]['done']}\n","INFO")
            self.pb.stop(); self.btn_stop.config(state=tk.DISABLED)
            if self.last_output.get():
                self.btn_open.config(state=tk.NORMAL)
            return
        name, cmd, out = tasks[i]
        def next_step(rc, tag):
            if rc!=0:
                self.on_done(rc, name); return
            self.last_output.set(out)
            self.runner.run(cmd, tag=name)
            self._wait_then(lambda rc2, tg2: self._run_tasks_chain(tasks, i+1), name)
        # 先直接进入 next_step，按 step1 完成后调用
        next_step(0, name)

    def _wait_then(self, cb, tag):
        # 等待上一个 runner 完成后再回调
        def poll():
            if self.runner.proc is None:
                cb(0, tag)
            else:
                self.root.after(150, poll)
        self.root.after(150, poll)

    def on_done(self, rc, tag):
        if rc==0:
            self.append_log("[OK] 步骤完成。\n","INFO")
        else:
            self.append_log(f"[ERROR] finished with rc={rc}\n","ERROR")
        if self.runner.proc is None:
            self.pb.stop()
            self.btn_stop.config(state=tk.DISABLED)
            if self.last_output.get():
                self.btn_open.config(state=tk.NORMAL)

    def stop_pipeline(self):
        if self.runner.proc:
            self.runner.stop()
            self.append_log("[INFO] 停止信号已发送。\n","INFO")

def main():
    root=tk.Tk()
    App(root)
    root.mainloop()

if __name__=="__main__":
    main()
