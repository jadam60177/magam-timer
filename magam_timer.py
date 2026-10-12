# -*- coding: utf-8 -*-
"""
마감의 숲 집필 타이머 (배포판)

- 고른 프로그램(한글·워드 등) 창에서 입력하고 있을 때만 시간이 흘러요.
- 키보드를 직접 들여다보지 않아요. 윈도우가 알려 주는 "마지막으로 입력이 있었던 시각"과
  마우스 위치만 보고, 마우스가 그대로인데 입력이 있었으면 타자를 친 걸로 셈해요.
- 인터넷에 연결하지 않아요. 기록은 이 컴퓨터의 %APPDATA%\\MagamForestTimer 에만 저장돼요.
"""
import tkinter as tk
from tkinter import messagebox
import time, json, os, sys, random, traceback
import datetime as dt
from pathlib import Path

APP_NAME = "마감의 숲 집필 타이머"
APP_VER = "1.0.0"
IS_WIN = sys.platform.startswith("win")

# ── 경로 ─────────────────────────────────────────────
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BG_DIR = RES_DIR / "timer_bg"
FONT_FILE = RES_DIR / "RamilRound.ttf"
ICON_PNG = RES_DIR / "icon.png"
if os.environ.get("TIMER_DIR"):
    DATA_DIR = Path(os.environ["TIMER_DIR"])
elif IS_WIN:
    DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "MagamForestTimer"
else:
    DATA_DIR = Path.home() / ".magam_timer"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
DATA_FILE = DATA_DIR / "timer_data.json"
SET_FILE = DATA_DIR / "timer_settings.json"
ERR_FILE = DATA_DIR / "error.log"
DEMO = os.environ.get("TIMER_DEMO")          # 미리보기용
SELFTEST = os.environ.get("MAGAM_SELFTEST")  # 자동 점검용


def log_error(where):
    try:
        with open(ERR_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {where}\n{traceback.format_exc()}\n")
    except Exception:
        pass


# ── 윈도우 기능 (키보드 감시 없음) ───────────────────
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32")

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
    kernel32.GetTickCount.restype = wintypes.DWORD
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    gdi32.AddFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    gdi32.AddFontResourceExW.restype = ctypes.c_int
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    except Exception:
        dwmapi = None

    try:  # 고해상도 화면에서 흐릿하지 않게
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    if FONT_FILE.exists():
        try:  # 컴퓨터에 설치하지 않고 이 프로그램 안에서만 쓰기 (FR_PRIVATE)
            gdi32.AddFontResourceExW(str(FONT_FILE), 0x10, None)
        except Exception:
            pass

    def last_input_tick():
        li = LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(li)):
            return int(li.dwTime)
        return None

    def idle_seconds(tick):
        return ((int(kernel32.GetTickCount()) - tick) & 0xFFFFFFFF) / 1000.0

    def cursor_pos():
        p = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(p)):
            return (p.x, p.y)
        return None

    def window_title(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    _exe_cache = {}

    def window_pid_exe(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        p = int(pid.value)
        if p in _exe_cache:
            return p, _exe_cache[p]
        exe = ""
        h = kernel32.OpenProcess(0x1000, False, p)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                buf = ctypes.create_unicode_buffer(520)
                size = wintypes.DWORD(520)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    exe = os.path.basename(buf.value)
            finally:
                kernel32.CloseHandle(h)
        if len(_exe_cache) > 300:
            _exe_cache.clear()
        _exe_cache[p] = exe
        return p, exe

    def foreground():
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, "", ""
        pid, exe = window_pid_exe(hwnd)
        return pid, window_title(hwnd), exe

    def _cloaked(hwnd):
        if not dwmapi:
            return False
        v = ctypes.c_int(0)
        try:
            dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), ctypes.sizeof(v))  # DWMWA_CLOAKED
        except Exception:
            return False
        return v.value != 0

    def list_windows():
        out, seen = [], set()
        me = os.getpid()

        def cb(hwnd, lparam):
            try:
                if not user32.IsWindowVisible(hwnd) or _cloaked(hwnd):
                    return True
                t = window_title(hwnd).strip()
                if not t or t in ("Program Manager",):
                    return True
                pid, exe = window_pid_exe(hwnd)
                if pid == me:
                    return True
                k = (t, exe.lower())
                if k not in seen:
                    seen.add(k)
                    out.append((t, exe))
            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out

    def single_instance():
        h = kernel32.CreateMutexW(None, False, "Local\\MagamForestWritingTimer")
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        return h, already
else:
    def last_input_tick():
        return None

    def idle_seconds(tick):
        return 0.0

    def cursor_pos():
        return None

    def foreground():
        return None, "", ""

    def list_windows():
        if DEMO:
            return [("2화 원고.hwp [C:\\원고\\] - 한글", "Hwp.exe"),
                    ("조아라 - 작품 관리 - Chrome", "chrome.exe"),
                    ("연재 메모.txt - 메모장", "notepad.exe"),
                    ("마감의 숲 - Discord", "Discord.exe")]
        return []

    def single_instance():
        return None, False

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter
except ImportError:  # 배포판(exe)에는 늘 들어 있음
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror(APP_NAME, "pillow 가 필요해요:  pip install pillow")
    sys.exit()

# ── 감지할 프로그램 ───────────────────────────────────
# (코드, 이름, 실행 파일 이름들, 창 제목에 들어가는 글자들)
PRESETS = [
    ("hwp", "한글", {"hwp.exe"}, [".hwp", " - 한글", "hancom"]),
    ("word", "워드", {"winword.exe"}, []),
    ("notepad", "메모장", {"notepad.exe"}, []),
    ("scrivener", "스크리브너", {"scrivener.exe", "scrivener3.exe"}, []),
    ("gdocs", "구글 문서 (웹)", set(), ["google docs", "google 문서"]),
]
BROWSERS = {"chrome.exe", "msedge.exe", "whale.exe", "firefox.exe", "opera.exe", "brave.exe", "iexplore.exe"}

# ── 시간대 ────────────────────────────────────────────
PHASES = [
    (4,  "dawn",      "새벽", "✧", "새벽이 밝아 오고 있어요"),
    (7,  "morning",   "아침", "☀", "아침이 됐어요"),
    (11, "day",       "낮",   "☀", "한낮이에요"),
    (15, "afternoon", "오후", "☼", "오후가 됐어요"),
    (18, "evening",   "저녁", "☽", "저녁이 됐어요"),
    (21, "night",     "밤",   "☾", "밤이 깊었어요"),
]
PHASE_BY_KEY = {p[1]: p for p in PHASES}


def phase_of(hour):
    cur = PHASES[-1]
    for p in PHASES:
        if hour >= p[0]:
            cur = p
    return cur


DEFAULTS = {
    "idle": 3.0,
    "goal_hours": 3.0,
    "day_start": 5,
    "phase_mode": "auto",
    "alpha": 100,
    "topmost": True,
    "sound": True,
    "hourly": True,
    "mini": False,
    "pos": None,
    "presets": {"hwp": True, "word": True, "notepad": False, "scrivener": False, "gdocs": False},
    "custom": [],  # [{"kind": "exe"|"title", "value": "..."}]
}

