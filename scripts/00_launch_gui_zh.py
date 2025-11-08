import sys, os, subprocess, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox

PROJECT_ROOT = Path(__file__).resolve().parents[1]

LANG_CHOICES = [
    ("Chinese (Simplified)", "zh-CN"), ("Chinese (Traditional)", "zh-TW"),
    ("English", "en"), ("Japanese", "ja"), ("Korean", "ko"),
    ("French", "fr"), ("German", "de"), ("Spanish", "es"),
    ("Portuguese (Brazil)", "pt-BR"), ("Portuguese (Portugal)", "pt-PT"),
    ("Italian", "it"), ("Russian", "ru"), ("Ukrainian", "uk"),
    ("Polish", "pl"), ("Czech", "cs"), ("Slovak", "sk"),
    ("Hungarian", "hu"), ("Romanian", "ro"), ("Bulgarian", "bg"),
    ("Greek", "el"), ("Turkish", "tr"), ("Dutch", "nl"),
    ("Norwegian", "no"), ("Danish", "da"), ("Swedish", "sv"),
    ("Finnish", "fi"), ("Estonian", "et"), ("Latvian", "lv"),
    ("Lithuanian", "lt"), ("Slovenian", "sl"), ("Croatian", "hr"),
    ("Serbian", "sr"), ("Bosnian", "bs"), ("Catalan", "ca"),
    ("Galician", "gl"), ("Basque", "eu"), ("Icelandic", "is"),
    ("Irish", "ga"), ("Welsh", "cy"), ("Scottish Gaelic", "gd"),
    ("Maltese", "mt"), ("Luxembourgish", "lb"), ("Esperanto", "eo"),
    ("Arabic", "ar"), ("Hebrew", "he"), ("Persian", "fa"),
    ("Hindi", "hi"), ("Bengali", "bn"), ("Urdu", "ur"),
    ("Tamil", "ta"), ("Telugu", "te"), ("Kannada", "kn"),
    ("Malayalam", "ml"), ("Marathi", "mr"), ("Gujarati", "gu"),
    ("Punjabi", "pa"), ("Sinhala", "si"), ("Nepali", "ne"),
    ("Thai", "th"), ("Vietnamese", "vi"), ("Indonesian", "id"),
    ("Malay", "ms"), ("Filipino", "fil"), ("Khmer", "km"),
    ("Lao", "lo"), ("Burmese", "my"), ("Mongolian", "mn"),
    ("Kazakh", "kk"), ("Uzbek", "uz"), ("Turkmen", "tk"),
    ("Georgian", "ka"), ("Armenian", "hy"), ("Azerbaijani", "az"),
    ("Albanian", "sq"), ("Macedonian", "mk"), ("Haitian Creole", "ht"),
    ("Swahili", "sw"), ("Amharic", "am"), ("Yoruba", "yo"),
    ("Zulu", "zu"), ("Afrikaans", "af")
]

def parse_code_from_choice(choice: str) -> str:
    if "(" in choice and choice.endswith(")"):
        return choice.rsplit("(",1)[1][:-1]
    return choice

def run_cmd(cmd, cwd, log, stop_flag):
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as e:
        log(f"[ERROR] {e}\n")
        return 1
    for line in iter(p.stdout.readline, ""):
        if stop_flag["stop"]:
            try:
                p.terminate()
            except Exception:
                pass
            log("[WARN] Stopped by user.\n")
            return 2
        log(line)
    p.wait()
    return p.returncode

STR = {
  "title": "MLS 本地化优化器 — 一键 GUI（v6.5 中文）",
  "sec_files": "输入文件",
  "excel": "Excel：",
  "name_map": "name_map.json：",
  "sec_lang": "语言与模型",
  "target_lang": "目标语言：",
  "custom_code": "或自定义代码：",
  "provider": "服务商：",
  "model": "模型：",
  "sec_perf": "性能",
  "workers": "并发数：",
  "min": "最小：",
  "max": "最大：",
  "rpm": "限速 RPM：",
  "glossary_max": "术语最大条数：",
  "sec_opt": "选项",
  "context_mode": "上下文模式：",
  "scene": "场景（推荐）",
  "window": "窗口",
  "include_system": "包含系统行",
  "resume": "断点续跑",
  "run_full": "运行全流程",
  "run_translate": "仅运行翻译",
  "open_artifacts": "打开 artifacts",
  "open_config": "打开 config",
  "help": "帮助",
  "stop": "停止",
  "ready": "就绪",
  "help_text": "1）将 MLS Chinese.xlsx 与 name_map.json 放在 data/\n2）在 config/settings.local.yaml 填好 API Key\n3）选择目标语言（或自定义代码），点击“运行全流程”\n已启用：断点续跑 / 自动保存 / 术语优先 / 实时日志"
}