# 색
C_TEXT = "#F6EBDD"
C_SUB = "#D9C9B6"
C_TYPING = "#A8F0C6"
C_IDLE = "#E9DCCB"
C_PAUSE = "#FFB98A"
C_GOLD = "#FFD27A"
C_MUTED = "#9c8c93"
PAL_DARK = dict(text=C_TEXT, sub=C_SUB, typing=C_TYPING, idle=C_IDLE, pause=C_PAUSE, gold=C_GOLD,
                shadow="#120d0a", pill="#2a211c", pill_hover="#4a3a2e", pill_line="#8a6e55",
                bar_bg="#3a302a", stopped="#bfae9c", bar_idle="#cdb89e", goal_done=C_GOLD)
PAL_LIGHT = dict(text="#3a2a1e", sub="#6b5444", typing="#2c8456", idle="#4a3628", pause="#c0622a", gold=C_GOLD,
                 shadow="#fffaf0", pill="#fff8ec", pill_hover="#f1e3c9", pill_line="#c9ab86",
                 bar_bg="#e3d3bd", stopped="#8a7464", bar_idle="#b59a78", goal_done="#b07a14")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:
        log_error("save_json")


def fmt_hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def fmt_hm(sec):
    m = int(sec // 60)
    h, m = divmod(m, 60)
    if h and m:
        return f"{h}시간 {m}분"
    if h:
        return f"{h}시간"
    return f"{m}분"


def fmt_goal(hours):
    h = float(hours)
    if h == int(h):
        return f"{int(h)}시간"
    if h < 1:
        return f"{int(round(h * 60))}분"
    return f"{int(h)}시간 {int(round((h - int(h)) * 60))}분"


def pick_font(root, cands):
    from tkinter import font as tkfont
    fams = {f.lower(): f for f in tkfont.families(root)}
    for c in cands:
        if c.lower() in fams:
            return fams[c.lower()]
    return cands[-1]


def custom_label(c):
    if c.get("kind") == "exe":
        return f"{c['value']}  (프로그램 전체)"
    return f"창 제목에 '{c['value']}'"


class TimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.resizable(False, False)
        self.errors = []
        try:
            if ICON_PNG.exists():
                self._icon = tk.PhotoImage(file=str(ICON_PNG))
                self.root.iconphoto(True, self._icon)
        except Exception:
            pass

        self.sc = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.f_ko = pick_font(root, ["RamilRound", "Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR",
                                     "NanumGothic", "minikr", "TkDefaultFont"])
        self.round = self.f_ko.lower() == "ramilround"

        first_run = not SET_FILE.exists()
        self.set = json.loads(json.dumps(DEFAULTS))
        self.set.update(load_json(SET_FILE, {}))
        for k, v in DEFAULTS["presets"].items():
            self.set.setdefault("presets", {}).setdefault(k, v)
        self.data = load_json(DATA_FILE, {"days": {}})
        self.data.setdefault("days", {})

        self.is_running = True
        self.is_typing = False
        self.on_target = False
        self.last_key_time = 0.0
        self.last_update = time.time()
        self.last_save = time.time()
        self._last_li = last_input_tick()
        self._last_pos = cursor_pos()
        self.toast_until = 0.0
        self.toast_text = ""
        self.stats_win = None
        self.set_win = None

        self.today = self.day_key()
        self.ensure_day(self.today)

        self.bg_src, self.bg_count = self.load_backgrounds()
        self.baked = {}
        self.light_of = {}
        self.cur_phase = self.wanted_phase()
        self.last_auto_phase = phase_of(dt.datetime.now().hour)[1]
        self.last_hour = dt.datetime.now().hour
        self.fade = None

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, bg="#151017")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Double-Button-1>", self.on_double)

        self.apply_window_settings()
        self.build_layout()

        if DEMO:
            self.fill_demo()
        elif first_run:
            self.root.after(800, lambda: self.show_toast("설정에서 글 쓰는 프로그램을 확인해 주세요", 20))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tick()

    # ── 기록 ───────────────────────────────────────────
    def day_key(self, t=None):
        now = dt.datetime.fromtimestamp(t or time.time())
        now -= dt.timedelta(hours=int(self.set.get("day_start", 5)))
        return now.strftime("%Y-%m-%d")

    def ensure_day(self, key):
        d = self.data["days"].setdefault(key, {})
        d.setdefault("sec", 0.0)
        d.setdefault("goal_done", False)
        return d

    @property
    def td(self):
        return self.ensure_day(self.today)

    def save_all(self):
        save_json(DATA_FILE, self.data)
        save_json(SET_FILE, self.set)
        self.last_save = time.time()

    # ── 입력 감지 (키보드 내용은 보지 않음) ─────────────
    def is_target(self, pid, title, exe):
        if pid == os.getpid():
            return False
        t, e = title.lower(), exe.lower()
        pre = self.set.get("presets", {})
        for code, _name, exes, titles in PRESETS:
            if pre.get(code) and (e in exes or any(k in t for k in titles)):
                return True
        for c in self.set.get("custom", []):
            v = str(c.get("value", "")).lower()
            if not v:
                continue
            if c.get("kind") == "exe" and e == v:
                return True
            if c.get("kind") == "title" and v in t:
                return True
        return False

    def poll_input(self):
        pid, title, exe = foreground()
        self.fg_pid = pid
        self.on_target = self.is_target(pid, title, exe) if pid is not None else False
        li = last_input_tick()
        pos = cursor_pos()
        if li is not None and li != self._last_li:
            moved = pos is not None and self._last_pos is not None and pos != self._last_pos
            if not moved and self.on_target and self.is_running:
                self.last_key_time = time.time() - min(idle_seconds(li), 1.0)
            self._last_li = li
        self._last_pos = pos

    def has_any_target(self):
        return any(self.set.get("presets", {}).values()) or bool(self.set.get("custom"))

    # ── 창 ─────────────────────────────────────────────
    def S(self, v):
        return int(round(v * self.sc))

    def size(self):
        return (290, 84) if self.set.get("mini") else (460, 258)

    def apply_window_settings(self):
        w, h = self.size()
        geo = f"{self.S(w)}x{self.S(h)}"
        pos = self.set.get("pos")
        if pos:
            x, y = pos
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            if 0 <= x < sw - 40 and 0 <= y < sh - 40:
                geo += f"+{x}+{y}"
        self.root.geometry(geo)
        self.root.attributes("-topmost", bool(self.set.get("topmost", True)))
        try:
            self.root.attributes("-alpha", max(0.3, min(1.0, self.set.get("alpha", 100) / 100)))
        except Exception:
            pass

    def remember_pos(self):
        try:
            self.set["pos"] = [self.root.winfo_x(), self.root.winfo_y()]
        except Exception:
            pass

    def on_double(self, e):
        for t in self.canvas.gettags("current"):
            if t.startswith("pill"):
                return
        self.toggle_mini()

    def child_pos(self, h):
        self.root.update_idletasks()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        rh = self.root.winfo_height()
        sh = self.root.winfo_screenheight()
        ny = y + rh + self.S(40)
        if ny + self.S(h) > sh - self.S(40):
            ny = max(0, y - self.S(h) - self.S(40))
        return f"+{max(0, x)}+{ny}"

    def toggle_mini(self):
        self.remember_pos()
        self.set["mini"] = not self.set.get("mini")
        self.apply_window_settings()
        self.build_layout()
        self.save_all()

    # ── 배경 그림 ─────────────────────────────────────
    def load_backgrounds(self):
        src = {}
        for _, key, *_ in PHASES:
            for ext in (".webp", ".png", ".jpg", ".jpeg"):
                p = BG_DIR / f"bg_{key}{ext}"
                if p.exists():
                    try:
                        src[key] = Image.open(p).convert("RGB")
                        break
                    except Exception:
                        log_error(f"bg {p}")
        count = len(src)
        if not src:
            src["night"] = Image.new("RGB", (1200, 670), (30, 24, 34))
        fallback = src.get("night") or next(iter(src.values()))
        for _, key, *_ in PHASES:
            src.setdefault(key, fallback)
        return src, count

    def wanted_phase(self):
        m = self.set.get("phase_mode", "auto")
        if m in PHASE_BY_KEY:
            return m
        return phase_of(dt.datetime.now().hour)[1]

    def bake(self, phase):
        mini = bool(self.set.get("mini"))
        w, h = self.S(self.size()[0]), self.S(self.size()[1])
        k = (phase, w, h, mini)
        if k in self.baked:
            self.light_of[phase] = self.baked[k][1]
            return self.baked[k][0]
        src = self.bg_src[phase]
        sw, sh = src.size
        sc = max(w / sw, h / sh)
        img = src.resize((max(w, int(sw * sc + 0.5)), max(h, int(sh * sc + 0.5))), Image.LANCZOS)
        fx, fy = (0.5, 0.42) if mini else (0.5, 0.5)
        x0 = int((img.width - w) * fx); y0 = int((img.height - h) * fy)
        img = img.crop((x0, y0, x0 + w, y0 + h))
        lum = sum(img.convert("L").crop((int(w * .25), int(h * .2), int(w * .75), int(h * .75)))
                  .resize((8, 8)).tobytes()) / 64
        light = lum > 140
        self.light_of[phase] = light
        a = int(max(95, min(185, 40 + lum * 1.35))) if not light else int(max(120, min(175, lum * 0.8)))
        mask = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(mask)
        if mini:
            d.rectangle((0, 0, w, h), fill=int(a * .85))
        else:
            r = self.S(26)
            d.rounded_rectangle((int(w * .15), int(h * .19), int(w * .85), int(h * .76)), r, fill=a)
            for yy in range(int(h * .17)):
                d.line((0, yy, w, yy), fill=max(int(a * .8 * (1 - yy / (h * .17))), 0) if yy > h * .02 else int(a * .8))
            for yy in range(int(h * .76), h):
                t = (yy - h * .76) / (h * .24)
                d.line((0, yy, w, yy), fill=int(a * .75 * min(1, t * 1.4)))
        mask = mask.filter(ImageFilter.GaussianBlur(self.S(12) if not mini else 2))
        dark = Image.new("RGB", (w, h), (252, 246, 236) if light else (14, 10, 16))
        out = Image.composite(dark, img, mask)
        self.baked[k] = (out, light)
        return out

    def set_bg_image(self, pil):
        self._bg_tk = ImageTk.PhotoImage(pil)
        self.canvas.itemconfigure(self.bg_item, image=self._bg_tk)

    def start_fade(self, new_phase):
        old = self.bake(self.cur_phase)
        new = self.bake(new_phase)
        self.cur_phase = new_phase
        self.fade = (old, new, 0)
        self._fade_step()

    def _fade_step(self):
        if not self.fade:
            return
        old, new, i = self.fade
        i += 1
        steps = 24
        self.set_bg_image(Image.blend(old, new, min(1, i / steps)))
        if i < steps:
            self.fade = (old, new, i)
            self.root.after(70, self._fade_step)
        else:
            self.fade = None
            want_light = bool(self.light_of.get(self.cur_phase))
            if want_light != (self.P is PAL_LIGHT):
                toast, until = self.toast_text, self.toast_until
                self.build_layout()
                if toast and time.time() < until:
                    self.show_toast(toast, until - time.time())

    # ── 화면 그리기 ───────────────────────────────────
    def text(self, x, y, s, size, color, anchor="center"):
        f = (self.f_ko, size)
        o = max(1, self.S(1))
        sh = self.canvas.create_text(self.S(x) + o, self.S(y) + o, text=s, font=f, fill=self.P["shadow"], anchor=anchor)
        fg = self.canvas.create_text(self.S(x), self.S(y), text=s, font=f, fill=color, anchor=anchor)
        return (sh, fg)

    def time_text(self, x, y, size, color, anchor="center"):
        from tkinter import font as tkfont
        fnt = tkfont.Font(root=self.root, family=self.f_ko, size=size, weight="normal" if self.round else "bold")
        dw = max(fnt.measure(d) for d in "0123456789")
        cw = int(fnt.measure(":") * 1.25)
        widths = [dw, dw, cw, dw, dw, cw, dw, dw]
        cx = self.S(x) - sum(widths) / 2 if anchor == "center" else self.S(x)
        o = max(1, self.S(1))
        pairs = []
        for wd in widths:
            mx = cx + wd / 2
            sh = self.canvas.create_text(mx + o, self.S(y) + o, text="0", font=fnt, fill=self.P["shadow"])
            fg = self.canvas.create_text(mx, self.S(y), text="0", font=fnt, fill=color)
            pairs.append((sh, fg))
            cx += wd
        self._time_font = fnt
        return pairs

    def set_time(self, pairs, s, color):
        for pair, ch in zip(pairs, s):
            self.set_text(pair, ch, color)

    def set_text(self, pair, s=None, color=None):
        sh, fg = pair
        if s is not None:
            self.canvas.itemconfigure(sh, text=s)
            self.canvas.itemconfigure(fg, text=s)
        if color is not None:
            self.canvas.itemconfigure(fg, fill=color)

    def round_rect(self, x1, y1, x2, y2, r, **kw):
        x1, y1, x2, y2, r = [self.S(v) for v in (x1, y1, x2, y2, r)]
        r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def pill(self, cx, cy, w, h, label, cmd, size=9):
        tag = f"pill{id(cmd)}{cx}{cy}"
        bgid = self.round_rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, h / 2,
                               fill=self.P["pill"], outline=self.P["pill_line"], width=max(1, self.S(1)), tags=(tag,))
        tid = self.canvas.create_text(self.S(cx), self.S(cy), text=label, font=(self.f_ko, size),
                                      fill=self.P["text"], tags=(tag,))
        self.canvas.tag_bind(tag, "<Enter>", lambda e: (self.canvas.itemconfigure(bgid, fill=self.P["pill_hover"]),
                                                        self.canvas.config(cursor="hand2")))
        self.canvas.tag_bind(tag, "<Leave>", lambda e: (self.canvas.itemconfigure(bgid, fill=self.P["pill"]),
                                                        self.canvas.config(cursor="")))
        self.canvas.tag_bind(tag, "<Button-1>", lambda e: cmd())
        self.canvas.tag_bind(tag, "<Double-Button-1>", lambda e: "break")
        return tid

    def build_layout(self):
        c = self.canvas
        c.delete("all")
        self.fade = None
        self.cur_phase = self.wanted_phase()
        self.bg_item = c.create_image(0, 0, anchor="nw")
        self.set_bg_image(self.bake(self.cur_phase))
        self.P = PAL_LIGHT if self.light_of.get(self.cur_phase) else PAL_DARK
        mini = bool(self.set.get("mini"))
        w, h = self.size()
        self.toast_items = []

        if mini:
            self.t_time = self.time_text(16, 30, 24, self.P["idle"], anchor="w")
            self.t_status = self.text(16, 58, "", 10, self.P["sub"], anchor="w")
            self.t_clock = self.text(w - 14, 16, "", 10, self.P["sub"], anchor="e")
            self.bar_x, self.bar_y, self.bar_w = 16, 74, 170
            self.pill(w - 36, 52, 50, 26, "크게", self.toggle_mini, 11)
            self.pause_tid = None
        else:
            self.t_clock = self.text(16, 21, "", 12, self.P["sub"], anchor="w")
            self.pill(w - 152, 21, 52, 28, "통계", self.open_stats, 11)
            self.pill(w - 95, 21, 52, 28, "설정", self.open_settings, 11)
            self.pill(w - 38, 21, 52, 28, "작게", self.toggle_mini, 11)
            self.t_status = self.text(w / 2, 74, "", 13, self.P["sub"])
            self.t_time = self.time_text(w / 2, 115, 38, self.P["idle"])
            self.bar_x, self.bar_y, self.bar_w = w / 2 - 140, 158, 280
            self.t_goal = self.text(w / 2, 180, "", 12, self.P["sub"])
            self.pause_tid = self.pill(w / 2 - 58, 227, 104, 34, "일시정지" if self.is_running else "다시 시작",
                                       self.toggle_pause, 13)
            self.pill(w / 2 + 58, 227, 104, 34, "초기화", self.reset_today, 13)

        bh = 5 if mini else 8
        self.bar_bg = self.round_rect(self.bar_x, self.bar_y - bh / 2, self.bar_x + self.bar_w, self.bar_y + bh / 2,
                                      bh / 2, fill=self.P["bar_bg"], outline="")
        self.bar_fg = self.round_rect(self.bar_x, self.bar_y - bh / 2, self.bar_x + 1, self.bar_y + bh / 2,
                                      bh / 2, fill=self.P["typing"], outline="")
        self.bar_h = bh
        self._last_bar = None
        self.refresh()

    def draw_bar(self, ratio, color):
        ratio = max(0.0, min(1.0, ratio))
        key = (round(ratio, 3), color)
        if key == self._last_bar:
            return
        self._last_bar = key
        self.canvas.delete(self.bar_fg)
        bh = self.bar_h
        x2 = self.bar_x + max(bh, self.bar_w * ratio)
        self.bar_fg = self.round_rect(self.bar_x, self.bar_y - bh / 2, x2, self.bar_y + bh / 2, bh / 2,
                                      fill=color, outline="")
        if ratio <= 0:
            self.canvas.itemconfigure(self.bar_fg, state="hidden")

    def show_toast(self, msg, secs=8):
        self.toast_text = msg
        self.toast_until = time.time() + secs
        for it in self.toast_items:
            self.canvas.delete(it)
        self.toast_items = []
        if self.set.get("mini"):
            return
        w, _ = self.size()
        f = (self.f_ko, 12) if self.round else (self.f_ko, 10, "bold")
        tid = self.canvas.create_text(self.S(w / 2), self.S(47), text=msg, font=f, fill="#3a2a1c")
        x1, y1, x2, y2 = self.canvas.bbox(tid)
        pad = self.S(12)
        bid = self.round_rect((x1 - pad) / self.sc, (y1 - self.S(4)) / self.sc, (x2 + pad) / self.sc,
                              (y2 + self.S(4)) / self.sc, 12, fill=C_GOLD, outline="")
        self.canvas.tag_raise(tid)
        self.toast_items = [bid, tid]

    def hide_toast(self):
        for it in self.toast_items:
            self.canvas.delete(it)
        self.toast_items = []
        self.toast_text = ""

    def status(self):
        if not self.is_running:
            return "수동 정지됨", "멈춤", self.P["pause"]
        if self.is_typing:
            return "● 작업 중", "● 작업 중", self.P["typing"]
        if not self.has_any_target():
            return "설정에서 프로그램을 골라 주세요", "프로그램을 골라 주세요", self.P["pause"]
        if self.on_target or getattr(self, "fg_pid", None) == os.getpid() or DEMO:
            return "입력 기다리는 중", "대기 중", self.P["idle"]
        return "글 쓰는 창으로 가면 시작해요", "대기 중", self.P["idle"]

    def refresh(self):
        d = self.td
        sec = d["sec"]
        mini = bool(self.set.get("mini"))
        goal = float(self.set.get("goal_hours", 3)) * 3600
        ratio = sec / goal if goal > 0 else 0
        done = goal > 0 and sec >= goal
        st, short, col = self.status()
        now = dt.datetime.now()
        ph = PHASE_BY_KEY[phase_of(now.hour)[1]]
        self.set_text(self.t_clock, f"{ph[3]} {ph[2]}  {now:%H:%M}")
        self.set_time(self.t_time, fmt_hms(sec), col if self.is_running else self.P["stopped"])
        if mini:
            if self.toast_text and time.time() < self.toast_until:
                self.set_text(self.t_status, self.toast_text, self.P["goal_done"])
            else:
                pct = f" · 목표 {int(ratio * 100)}%" if goal > 0 else ""
                self.set_text(self.t_status, f"{short}{pct}", col if self.is_typing else self.P["sub"])
        else:
            self.set_text(self.t_status, st, col)
            if goal > 0:
                g = f"오늘 목표 {fmt_goal(self.set['goal_hours'])} · {int(ratio * 100)}%"
                if done:
                    g = f"오늘 목표 {fmt_goal(self.set['goal_hours'])} 달성 ★"
            else:
                g = "오늘 목표 없음"
            self.set_text(self.t_goal, g, self.P["goal_done"] if done else self.P["sub"])
            if self.toast_items and time.time() >= self.toast_until:
                self.hide_toast()
        self.draw_bar(ratio, self.P["gold"] if done else (self.P["typing"] if self.is_typing else self.P["bar_idle"]))

    # ── 1초에 다섯 번 도는 시계 ─────────────────────
    def tick(self):
        try:
            self._tick()
        except Exception:
            log_error("tick")
            self.errors.append(traceback.format_exc())
        finally:
            self.root.after(200, self.tick)

    def _tick(self):
        now = time.time()
        delta = now - self.last_update
        self.last_update = now

        dk = self.day_key(now)
        if dk != self.today:
            self.today = dk
            self.ensure_day(dk)
            self.save_all()
            self.show_toast("새 하루 기록을 시작해요")

        if not DEMO:
            self.poll_input()
            if self.is_running:
                typing = self.last_key_time > 0 and now - self.last_key_time <= float(self.set.get("idle", 3))
                if typing and delta < 5:  # 컴퓨터가 잠들었다 깬 시간은 안 셈
                    self.td["sec"] += delta
                self.is_typing = typing

        goal = float(self.set.get("goal_hours", 3)) * 3600
        d = self.td
        if goal > 0 and d["sec"] >= goal and not d.get("goal_done"):
            d["goal_done"] = True
            self.show_toast(f"오늘 목표 {fmt_goal(self.set['goal_hours'])} 달성! 멋져요 ★", 12)
            self.ding()
            self.save_all()

        nowdt = dt.datetime.now()
        auto_now = phase_of(nowdt.hour)[1]
        if auto_now != self.last_auto_phase:
            self.last_auto_phase = auto_now
            self.last_hour = nowdt.hour
            p = PHASE_BY_KEY[auto_now]
            self.show_toast(f"{p[3]} {p[4]} · {nowdt:%H:%M}", 10)
            self.ding()
        elif nowdt.hour != self.last_hour:
            self.last_hour = nowdt.hour
            if self.set.get("hourly", True):
                p = PHASE_BY_KEY[auto_now]
                h12 = nowdt.hour % 12 or 12
                self.show_toast(f"{p[3]} {p[2]} {h12}시예요 · 오늘 {fmt_hm(self.td['sec'])} 썼어요", 8)
        want = self.wanted_phase()
        if want != self.cur_phase and not self.fade:
            self.start_fade(want)

        self.refresh()
        if now - self.last_save > 30:
            self.save_all()

    def ding(self):
        if not self.set.get("sound", True):
            return
        try:
            if IS_WIN:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                self.root.bell()
        except Exception:
            pass

    # ── 버튼 ───────────────────────────────────────────
    def toggle_pause(self):
        self.is_running = not self.is_running
        self.is_typing = False
        self.last_update = time.time()
        if self.pause_tid:
            self.canvas.itemconfigure(self.pause_tid, text="일시정지" if self.is_running else "다시 시작")
        self.refresh()

    def reset_today(self):
        if not messagebox.askyesno(APP_NAME, "오늘 기록을 0으로 되돌릴까요?", parent=self.root):
            return
        d = self.td
        d["sec"] = 0.0
        d["goal_done"] = False
        self.last_key_time = 0.0
        self.is_typing = False
        self.save_all()
        self.refresh()

    def on_close(self):
        self.remember_pos()
        self.save_all()
        self.root.destroy()

    def open_stats(self):
        if self.stats_win and self.stats_win.winfo_exists():
            self.stats_win.lift()
            return
        StatsWindow(self)

    def open_settings(self):
        if self.set_win and self.set_win.winfo_exists():
            self.set_win.lift()
            return
        SettingsWindow(self)

    # ── 미리보기용 가짜 기록 ─────────────────────────
    def fill_demo(self):
        random.seed(7)
        base = dt.datetime.strptime(self.today, "%Y-%m-%d")
        for i in range(1, 40):
            k = (base - dt.timedelta(days=i)).strftime("%Y-%m-%d")
            if random.random() < 0.12:
                continue
            s = random.uniform(1.2, 5.2) * 3600
            self.data["days"][k] = {"sec": s, "goal_done": s > 3 * 3600}
        self.data["days"][self.today] = {"sec": 2 * 3600 + 13 * 60 + 41, "goal_done": False}
        self.is_typing = True
        self.set["custom"] = [{"kind": "title", "value": "조아라"}]
        ph = os.environ.get("TIMER_PHASE")
        if ph:
            self.set["phase_mode"] = ph
        if os.environ.get("TIMER_MINI"):
            self.set["mini"] = True
            self.apply_window_settings()
        if ph or os.environ.get("TIMER_MINI"):
            self.build_layout()
        if os.environ.get("TIMER_TOAST"):
            self.show_toast(os.environ["TIMER_TOAST"], 999)