class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.master.title(STR["title"])
        self.master.geometry("980x680")
        try:
            style = ttk.Style()
            style.theme_use("clam")
        except Exception:
            pass

        self.var_excel = tk.StringVar(value=str(PROJECT_ROOT / "data" / "MLS Chinese.xlsx"))
        self.var_namemap = tk.StringVar(value=str(PROJECT_ROOT / "data" / "name_map.json"))
        self.var_lang_code = tk.StringVar(value="zh-CN")
        self.var_lang_choice = tk.StringVar(value="Chinese (Simplified) (zh-CN)")
        self.var_provider = tk.StringVar(value="deepseek")
        self.var_model = tk.StringVar(value="deepseek-ai/DeepSeek-V3.2-Exp")
        self.var_workers = tk.IntVar(value=8)
        self.var_minw = tk.IntVar(value=2)
        self.var_maxw = tk.IntVar(value=12)
        self.var_rpm = tk.IntVar(value=60)
        self.var_glossary_max = tk.IntVar(value=300)
        self.var_mode = tk.StringVar(value="scene")
        self.var_resume = tk.BooleanVar(value=True)
        self.var_include_system = tk.BooleanVar(value=False)

        self.grid(sticky="nsew")
        self.master.rowconfigure(0, weight=0)
        self.master.rowconfigure(1, weight=1)
        self.master.columnconfigure(0, weight=1)

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="we")
        controls.columnconfigure(1, weight=1)

        # Files
        sec_files = ttk.LabelFrame(controls, text=STR["sec_files"], padding=8)
        sec_files.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0,8))
        sec_files.columnconfigure(1, weight=1)
        ttk.Label(sec_files, text=STR["excel"]).grid(row=0, column=0, sticky="e", padx=(0,6), pady=2)
        ttk.Entry(sec_files, textvariable=self.var_excel).grid(row=0, column=1, sticky="we", pady=2)
        ttk.Button(sec_files, text="Browse..." if "中文" not in STR["title"] else "选择...", command=self.browse_excel).grid(row=0, column=2, padx=6, pady=2)
        ttk.Label(sec_files, text=STR["name_map"]).grid(row=1, column=0, sticky="e", padx=(0,6), pady=2)
        ttk.Entry(sec_files, textvariable=self.var_namemap).grid(row=1, column=1, sticky="we", pady=2)
        ttk.Button(sec_files, text="Browse..." if "中文" not in STR["title"] else "选择...", command=self.browse_namemap).grid(row=1, column=2, padx=6, pady=2)

        # Language & Model
        sec_lang = ttk.LabelFrame(controls, text=STR["sec_lang"], padding=8)
        sec_lang.grid(row=1, column=0, sticky="we", pady=(0,8))
        sec_lang.columnconfigure(1, weight=1)
        ttk.Label(sec_lang, text=STR["target_lang"]).grid(row=0, column=0, sticky="e", padx=(0,6), pady=2)
        choices = [f"{label} ({code})" for (label, code) in LANG_CHOICES]
        self.combo_lang = ttk.Combobox(sec_lang, textvariable=self.var_lang_choice, values=choices, width=32)
        self.combo_lang.grid(row=0, column=1, sticky="w", pady=2)
        self.combo_lang.bind("<<ComboboxSelected>>", self.on_lang_change)
        ttk.Label(sec_lang, text=STR["custom_code"]).grid(row=0, column=2, sticky="e", padx=(18,6))
        ttk.Entry(sec_lang, textvariable=self.var_lang_code, width=12).grid(row=0, column=3, sticky="w")
        ttk.Label(sec_lang, text=STR["provider"]).grid(row=1, column=0, sticky="e", padx=(0,6), pady=2)
        ttk.Combobox(sec_lang, textvariable=self.var_provider, values=["deepseek","openai"], width=12, state="readonly").grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(sec_lang, text=STR["model"]).grid(row=1, column=2, sticky="e", padx=(18,6))
        ttk.Entry(sec_lang, textvariable=self.var_model, width=30).grid(row=1, column=3, sticky="w")

        # Performance
        sec_perf = ttk.LabelFrame(controls, text=STR["sec_perf"], padding=8)
        sec_perf.grid(row=1, column=1, sticky="we", padx=(8,0), pady=(0,8))
        for c in range(6):
            sec_perf.columnconfigure(c, weight=0)
        sec_perf.columnconfigure(5, weight=1)
        ttk.Label(sec_perf, text=STR["workers"]).grid(row=0, column=0, sticky="e", padx=(0,6), pady=2)
        ttk.Spinbox(sec_perf, from_=1, to=64, textvariable=self.var_workers, width=6).grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(sec_perf, text=STR["min"]).grid(row=0, column=2, sticky="e", padx=(12,6))
        ttk.Spinbox(sec_perf, from_=1, to=64, textvariable=self.var_minw, width=6).grid(row=0, column=3, sticky="w")
        ttk.Label(sec_perf, text=STR["max"]).grid(row=0, column=4, sticky="e", padx=(12,6))
        ttk.Spinbox(sec_perf, from_=1, to=64, textvariable=self.var_maxw, width=6).grid(row=0, column=5, sticky="w")
        ttk.Label(sec_perf, text=STR["rpm"]).grid(row=1, column=0, sticky="e", padx=(0,6))
        ttk.Spinbox(sec_perf, from_=10, to=5000, textvariable=self.var_rpm, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(sec_perf, text=STR["glossary_max"]).grid(row=1, column=2, sticky="e", padx=(12,6))
        ttk.Spinbox(sec_perf, from_=50, to=1000, textvariable=self.var_glossary_max, width=8).grid(row=1, column=3, sticky="w")

        # Options
        sec_opt = ttk.LabelFrame(controls, text=STR["sec_opt"], padding=8)
        sec_opt.grid(row=2, column=0, columnspan=2, sticky="we", pady=(0,8))
        sec_opt.columnconfigure(1, weight=1)
        ttk.Label(sec_opt, text=STR["context_mode"]).grid(row=0, column=0, sticky="e", padx=(0,6))
        ttk.Radiobutton(sec_opt, text=STR["scene"], variable=self.var_mode, value="scene").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(sec_opt, text=STR["window"], variable=self.var_mode, value="window").grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(sec_opt, text=STR["include_system"], variable=self.var_include_system).grid(row=0, column=3, sticky="w")
        ttk.Checkbutton(sec_opt, text=STR["resume"], variable=self.var_resume).grid(row=0, column=4, sticky="w")

        # Buttons
        btns = ttk.Frame(controls)
        btns.grid(row=3, column=0, columnspan=2, sticky="we")
        ttk.Button(btns, text=STR["run_full"], command=self.run_full).pack(side="left", padx=4, pady=4)
        ttk.Button(btns, text=STR["run_translate"], command=self.run_translate).pack(side="left", padx=4, pady=4)
        ttk.Button(btns, text=STR["open_artifacts"], command=self.open_artifacts).pack(side="left", padx=4, pady=4)
        ttk.Button(btns, text=STR["open_config"], command=self.open_config).pack(side="left", padx=4, pady=4)
        ttk.Button(btns, text=STR["help"], command=self.show_help).pack(side="left", padx=4, pady=4)
        ttk.Button(btns, text=STR["stop"], command=self.stop).pack(side="right", padx=4, pady=4)

        self.logbox = scrolledtext.ScrolledText(self, height=22, font=("Consolas", 10))
        self.logbox.grid(row=1, column=0, sticky="nsew", pady=(8,0))
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.status = ttk.Label(self, text=STR["ready"], anchor="w")
        self.status.grid(row=2, column=0, sticky="we")

        self.stop_flag = {"stop": False}
        self.worker = None

    def on_lang_change(self, _evt=None):
        choice = self.var_lang_choice.get().strip()
        code = parse_code_from_choice(choice)
        self.var_lang_code.set(code)

    def browse_excel(self):
        p = filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")])
        if p: self.var_excel.set(p)

    def browse_namemap(self):
        p = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if p: self.var_namemap.set(p)

    def log(self, msg):
        self.logbox.insert("end", msg)
        self.logbox.see("end")
        self.status.config(text=msg.strip()[:120])
        self.update_idletasks()

    def _cmds_full(self):
        excel = self.var_excel.get()
        nm = self.var_namemap.get()
        lang = self.var_lang_code.get() or "zh-CN"
        workers, minw, maxw, rpm = self.var_workers.get(), self.var_minw.get(), self.var_maxw.get(), self.var_rpm.get()
        mode = self.var_mode.get()
        inc_sys = self.var_include_system.get()

        cmds = []
        cmds.append([sys.executable, "-m", "scripts.05_segment_context", "--excel", excel] + (["--include-system"] if inc_sys else []))

        tcmd = [sys.executable, "-m", "scripts.12_llm_translate", "--excel", excel,
                "--target-lang", lang, "--context-mode", mode, "--glossary", nm, "--glossary-max", str(300),
                "--workers", str(workers), "--min-workers", str(minw), "--max-workers", str(maxw), "--rpm", str(rpm),
                "--autosave-every", "200", "--checkpoint-file", "artifacts/ckpt.translate.jsonl", "--resume"]
        cmds.append(tcmd)

        xl1 = excel.replace(".xlsx", f".{lang}.llm.xlsx")
        ecmd = [sys.executable, "-m", "scripts.20_enforce_terms", "--excel", xl1, "--name-map", nm,
                "--target-lang", lang, "--guard-by", "BOTH",
                "--autosave-every", "500", "--checkpoint-file", "artifacts/ckpt.enforce.jsonl", "--resume"]
        cmds.append(ecmd)

        xl2 = xl1.replace(".llm.xlsx", ".terms.xlsx")
        scmd = [sys.executable, "-m", "scripts.30_style_adapt", "--excel", xl2, "--target-lang", lang,
                "--punct-map", "config/punct.zh-CN.yaml",
                "--autosave-every", "800", "--checkpoint-file", "artifacts/ckpt.style.jsonl", "--resume"]
        cmds.append(scmd)

        xl3 = xl2.replace(".terms.xlsx", ".styled.xlsx")
        recmd = [sys.executable, "-m", "scripts.21_enforce_terms_again", "--excel", xl3, "--name-map", nm,
                 "--target-lang", lang, "--guard-by", "BOTH"]
        cmds.append(recmd)

        xl4 = xl3.replace(".styled.xlsx", f".styled.{lang}.terms.xlsx")
        qcmd = [sys.executable, "-m", "scripts.25_qa_check", "--excel", xl4, "--out", f"data/report.{lang}.qa.xlsx"]
        cmds.append(qcmd)

        return cmds

    def run_full(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Running", "A task is already running." if "中文" not in STR["title"] else "已有任务在运行")
            return
        self.stop_flag["stop"] = False
        cmds = self._cmds_full()
        self.worker = threading.Thread(target=self._run_cmds, args=(cmds,))
        self.worker.daemon = True
        self.worker.start()

    def run_translate(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Running", "A task is already running." if "中文" not in STR["title"] else "已有任务在运行")
            return
        self.stop_flag["stop"] = False
        excel = self.var_excel.get()
        nm = self.var_namemap.get()
        lang = self.var_lang_code.get() or "zh-CN"
        workers, minw, maxw, rpm = self.var_workers.get(), self.var_minw.get(), self.var_maxw.get(), self.var_rpm.get()
        mode = self.var_mode.get()
        inc_sys = self.var_include_system.get()
        cmd = [sys.executable, "-m", "scripts.12_llm_translate", "--excel", excel, "--target-lang", lang,
               "--context-mode", mode, "--glossary", nm, "--glossary-max", "300", "--workers", str(workers),
               "--min-workers", str(minw), "--max-workers", str(maxw), "--rpm", str(rpm),
               "--autosave-every", "200", "--checkpoint-file", "artifacts/ckpt.translate.jsonl", "--resume"]
        if inc_sys: cmd.append("--include-system")
        self.worker = threading.Thread(target=self._run_cmds, args=([cmd],))
        self.worker.daemon = True
        self.worker.start()

    def _run_cmds(self, cmds):
        self.log(f"== Workdir: {PROJECT_ROOT}\n")
        for i, cmd in enumerate(cmds, 1):
            self.log(f"\n== Step {i}/{len(cmds)}: {' '.join(cmd)}\n")
            rc = run_cmd(cmd, cwd=str(PROJECT_ROOT), log=self.log, stop_flag=self.stop_flag)
            if rc != 0:
                self.log(f"[ERROR] Step {i} failed with code {rc}\n" if "中文" not in STR["title"] else f"[错误] 第 {i} 步失败，返回码 {rc}\n")
                break
        else:
            self.log("\n== ALL DONE ==\n" if "中文" not in STR["title"] else "\n== 全部完成 ==\n")

    def stop(self):
        self.stop_flag["stop"] = True
        self.status.config(text="Stopping..." if "中文" not in STR["title"] else "正在停止...")

    def open_artifacts(self):
        p = PROJECT_ROOT / "artifacts"
        p.mkdir(exist_ok=True, parents=True)
        try:
            if os.name == "nt":
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.call(["open", str(p)])
            else:
                subprocess.call(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showerror("Open artifacts" if "中文" not in STR["title"] else "打开 artifacts", str(e))

    def open_config(self):
        p = PROJECT_ROOT / "config"
        p.mkdir(exist_ok=True, parents=True)
        try:
            if os.name == "nt":
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.call(["open", str(p)])
            else:
                subprocess.call(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showerror("Open config" if "中文" not in STR["title"] else "打开 config", str(e))

    def show_help(self):
        messagebox.showinfo("Help" if "中文" not in STR["title"] else "帮助", STR["help_text"])

def main():
    root = tk.Tk()
    App(root)
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    root.mainloop()

if __name__ == "__main__":
    main()