# ══ 통계 창 ═══════════════════════════════════════════
class StatsWindow:
    BG = "#1d1820"
    CARD = "#2a2229"

    def __init__(self, app):
        self.app = app
        S = app.S
        self.win = tk.Toplevel(app.root)
        app.stats_win = self.win
        self.win.title("집필 기록")
        self.win.configure(bg=self.BG)
        self.win.resizable(False, False)
        self.win.attributes("-topmost", bool(app.set.get("topmost", True)))
        self.W, self.H = 560, 400
        self.win.geometry(f"{S(self.W)}x{S(self.H)}" + app.child_pos(self.H))
        self.range_days = 14
        self.cv = tk.Canvas(self.win, bg=self.BG, highlightthickness=0, width=S(self.W), height=S(self.H))
        self.cv.pack(fill="both", expand=True)
        self.draw()
        self._loop()

    def _loop(self):
        if not self.win.winfo_exists():
            return
        self.draw()
        self.win.after(5000, self._loop)

    def rr(self, x1, y1, x2, y2, r, **kw):
        S = self.app.S
        x1, y1, x2, y2, r = S(x1), S(y1), S(x2), S(y2), S(r)
        r = min(r, max(1, (x2 - x1) // 2), max(1, (y2 - y1) // 2))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, **kw)

    def t(self, x, y, s, size=9, color=C_TEXT, anchor="center"):
        f = (self.app.f_ko, size + 2) if self.app.round else (self.app.f_ko, size)
        return self.cv.create_text(self.app.S(x), self.app.S(y), text=s, font=f, fill=color, anchor=anchor)

    def btn(self, x, y, w, h, label, on, cmd):
        tag = f"b{label}{x}"
        self.rr(x, y, x + w, y + h, h / 2, fill=C_GOLD if on else self.CARD,
                outline="" if on else "#4a3d44", tags=(tag,))
        tid = self.t(x + w / 2, y + h / 2, label, 9, "#3a2a1c" if on else C_SUB)
        self.cv.addtag_withtag(tag, tid)
        self.cv.tag_bind(tag, "<Button-1>", lambda e: (cmd(), self.draw()))
        self.cv.tag_bind(tag, "<Enter>", lambda e: self.cv.config(cursor="hand2"))
        self.cv.tag_bind(tag, "<Leave>", lambda e: self.cv.config(cursor=""))

    def draw(self):
        app = self.app
        cv = self.cv
        cv.delete("all")
        today = dt.datetime.strptime(app.today, "%Y-%m-%d").date()
        days = app.data["days"]
        key = lambda d: d.strftime("%Y-%m-%d")
        secs = lambda ks: sum(days.get(k, {}).get("sec", 0) for k in ks)
        worked = lambda ks: sum(1 for k in ks if days.get(k, {}).get("sec", 0) >= 60)

        week = [key(today - dt.timedelta(days=i)) for i in range(today.weekday() + 1)]
        month = [key(today.replace(day=i)) for i in range(1, today.day + 1)]
        goal = float(app.set.get("goal_hours", 0))
        tsec = secs([app.today])
        sub_today = f"목표의 {int(tsec / (goal * 3600) * 100)}%" if goal > 0 else "목표 없음"
        cards = [("오늘", tsec, sub_today), ("이번 주", secs(week), f"작업한 날 {worked(week)}일"),
                 (f"{today.month}월", secs(month), f"작업한 날 {worked(month)}일")]
        self.t(24, 26, "집필 기록", 13, C_TEXT, anchor="w")
        self.t(self.W - 24, 28, f"하루는 {app.set['day_start']}시에 바뀌어요", 8, "#8f7f86", anchor="e")
        cw = (self.W - 48 - 20) / 3
        for i, (name, sec, sub) in enumerate(cards):
            x = 24 + i * (cw + 10)
            self.rr(x, 48, x + cw, 118, 14, fill=self.CARD, outline="")
            self.t(x + 14, 64, name, 9, C_SUB, anchor="w")
            self.t(x + 14, 87, fmt_hm(sec), 14, C_GOLD if i == 0 else C_TEXT, anchor="w")
            self.t(x + 14, 106, sub, 9, "#b9a8ad", anchor="w")

        self.btn(24, 132, 66, 24, "2주", self.range_days == 14, lambda: setattr(self, "range_days", 14))
        self.btn(96, 132, 66, 24, "30일", self.range_days == 30, lambda: setattr(self, "range_days", 30))

        n = self.range_days
        ds = [today - dt.timedelta(days=n - 1 - i) for i in range(n)]
        vals = [days.get(key(d), {}).get("sec", 0) / 3600 for d in ds]
        top = max(vals + [goal, 0.001]) * 1.15
        gx1, gx2, gy1, gy2 = 40, self.W - 24, 178, 330
        self.rr(24, 166, self.W - 24, 356, 14, fill="#221c24", outline="")
        slot = (gx2 - gx1) / n
        bw = slot * 0.62
        for i, (d, v) in enumerate(zip(ds, vals)):
            cx = gx1 + slot * (i + 0.5)
            hgt = (gy2 - gy1) * v / top
            is_today = key(d) == app.today
            hit = goal > 0 and v >= goal
            col = C_GOLD if is_today else ("#A8D8B9" if hit else "#8e7a9a")
            if v > 0:
                self.rr(cx - bw / 2, gy2 - max(hgt, 3), cx + bw / 2, gy2, min(5, bw / 2), fill=col, outline="")
            if n == 14 and v > 0:
                self.t(cx, gy2 - hgt - 9, f"{v:.1f}", 7, "#cbbcc2")
            if n == 14 or i % 5 == (n - 1) % 5:
                self.t(cx, gy2 + 11, f"{d.month}/{d.day}" if n == 30 else f"{d.day}", 7,
                       C_GOLD if is_today else C_MUTED)
                if n == 14:
                    self.t(cx, gy2 + 22, "월화수목금토일"[d.weekday()], 7, "#7d6f76")
        if goal > 0:
            gy = gy2 - (gy2 - gy1) * goal / top
            for xx in range(int(gx1), int(gx2), 8):
                cv.create_line(app.S(xx), app.S(gy), app.S(xx + 4), app.S(gy), fill="#d9b36a")
            self.t(gx2 - 2, gy - 8, f"목표 {fmt_goal(goal)}", 7, "#d9b36a", anchor="e")

        w_ = [v for v in vals if v > 0]
        if w_:
            avg = sum(w_) / len(w_)
            bi = max(range(n), key=lambda i: vals[i])
            bd = ds[bi]
            s = (f"작업한 날 {len(w_)}일 · 하루 평균 {fmt_hm(avg * 3600)} · "
                 f"가장 많이 한 날 {bd.month}/{bd.day} ({fmt_hm(vals[bi] * 3600)})")
            if goal > 0:
                s += f" · 목표 달성 {sum(1 for v in vals if v >= goal)}일"
        else:
            s = "아직 기록이 없어요. 고른 프로그램에서 글을 쓰면 쌓여요!"
        self.t(self.W / 2, 376, s, 8, C_SUB)


# ══ 설정 창 ═══════════════════════════════════════════
class SettingsWindow:
    BG = "#1d1820"
    FIELD = "#2a2229"

    def __init__(self, app):
        self.app = app
        S = app.S
        w = tk.Toplevel(app.root)
        self.win = w
        app.set_win = w
        app._last_sw = self
        w.title("타이머 설정")
        w.configure(bg=self.BG, padx=S(18), pady=S(14))
        w.resizable(False, False)
        w.attributes("-topmost", bool(app.set.get("topmost", True)))
        w.geometry(app.child_pos(470))
        self.f = f = (app.f_ko, 11) if app.round else (app.f_ko, 9)
        self.fb = fb = (app.f_ko, 13) if app.round else (app.f_ko, 10, "bold")
        self.fs = fs = (app.f_ko, 10) if app.round else (app.f_ko, 8)
        st = app.set
        self.custom = [dict(c) for c in st.get("custom", [])]

        left = tk.Frame(w, bg=self.BG)
        left.grid(row=0, column=0, sticky="nw")
        tk.Frame(w, bg="#3a3038", width=1).grid(row=0, column=1, sticky="ns", padx=S(16))
        right = tk.Frame(w, bg=self.BG)
        right.grid(row=0, column=2, sticky="nw")

        # ── 왼쪽: 감지할 프로그램
        tk.Label(left, text="감지할 프로그램", font=fb, bg=self.BG, fg=C_TEXT).pack(anchor="w")
        tk.Label(left, text="고른 프로그램 창에서 입력할 때만 시간이 흘러요", font=fs, bg=self.BG,
                 fg=C_MUTED).pack(anchor="w", pady=(0, S(4)))
        cb = dict(bg=self.BG, fg=C_TEXT, selectcolor=self.FIELD, activebackground=self.BG,
                  activeforeground=C_TEXT, font=f, anchor="w", highlightthickness=0, bd=0)
        self.v_pre = {}
        pre = st.get("presets", {})
        for code, name, *_ in PRESETS:
            v = tk.BooleanVar(value=bool(pre.get(code)))
            self.v_pre[code] = v
            tk.Checkbutton(left, text=name, variable=v, **cb).pack(anchor="w", pady=S(1))
        tk.Label(left, text="직접 넣은 것", font=f, bg=self.BG, fg=C_SUB).pack(anchor="w", pady=(S(10), S(2)))
        self.lb = tk.Listbox(left, height=4, width=30, font=fs, bg=self.FIELD, fg=C_TEXT, relief="flat",
                             highlightthickness=0, selectbackground="#4a3d44", activestyle="none")
        self.lb.pack(anchor="w", fill="x")
        bf = tk.Frame(left, bg=self.BG)
        bf.pack(anchor="w", pady=(S(6), 0), fill="x")
        self.button(bf, "열린 창에서 고르기", self.open_picker, gold=True).pack(side="left")
        self.button(bf, "빼기", self.remove_custom).pack(side="left", padx=(S(6), 0))
        tk.Label(left, text="웹 연재 편집기(조아라 등)도 여기서 넣을 수 있어요", font=fs, bg=self.BG,
                 fg=C_MUTED).pack(anchor="w", pady=(S(6), 0))
        self.refresh_custom()

        # ── 오른쪽: 나머지 설정
        self.v_goal = tk.DoubleVar(value=st["goal_hours"])
        self.v_idle = tk.DoubleVar(value=st["idle"])
        self.v_day = tk.IntVar(value=st["day_start"])
        self.v_alpha = tk.IntVar(value=st["alpha"])
        self.v_top = tk.BooleanVar(value=st["topmost"])
        self.v_sound = tk.BooleanVar(value=st["sound"])
        self.v_hourly = tk.BooleanVar(value=st.get("hourly", True))
        names = {"auto": "자동 (지금 시각에 맞춰)"}
        for p in PHASES:
            names[p[1]] = f"{p[2]}로 고정"
        self.phase_names = names
        self.v_phase = tk.StringVar(value=names.get(st["phase_mode"], names["auto"]))

        def row(r, title, sub, var=None, a=0, b=0, inc=1, unit=""):
            tk.Label(right, text=title, font=fb, bg=self.BG, fg=C_TEXT).grid(row=r, column=0, sticky="w",
                                                                           pady=(S(6) if r else 0, 0))
            if var is not None:
                fr = tk.Frame(right, bg=self.BG)
                fr.grid(row=r, column=1, sticky="e", pady=(S(6) if r else 0, 0))
                tk.Spinbox(fr, from_=a, to=b, increment=inc, textvariable=var, width=5, font=f, justify="center",
                           bg=self.FIELD, fg=C_TEXT, buttonbackground="#3a3038", insertbackground=C_TEXT,
                           relief="flat").pack(side="left")
                tk.Label(fr, text=unit, font=f, bg=self.BG, fg=C_SUB).pack(side="left", padx=(S(4), 0))
            if sub:
                tk.Label(right, text=sub, font=fs, bg=self.BG, fg=C_MUTED).grid(row=r + 1, column=0, columnspan=2,
                                                                                sticky="w")

        row(0, "하루 목표 시간", "0 으로 두면 목표 없이 써요", self.v_goal, 0, 16, 0.5, "시간")
        row(2, "멈춤 판정", "입력이 멈추고 이만큼 지나면 시간이 멈춰요", self.v_idle, 1, 30, 1, "초")
        row(4, "하루가 바뀌는 시각", "이 시각 전까지는 전날 기록으로 쳐요 (밤샘용)", self.v_day, 0, 12, 1, "시")
        row(6, "배경 시간대", None)
        om = tk.OptionMenu(right, self.v_phase, *names.values())
        om.config(font=f, bg=self.FIELD, fg=C_TEXT, activebackground="#3a3038", activeforeground=C_TEXT,
                  relief="flat", highlightthickness=0, width=16)
        om["menu"].config(font=f, bg=self.FIELD, fg=C_TEXT)
        om.grid(row=6, column=1, sticky="e", pady=(S(6), 0))
        row(7, "창 투명도", None)
        tk.Scale(right, from_=40, to=100, orient="horizontal", variable=self.v_alpha, showvalue=True,
                 length=S(140), bg=self.BG, fg=C_SUB, troughcolor=self.FIELD, highlightthickness=0, font=fs,
                 command=lambda v: app.root.attributes("-alpha", int(v) / 100)).grid(row=7, column=1, sticky="e")
        for i, (txt, var) in enumerate([("항상 다른 창 위에 띄우기", self.v_top),
                                        ("시간대가 바뀌거나 목표를 채우면 알림 소리", self.v_sound),
                                        ("정시마다 지금 시각 알려 주기", self.v_hourly)]):
            tk.Checkbutton(right, text=txt, variable=var, **cb).grid(row=8 + i, column=0, columnspan=2, sticky="w",
                                                                     pady=(S(8) if i == 0 else 0, 0))

        # ── 아래 버튼
        bottom = tk.Frame(w, bg=self.BG)
        bottom.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(S(16), 0))
        self.button(bottom, "기록 폴더 열기", self.open_data_dir).pack(side="left")
        tk.Label(bottom, text=f"v{APP_VER}", font=fs, bg=self.BG, fg="#5e5258").pack(side="left", padx=(S(8), 0))
        self.button(bottom, "저장", self.save, gold=True, width=8).pack(side="right")
        self.button(bottom, "닫기", self.cancel, width=8).pack(side="right", padx=(0, S(6)))
        w.protocol("WM_DELETE_WINDOW", self.cancel)

    def button(self, parent, text, cmd, gold=False, width=None):
        kw = dict(text=text, font=self.fb if gold and self.app.round else self.f, command=cmd, relief="flat",
                  bd=0, padx=self.app.S(10), pady=self.app.S(3), cursor="hand2")
        if width:
            kw["width"] = width
        if gold:
            kw.update(bg=C_GOLD, fg="#3a2a1c", activebackground="#ffe2a3", activeforeground="#3a2a1c")
        else:
            kw.update(bg="#3a3038", fg=C_TEXT, activebackground="#4a3d44", activeforeground=C_TEXT)
        return tk.Button(parent, **kw)

    def refresh_custom(self):
        self.lb.delete(0, "end")
        for c in self.custom:
            self.lb.insert("end", custom_label(c))
        if not self.custom:
            self.lb.insert("end", "(아직 없어요)")

    def remove_custom(self):
        sel = self.lb.curselection()
        if sel and self.custom and sel[0] < len(self.custom):
            del self.custom[sel[0]]
            self.refresh_custom()

    def add_custom(self, kind, value):
        value = value.strip()
        if not value:
            return False
        item = {"kind": kind, "value": value}
        if item not in self.custom:
            self.custom.append(item)
            self.refresh_custom()
        return True

    def open_picker(self):
        WindowPicker(self)

    def open_data_dir(self):
        try:
            if IS_WIN:
                os.startfile(str(DATA_DIR))
            else:
                messagebox.showinfo(APP_NAME, str(DATA_DIR), parent=self.win)
        except Exception:
            log_error("open_data_dir")

    def save(self):
        app = self.app
        st = app.set
        try:
            st["goal_hours"] = max(0.0, min(16.0, float(self.v_goal.get())))
            st["idle"] = max(1.0, min(30.0, float(self.v_idle.get())))
            st["day_start"] = max(0, min(12, int(self.v_day.get())))
        except (ValueError, tk.TclError):
            messagebox.showwarning("타이머 설정", "숫자를 확인해 주세요", parent=self.win)
            return
        st["alpha"] = int(self.v_alpha.get())
        st["topmost"] = bool(self.v_top.get())
        st["sound"] = bool(self.v_sound.get())
        st["hourly"] = bool(self.v_hourly.get())
        st["presets"] = {k: bool(v.get()) for k, v in self.v_pre.items()}
        st["custom"] = self.custom
        inv = {v: k for k, v in self.phase_names.items()}
        st["phase_mode"] = inv.get(self.v_phase.get(), "auto")
        app.today = app.day_key()
        app.ensure_day(app.today)
        d = app.td
        goal = st["goal_hours"] * 3600
        if goal > 0 and d["sec"] < goal:
            d["goal_done"] = False
        app.hide_toast()
        app.remember_pos()
        app.apply_window_settings()
        app.build_layout()
        app.save_all()
        self.win.destroy()

    def cancel(self):
        self.app.root.attributes("-alpha", max(0.3, self.app.set.get("alpha", 100) / 100))
        self.win.destroy()


# ══ 열린 창에서 고르기 ═══════════════════════════════
class WindowPicker:
    BG = "#1d1820"

    def __init__(self, sw):
        self.sw = sw
        app = sw.app
        S = app.S
        w = tk.Toplevel(sw.win)
        self.win = w
        w.title("열린 창에서 고르기")
        w.configure(bg=self.BG, padx=S(18), pady=S(14))
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.transient(sw.win)
        f, fb, fs = sw.f, sw.fb, sw.fs
        tk.Label(w, text="글 쓰는 창을 골라 주세요", font=fb, bg=self.BG, fg=C_TEXT).pack(anchor="w")
        tk.Label(w, text="쓰는 프로그램을 먼저 켜 두고 '새로 고침'을 누르면 목록에 나와요", font=fs, bg=self.BG,
                 fg=C_MUTED).pack(anchor="w", pady=(0, S(6)))
        self.lb = tk.Listbox(w, height=9, width=58, font=fs, bg="#2a2229", fg=C_TEXT, relief="flat",
                             highlightthickness=0, selectbackground="#4a3d44", activestyle="none",
                             exportselection=False)
        self.lb.pack(fill="x")
        self.lb.bind("<<ListboxSelect>>", self.on_select)

        self.v_kind = tk.StringVar(value="exe")
        self.v_text = tk.StringVar()
        rb = dict(bg=self.BG, fg=C_TEXT, selectcolor="#2a2229", activebackground=self.BG,
                  activeforeground=C_TEXT, font=f, anchor="w", highlightthickness=0, bd=0)
        box = tk.Frame(w, bg=self.BG)
        box.pack(fill="x", pady=(S(10), 0))
        self.rb_exe = tk.Radiobutton(box, text="이 프로그램이면 다 세기", variable=self.v_kind, value="exe", **rb)
        self.rb_exe.pack(anchor="w")
        tk.Radiobutton(box, text="창 제목에 아래 글자가 들어 있을 때만 세기", variable=self.v_kind, value="title",
                       **rb).pack(anchor="w")
        tk.Entry(box, textvariable=self.v_text, font=f, bg="#2a2229", fg=C_TEXT, relief="flat",
                 insertbackground=C_TEXT).pack(fill="x", pady=(S(4), 0), ipady=S(3))
        tk.Label(box, text="웹 브라우저(크롬·엣지·웨일)는 아래쪽을 고르고 사이트 이름만 남겨 주세요. 예: 조아라",
                 font=fs, bg=self.BG, fg=C_MUTED, wraplength=S(460), justify="left").pack(anchor="w", pady=(S(4), 0))
        self.msg = tk.Label(w, text="", font=fs, bg=self.BG, fg=C_TYPING)
        self.msg.pack(anchor="w", pady=(S(6), 0))
        bf = tk.Frame(w, bg=self.BG)
        bf.pack(fill="x", pady=(S(8), 0))
        sw.button(bf, "새로 고침", self.load).pack(side="left")
        sw.button(bf, "추가", self.add, gold=True, width=8).pack(side="right")
        sw.button(bf, "닫기", w.destroy, width=8).pack(side="right", padx=(0, S(6)))
        self.items = []
        self.load()
        if DEMO and self.items:  # 미리보기: 조아라 창을 골라 둔 모습
            self.lb.selection_set(1)
            self.on_select()
            self.v_text.set("조아라")
        w.update_idletasks()
        w.geometry(f"+{sw.win.winfo_rootx() + S(30)}+{sw.win.winfo_rooty() + S(30)}")

    def load(self):
        try:
            self.items = list_windows()
        except Exception:
            log_error("list_windows")
            self.items = []
        self.lb.delete(0, "end")
        for t, exe in self.items:
            self.lb.insert("end", f"{t}   ·  {exe}")
        if not self.items:
            self.lb.insert("end", "(열린 창이 없어요)")

    def on_select(self, e=None):
        sel = self.lb.curselection()
        if not sel or sel[0] >= len(self.items):
            return
        title, exe = self.items[sel[0]]
        self.rb_exe.config(text=f"이 프로그램이면 다 세기  ({exe or '알 수 없음'})")
        self.v_text.set(title)
        self.v_kind.set("title" if (exe.lower() in BROWSERS or not exe) else "exe")

    def add(self):
        sel = self.lb.curselection()
        kind = self.v_kind.get()
        if kind == "exe":
            if not sel or sel[0] >= len(self.items) or not self.items[sel[0]][1]:
                self.msg.config(text="목록에서 창을 먼저 골라 주세요", fg=C_PAUSE)
                return
            value = self.items[sel[0]][1]
        else:
            value = self.v_text.get()
            if not value.strip():
                self.msg.config(text="창 제목에 들어갈 글자를 넣어 주세요", fg=C_PAUSE)
                return
        self.sw.add_custom(kind, value)
        self.msg.config(text=f"넣었어요: {custom_label({'kind': kind, 'value': value.strip()})}", fg=C_TYPING)


# ══ 자동 점검 (만들 때 깃허브에서 돌림) ═══════════════
def run_selftest(root, app):
    from tkinter import font as tkfont
    report = {"version": APP_VER, "frozen": bool(getattr(sys, "frozen", False)), "data_dir": str(DATA_DIR)}
    errors = []
    root.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))

    def step1():
        try:
            app.open_settings()
            app.open_stats()
            root.update()
            WindowPicker(app._last_sw)
            app.toggle_mini()
            app.toggle_mini()
        except Exception:
            errors.append(traceback.format_exc())
        root.after(1500, step2)

    def step2():
        try:
            report["font"] = app.f_ko
            report["ramil_font_found"] = any(f.lower() == "ramilround" for f in tkfont.families(root))
            report["backgrounds"] = app.bg_count
            report["last_input_tick"] = last_input_tick()
            report["cursor"] = cursor_pos()
            pid, title, exe = foreground()
            report["foreground"] = {"pid": pid, "title": title, "exe": exe}
            report["windows"] = len(list_windows())
            report["is_target_hwp"] = app.is_target(1, "1화.hwp - 한글", "Hwp.exe")
            report["is_target_chrome"] = app.is_target(1, "유튜브 - Chrome", "chrome.exe")
            report["errors"] = errors + app.errors
            if IS_WIN:  # 윈도우에서는 이것들이 꼭 돼야 함
                if not report["ramil_font_found"]:
                    report["errors"].append("둥근 글꼴을 못 불러옴")
                if report["backgrounds"] < 6:
                    report["errors"].append("배경 그림이 모자람")
                if report["last_input_tick"] is None:
                    report["errors"].append("마지막 입력 시각을 못 읽음")
        except Exception:
            report["errors"] = errors + [traceback.format_exc()]
        save_json(DATA_DIR / "selftest.json", report)
        root.destroy()

    root.after(1500, step1)


if __name__ == "__main__":
    _mutex, _already = single_instance()
    if _already and not SELFTEST:
        _r = tk.Tk(); _r.withdraw()
        messagebox.showinfo(APP_NAME, "타이머가 이미 켜져 있어요!\n작업 표시줄을 확인해 주세요.")
        sys.exit()
    root = tk.Tk()
    try:
        app = TimerApp(root)
    except Exception:
        log_error("start")
        raise
    if SELFTEST:
        run_selftest(root, app)
    o = os.environ.get("TIMER_OPEN")
    if o == "stats":
        root.after(300, app.open_stats)
    elif o == "settings":
        root.after(300, app.open_settings)
    elif o == "picker":
        root.after(300, lambda: (app.open_settings(), root.after(300, lambda: WindowPicker(app._last_sw))))
    root.mainloop()
    if SELFTEST:
        rep = load_json(DATA_DIR / "selftest.json", {})
        sys.exit(1 if rep.get("errors") or not rep else 0)
