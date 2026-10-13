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
import time, json, os, sys, random, traceback, re, collections
import datetime as dt
from pathlib import Path

APP_NAME = "마감의 숲 집필 타이머"
APP_VER = "1.1.6"
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
    for _ff in (FONT_FILE,):
        if _ff.exists():
            try:  # 컴퓨터에 설치하지 않고 이 프로그램 안에서만 쓰기 (FR_PRIVATE)
                gdi32.AddFontResourceExW(str(_ff), 0x10, None)
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
    "char_basis": "sp",   # 글자 수 기준: sp 공백 포함 / ns 공백 제외
    "goal_chars": 0,      # 하루 목표 글자 수 (0 이면 없음)
    "tidy": {"blank": "keep", "quotes": True, "ellipsis": True, "ellipsis_to": "…", "trim": True},
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


# ── 원고 글 다루기 ────────────────────────────────────
def norm_nl(t):
    return t.replace("\r\n", "\n").replace("\r", "\n")


def count_chars(text):
    """(공백 포함, 공백 제외) 글자 수. 줄바꿈은 어느 쪽에도 안 셈 (한글 문서 정보와 같은 방식)"""
    t = norm_nl(text)
    sp = len(t) - t.count("\n")
    ns = len(re.sub(r"\s", "", t))
    return sp, ns


def first_line(text):
    for line in norm_nl(text).split("\n"):
        if line.strip():
            return line.strip()
    return ""


def piece_key(text):
    return re.sub(r"\s+", "", first_line(text))[:40]


_OPEN_BEFORE = set(" \t\u3000([{<“‘「『—–-·…")


def curly_quotes(line):
    out = []
    for i, ch in enumerate(line):
        if ch in "\"'":
            prev = line[i - 1] if i else " "
            opening = i == 0 or prev in _OPEN_BEFORE
            if ch == '"':
                out.append("“" if opening else "”")
            else:
                out.append("‘" if opening else "’")
        else:
            out.append(ch)
    return "".join(out)


_ELLIPSIS = re.compile(r"[.…⋯]*[…⋯][.…⋯]*|\.{2,}")


def tidy_text(text, opt):
    lines = norm_nl(text).split("\n")
    if opt.get("trim"):
        lines = [re.sub(r"(?<=\S)[ \t]{2,}", " ", l).rstrip() for l in lines]
    if opt.get("quotes"):
        lines = [curly_quotes(l) for l in lines]
    if opt.get("ellipsis"):
        to = opt.get("ellipsis_to", "…")
        lines = [_ELLIPSIS.sub(to, l) for l in lines]
    blank = opt.get("blank", "keep")
    if blank == "remove":
        lines = [l for l in lines if l.strip()]
    elif blank == "add":
        return "\n\n".join(l for l in lines if l.strip())
    return "\n".join(lines)


JOSA = sorted(["은", "는", "이", "가", "을", "를", "에", "의", "로", "와", "과", "도", "만", "랑", "께",
               "으로", "에서", "에게", "한테", "께서", "까지", "부터", "처럼", "보다", "마저", "조차", "이나",
               "이랑", "하고", "에는", "에도", "에서는", "에서도", "에게서", "으로는", "으로도", "으로써",
               "으로서", "만큼", "밖에", "이라도", "라도", "이며", "이고"], key=len, reverse=True)


def find_repeats(text):
    """자주 나온 단어(조사만 다른 건 묶음)와 두 단어 표현"""
    toks = re.findall(r"[가-힣]+|[A-Za-z]+", text)
    raw = collections.Counter(t for t in toks if len(t) >= 2)
    cands = {}
    support = collections.defaultdict(set)
    for t in raw:
        cs = [t[:-len(j)] for j in JOSA if t.endswith(j) and len(t) - len(j) >= 2]
        cands[t] = cs
        for c in cs:
            support[c].add(t)
    stem_of = {}
    for t, cs in cands.items():
        stem_of[t] = t
        for c in cs:
            if c in raw or len(support[c]) >= 2:
                stem_of[t] = c
                break
    words = collections.Counter()
    forms = collections.defaultdict(collections.Counter)
    for t, n in raw.items():
        words[stem_of[t]] += n
        forms[stem_of[t]][t] += n
    w_list = [(w, n, forms[w].most_common(3)) for w, n in words.most_common(80) if n >= 3]
    pairs = collections.Counter()
    for chunk in re.split(r"[.!?…⋯\n“”\"‘’',;:()\[\]~]+", text):  # 문장·따옴표를 넘어가는 짝은 안 셈
        ct = re.findall(r"[가-힣]+|[A-Za-z]+", chunk)
        pairs.update(f"{a} {b}" for a, b in zip(ct, ct[1:]) if len(a) >= 2 and len(b) >= 2)
    p_list = [(p, n) for p, n in pairs.most_common(60) if n >= 2]
    return w_list, p_list


def fmt_chars(n):
    return f"{int(n):,}자"


def fmt_man(n):
    n = int(n)
    if n < 10000:
        return f"{n:,}자"
    v = f"{n / 10000:.1f}".rstrip("0").rstrip(".")
    return f"{v}만 자"


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
        # 원고 창처럼 글을 많이 읽는 곳은 깔끔한 글꼴
        self.f_clean = pick_font(root, ["Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR",
                                        "NanumGothic", "minikr", "TkDefaultFont"])

        first_run = not SET_FILE.exists()
        self.set = json.loads(json.dumps(DEFAULTS))
        self.set.update(load_json(SET_FILE, {}))
        for k, v in DEFAULTS["presets"].items():
            self.set.setdefault("presets", {}).setdefault(k, v)
        for k, v in DEFAULTS["tidy"].items():
            self.set.setdefault("tidy", {}).setdefault(k, v)
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
        self.tidy_win = None

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

    def basis_name(self):
        return "공백 포함" if self.set.get("char_basis", "sp") == "sp" else "공백 제외"

    def day_chars(self, d, basis=None):
        b = basis or self.set.get("char_basis", "sp")
        return sum(int(p.get(b, 0)) for p in d.get("pieces", []))

    def add_piece(self, text):
        """오늘 작업한 글자 수에 더하기. 같은 화(첫 줄이 같은 글)는 새 글자 수로 바꾸고,
        전날 쓰던 화면 늘어난 만큼만 더함"""
        sp, ns = count_chars(text)
        key = piece_key(text)
        if not key or sp == 0:
            return None
        b = self.set.get("char_basis", "sp")
        cutoff = (dt.datetime.strptime(self.today, "%Y-%m-%d") - dt.timedelta(days=60)).strftime("%Y-%m-%d")
        prev = None
        for k in sorted(self.data["days"]):
            if k >= self.today or k < cutoff:
                continue
            for p in self.data["days"][k].get("pieces", []):
                if p.get("key") == key:
                    prev = p
        psp = int(prev.get("total_sp", 0)) if prev else 0
        pns = int(prev.get("total_ns", 0)) if prev else 0
        rec = {"key": key, "head": first_line(text)[:24], "total_sp": sp, "total_ns": ns,
               "sp": max(0, sp - psp), "ns": max(0, ns - pns), "t": int(time.time())}
        pieces = self.td.setdefault("pieces", [])
        old = None
        for i, p in enumerate(pieces):
            if p.get("key") == key:
                old = p
                pieces[i] = rec
                break
        else:
            pieces.append(rec)
        kind = "update" if old else ("cont" if prev else "new")
        self.save_all()
        self.refresh()
        if old:
            before = int(old.get(b, 0))
        elif prev:
            before = int(prev.get("total_" + b, 0))
        else:
            before = 0
        return kind, rec, before

    def remove_piece(self, idx):
        pieces = self.td.get("pieces", [])
        if 0 <= idx < len(pieces):
            del pieces[idx]
            d = self.td
            g = int(self.set.get("goal_chars", 0) or 0)
            if g and self.day_chars(d) < g:
                d["chars_goal_done"] = False
            self.save_all()
            self.refresh()

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

    def pill(self, cx, cy, w, h, label, cmd, size=9, extra=()):
        tag = f"pill{id(cmd)}{cx}{cy}"
        bgid = self.round_rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, h / 2,
                               fill=self.P["pill"], outline=self.P["pill_line"], width=max(1, self.S(1)),
                               tags=(tag,) + tuple(extra))
        tid = self.canvas.create_text(self.S(cx), self.S(cy), text=label, font=(self.f_ko, size),
                                      fill=self.P["text"], tags=(tag,) + tuple(extra))
        self.canvas.tag_bind(tag, "<Enter>", lambda e: (self.canvas.itemconfigure(bgid, fill=self.P["pill_hover"]),
                                                        self.canvas.config(cursor="hand2")))
        self.canvas.tag_bind(tag, "<Leave>", lambda e: (self.canvas.itemconfigure(bgid, fill=self.P["pill"]),
                                                        self.canvas.config(cursor="")))
        self.canvas.tag_bind(tag, "<Button-1>", lambda e: cmd())
        self.canvas.tag_bind(tag, "<Double-Button-1>", lambda e: "break")
        return tid

    def build_layout(self):
        c = self.canvas
        self.hide_reset_menu()
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
            self.pill(w - 209, 21, 52, 28, "원고", self.open_tidy, 11)
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
        chars = self.day_chars(d)
        gch = int(self.set.get("goal_chars", 0) or 0)
        if mini:
            if self.toast_text and time.time() < self.toast_until:
                self.set_text(self.t_status, self.toast_text, self.P["goal_done"])
            else:
                pct = f" · {int(ratio * 100)}%" if goal > 0 else ""
                cs = f" · {fmt_man(chars)}" if chars else ""
                self.set_text(self.t_status, f"{short}{pct}{cs}", col if self.is_typing else self.P["sub"])
        else:
            self.set_text(self.t_status, st, col)
            if goal > 0:
                g = f"목표 {fmt_goal(self.set['goal_hours'])} · {int(ratio * 100)}%"
                if done:
                    g = f"목표 {fmt_goal(self.set['goal_hours'])} 달성 ★"
            else:
                g = ""
            if gch:
                c = f"{chars:,} / {gch:,}자" + (" ★" if chars >= gch else "")
            else:
                c = fmt_chars(chars) if chars else ""
            line = "   ·   ".join(x for x in (g, c) if x) or "오늘 목표 없음"
            self.set_text(self.t_goal, line, self.P["goal_done"] if done else self.P["sub"])
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

        gch = int(self.set.get("goal_chars", 0) or 0)
        if gch and self.day_chars(d) >= gch and not d.get("chars_goal_done"):
            d["chars_goal_done"] = True
            self.show_toast(f"오늘 목표 {gch:,}자 달성! 대단해요 ★", 12)
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
                ch = self.day_chars(self.td)
                more = f" · {fmt_man(ch)}" if ch else " 썼어요"
                self.show_toast(f"{p[3]} {p[2]} {h12}시예요 · 오늘 {fmt_hm(self.td['sec'])}{more}", 8)
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
        """초기화 버튼 바로 위에 [시간] [원고] [모두] 작은 팝업"""
        c = self.canvas
        if c.find_withtag("resetmenu"):
            self.hide_reset_menu()
            return
        if self.set.get("mini"):
            return
        w, _ = self.size()
        cx, cy = w / 2 + 58, 183  # 초기화 버튼(227) 위
        pw, ph = 236, 46
        self.round_rect(cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2, 16, fill=self.P["pill"],
                        outline=C_GOLD, width=max(1, self.S(1)), tags=("resetmenu",))
        tri = [self.S(v) for v in (cx - 8, cy + ph / 2 - 1, cx + 8, cy + ph / 2 - 1, cx, cy + ph / 2 + 8)]
        c.create_polygon(tri, fill=self.P["pill"], outline="", tags=("resetmenu",))
        for i, (label, what) in enumerate((("시간", "time"), ("원고", "chars"), ("모두", "all"))):
            self.pill(cx - 74 + i * 74, cy, 64, 30, label, lambda x=what: self.pick_reset(x), 12,
                      extra=("resetmenu",))
        self._reset_after = self.root.after(6000, self.hide_reset_menu)

    def hide_reset_menu(self):
        self.canvas.delete("resetmenu")
        self.canvas.config(cursor="")
        if getattr(self, "_reset_after", None):
            try:
                self.root.after_cancel(self._reset_after)
            except Exception:
                pass
            self._reset_after = None

    def pick_reset(self, what):
        self.hide_reset_menu()
        self.do_reset(what)
        self.show_toast({"time": "오늘 시간을 0으로 되돌렸어요", "chars": "오늘 작업한 글자 수를 비웠어요",
                         "all": "오늘 기록을 모두 비웠어요"}[what], 5)

    def do_reset(self, what):
        """what: time / chars / all"""
        d = self.td
        if what in ("time", "all"):
            d["sec"] = 0.0
            d["goal_done"] = False
            self.last_key_time = 0.0
            self.is_typing = False
        if what in ("chars", "all"):
            d["pieces"] = []
            d["chars_goal_done"] = False
            # 원고 창에 불러온 글도 비우기 (다시 열 때 같은 글을 또 불러오지 않게 기억)
            try:
                self._cleared_clip = self.root.clipboard_get()
            except tk.TclError:
                self._cleared_clip = ""
        self.save_all()
        self.refresh()
        if self.tidy_win and self.tidy_win.winfo_exists() and getattr(self, "_last_tidy", None):
            if what in ("chars", "all"):
                self._last_tidy.clear_loaded()
            self._last_tidy.refresh_pieces()

    def on_close(self):
        self.remember_pos()
        self.save_all()
        self.root.destroy()

    def open_stats(self):
        if self.stats_win and self.stats_win.winfo_exists():
            self.stats_win.lift()
            return
        StatsWindow(self)

    def open_tidy(self):
        if self.tidy_win and self.tidy_win.winfo_exists():
            self.tidy_win.lift()
            return
        TidyWindow(self)

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
            c = int(s / 3600 * random.uniform(3500, 6000))
            self.data["days"][k] = {"sec": s, "goal_done": s > 3 * 3600,
                                    "pieces": [{"key": f"d{i}", "head": "", "sp": c, "ns": int(c * .78),
                                                "total_sp": c, "total_ns": int(c * .78)}]}
        self.data["days"][self.today] = {"sec": 2 * 3600 + 13 * 60 + 41, "goal_done": False, "pieces": [
            {"key": "11화.", "head": "11화. 비 오는 밤의 손님", "sp": 5234, "ns": 4102, "total_sp": 5234, "total_ns": 4102},
            {"key": "12화.", "head": "12화. 젖은 우산", "sp": 7106, "ns": 5530, "total_sp": 7106, "total_ns": 5530}]}
        self.set["goal_chars"] = 20000
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
        self.W, self.H = 560, 418
        self.win.geometry(f"{S(self.W)}x{S(self.H)}" + app.child_pos(self.H))
        self.range_days = 14
        self.metric = "chars" if DEMO and os.environ.get("TIMER_METRIC") == "chars" else "time"
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
        chars = lambda ks: sum(app.day_chars(days.get(k, {})) for k in ks)
        worked = lambda ks: sum(1 for k in ks if days.get(k, {}).get("sec", 0) >= 60 or app.day_chars(days.get(k, {})))

        week = [key(today - dt.timedelta(days=i)) for i in range(today.weekday() + 1)]
        month = [key(today.replace(day=i)) for i in range(1, today.day + 1)]
        goal = float(app.set.get("goal_hours", 0))
        gch = int(app.set.get("goal_chars", 0) or 0)
        tsec = secs([app.today])
        sub_today = f"목표의 {int(tsec / (goal * 3600) * 100)}%" if goal > 0 else "목표 없음"
        cards = [("오늘", [app.today], sub_today), ("이번 주", week, f"작업한 날 {worked(week)}일"),
                 (f"{today.month}월", month, f"작업한 날 {worked(month)}일")]
        self.t(24, 26, "집필 기록", 13, C_TEXT, anchor="w")
        self.t(self.W - 24, 28, f"글자 수는 {app.basis_name()} · 하루는 {app.set['day_start']}시에 바뀌어요", 8,
               "#8f7f86", anchor="e")
        cw = (self.W - 48 - 20) / 3
        for i, (name, ks, sub) in enumerate(cards):
            x = 24 + i * (cw + 10)
            self.rr(x, 48, x + cw, 136, 14, fill=self.CARD, outline="")
            self.t(x + 14, 64, name, 9, C_SUB, anchor="w")
            self.t(x + 14, 87, fmt_hm(secs(ks)), 14, C_GOLD if i == 0 else C_TEXT, anchor="w")
            self.t(x + 14, 107, fmt_man(chars(ks)), 10, "#e8d6c4", anchor="w")
            self.t(x + 14, 124, sub, 8, "#b9a8ad", anchor="w")

        y0 = 146
        self.btn(24, y0, 66, 24, "2주", self.range_days == 14, lambda: setattr(self, "range_days", 14))
        self.btn(96, y0, 66, 24, "30일", self.range_days == 30, lambda: setattr(self, "range_days", 30))
        self.btn(self.W - 24 - 140, y0, 66, 24, "시간", self.metric == "time", lambda: setattr(self, "metric", "time"))
        self.btn(self.W - 24 - 66, y0, 66, 24, "글자 수", self.metric == "chars",
                 lambda: setattr(self, "metric", "chars"))

        n = self.range_days
        ds = [today - dt.timedelta(days=n - 1 - i) for i in range(n)]
        if self.metric == "time":
            vals = [days.get(key(d), {}).get("sec", 0) / 3600 for d in ds]
            g = goal
            lab = lambda v: f"{v:.1f}"
            gname = f"목표 {fmt_goal(goal)}"
        else:
            vals = [app.day_chars(days.get(key(d), {})) for d in ds]
            g = gch
            lab = lambda v: (f"{v / 10000:.1f}만" if v >= 10000 else (f"{v / 1000:.1f}천" if v >= 1000 else str(int(v))))
            gname = f"목표 {gch:,}자"
        top = max(vals + [g, 0.001]) * 1.15
        gx1, gx2, gy1, gy2 = 40, self.W - 24, y0 + 46, y0 + 198
        self.rr(24, y0 + 34, self.W - 24, y0 + 224, 14, fill="#221c24", outline="")
        slot = (gx2 - gx1) / n
        bw = slot * 0.62
        for i, (d, v) in enumerate(zip(ds, vals)):
            cx = gx1 + slot * (i + 0.5)
            hgt = (gy2 - gy1) * v / top
            is_today = key(d) == app.today
            hit = g > 0 and v >= g
            col = C_GOLD if is_today else ("#A8D8B9" if hit else "#8e7a9a")
            if v > 0:
                self.rr(cx - bw / 2, gy2 - max(hgt, 3), cx + bw / 2, gy2, min(5, bw / 2), fill=col, outline="")
            if n == 14 and v > 0:
                self.t(cx, gy2 - hgt - 9, lab(v), 7, "#cbbcc2")
            if n == 14 or i % 5 == (n - 1) % 5:
                self.t(cx, gy2 + 11, f"{d.month}/{d.day}" if n == 30 else f"{d.day}", 7,
                       C_GOLD if is_today else C_MUTED)
                if n == 14:
                    self.t(cx, gy2 + 22, "월화수목금토일"[d.weekday()], 7, "#7d6f76")
        if g > 0:
            gy = gy2 - (gy2 - gy1) * g / top
            for xx in range(int(gx1), int(gx2), 8):
                cv.create_line(app.S(xx), app.S(gy), app.S(xx + 4), app.S(gy), fill="#d9b36a")
            self.t(gx2 - 2, gy - 8, gname, 7, "#d9b36a", anchor="e")

        w_ = [v for v in vals if v > 0]
        if w_:
            avg = sum(w_) / len(w_)
            bi = max(range(n), key=lambda i: vals[i])
            bd = ds[bi]
            if self.metric == "time":
                s = (f"작업한 날 {len(w_)}일 · 하루 평균 {fmt_hm(avg * 3600)} · "
                     f"가장 많이 한 날 {bd.month}/{bd.day} ({fmt_hm(vals[bi] * 3600)})")
            else:
                s = (f"글 쓴 날 {len(w_)}일 · 하루 평균 {fmt_man(avg)} · "
                     f"가장 많이 쓴 날 {bd.month}/{bd.day} ({fmt_man(vals[bi])})")
            if g > 0:
                s += f" · 목표 달성 {sum(1 for v in vals if v >= g)}일"
        elif self.metric == "chars":
            s = "원고 창에서 '오늘 작업한 글자 수'의 '더하기'를 누르면 쌓여요!"
        else:
            s = "아직 기록이 없어요. 고른 프로그램에서 글을 쓰면 쌓여요!"
        self.t(self.W / 2, y0 + 248, s, 8, C_SUB)


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
        # 라밀: 주아로 통일하고 한 단계씩 크게
        self.f = f = (app.f_ko, 13) if app.round else (app.f_ko, 11)
        self.fb = fb = (app.f_ko, 15) if app.round else (app.f_ko, 12, "bold")
        self.fs = fs = (app.f_ko, 12) if app.round else (app.f_ko, 10)
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

        self.v_gch = tk.IntVar(value=int(st.get("goal_chars", 0) or 0))
        self.basis_names = {"sp": "공백 포함", "ns": "공백 제외"}
        self.v_basis = tk.StringVar(value=self.basis_names.get(st.get("char_basis", "sp"), "공백 포함"))

        def row(r, title, sub, var=None, a=0, b=0, inc=1, unit="", width=5):
            tk.Label(right, text=title, font=fb, bg=self.BG, fg=C_TEXT).grid(row=r, column=0, sticky="w",
                                                                           pady=(S(6) if r else 0, 0))
            if var is not None:
                fr = tk.Frame(right, bg=self.BG)
                fr.grid(row=r, column=1, sticky="e", pady=(S(6) if r else 0, 0))
                tk.Spinbox(fr, from_=a, to=b, increment=inc, textvariable=var, width=width, font=f, justify="center",
                           bg=self.FIELD, fg=C_TEXT, buttonbackground="#3a3038", insertbackground=C_TEXT,
                           relief="flat").pack(side="left")
                tk.Label(fr, text=unit, font=f, bg=self.BG, fg=C_SUB).pack(side="left", padx=(S(4), 0))
            if sub:
                tk.Label(right, text=sub, font=fs, bg=self.BG, fg=C_MUTED).grid(row=r + 1, column=0, columnspan=2,
                                                                                sticky="w")

        row(0, "하루 목표 시간", None, self.v_goal, 0, 16, 0.5, "시간")
        row(1, "하루 목표 글자 수", "0 으로 두면 목표 없이 써요", self.v_gch, 0, 200000, 1000, "자", width=7)
        row(3, "글자 수 세는 기준", None)
        omb = tk.OptionMenu(right, self.v_basis, *self.basis_names.values())
        omb.config(font=f, bg=self.FIELD, fg=C_TEXT, activebackground="#3a3038", activeforeground=C_TEXT,
                   relief="flat", highlightthickness=0, width=10)
        omb["menu"].config(font=f, bg=self.FIELD, fg=C_TEXT)
        omb.grid(row=3, column=1, sticky="e", pady=(S(6), 0))
        row(4, "멈춤 판정", "입력이 멈추고 이만큼 지나면 시간이 멈춰요", self.v_idle, 1, 30, 1, "초")
        row(6, "하루가 바뀌는 시각", "이 시각 전까지는 전날 기록으로 쳐요 (밤샘용)", self.v_day, 0, 12, 1, "시")
        row(8, "배경 시간대", None)
        om = tk.OptionMenu(right, self.v_phase, *names.values())
        om.config(font=f, bg=self.FIELD, fg=C_TEXT, activebackground="#3a3038", activeforeground=C_TEXT,
                  relief="flat", highlightthickness=0, width=16)
        om["menu"].config(font=f, bg=self.FIELD, fg=C_TEXT)
        om.grid(row=8, column=1, sticky="e", pady=(S(6), 0))
        row(9, "창 투명도", None)
        tk.Scale(right, from_=40, to=100, orient="horizontal", variable=self.v_alpha, showvalue=True,
                 length=S(140), bg=self.BG, fg=C_SUB, troughcolor=self.FIELD, highlightthickness=0, font=fs,
                 command=lambda v: app.root.attributes("-alpha", int(v) / 100)).grid(row=9, column=1, sticky="e")
        for i, (txt, var) in enumerate([("항상 다른 창 위에 띄우기", self.v_top),
                                        ("시간대가 바뀌거나 목표를 채우면 알림 소리", self.v_sound),
                                        ("정시마다 지금 시각 알려 주기", self.v_hourly)]):
            tk.Checkbutton(right, text=txt, variable=var, **cb).grid(row=10 + i, column=0, columnspan=2, sticky="w",
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
            st["goal_chars"] = max(0, min(200000, int(float(self.v_gch.get()))))
        except (ValueError, tk.TclError):
            messagebox.showwarning("타이머 설정", "숫자를 확인해 주세요", parent=self.win)
            return
        st["alpha"] = int(self.v_alpha.get())
        st["topmost"] = bool(self.v_top.get())
        st["sound"] = bool(self.v_sound.get())
        st["hourly"] = bool(self.v_hourly.get())
        st["char_basis"] = {v: k for k, v in self.basis_names.items()}.get(self.v_basis.get(), "sp")
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
        if st["goal_chars"] and app.day_chars(d) < st["goal_chars"]:
            d["chars_goal_done"] = False
        app.hide_toast()
        app.remember_pos()
        app.apply_window_settings()
        app.build_layout()
        app.save_all()
        self.win.destroy()

    def cancel(self):
        self.app.root.attributes("-alpha", max(0.3, self.app.set.get("alpha", 100) / 100))
        self.win.destroy()


# ══ 원고 정리 창 ═════════════════════════════════════
class TidyWindow:
    BG = "#1d1820"
    FIELD = "#2a2229"

    def __init__(self, app):
        self.app = app
        S = app.S
        w = tk.Toplevel(app.root)
        self.win = w
        app.tidy_win = w
        app._last_tidy = self
        w.title("원고 정리")
        w.configure(bg=self.BG, padx=S(28), pady=S(22))
        w.resizable(False, False)
        w.attributes("-topmost", bool(app.set.get("topmost", True)))
        w.geometry(app.child_pos(720))
        # 원고 창: 주아로 통일, 한 단계씩 크게 (라밀: 맑은 고딕·고운돋움보다 주아가 나음)
        fk = app.f_ko
        self.f = f = (fk, 14) if app.round else (fk, 12)
        self.fb = fb = (fk, 18) if app.round else (fk, 14, "bold")
        self.fs = fs = (fk, 13) if app.round else (fk, 11)
        self.fl = fl = (fk, 14) if app.round else (fk, 12)  # 목록 글씨
        HINT = "#c4b5bc"
        self.orig = ""
        self.cur = ""
        to = app.set.get("tidy", {})
        lab = dict(bg=self.BG)
        cb = dict(bg=self.BG, fg=C_TEXT, selectcolor=self.FIELD, activebackground=self.BG,
                  activeforeground=C_TEXT, font=f, anchor="w", highlightthickness=0, bd=0)

        top = tk.Frame(w, **lab)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(top, text="원고 정리", font=fb, fg=C_TEXT, **lab).pack(side="left")
        self.button(top, "복사한 글 불러오기", self.load, gold=True).pack(side="right")
        tk.Label(w, text="한글에서 Ctrl+A → Ctrl+C 로 원고를 복사한 뒤 '복사한 글 불러오기'를 눌러 주세요",
                 font=fs, fg=HINT, **lab).grid(row=1, column=0, columnspan=3, sticky="w", pady=(S(6), 0))
        self.info = tk.Label(w, text="", font=f, fg=C_GOLD, anchor="w", justify="left", **lab)
        self.info.grid(row=2, column=0, columnspan=3, sticky="w", pady=(S(10), S(12)))

        # 왼쪽: 정리하기
        left = tk.Frame(w, **lab)
        left.grid(row=3, column=0, sticky="nw")
        tk.Frame(w, bg="#3a3038", width=1).grid(row=3, column=1, sticky="ns", padx=S(24))
        right = tk.Frame(w, **lab)
        right.grid(row=3, column=2, sticky="nw")

        tk.Label(left, text="정리하기", font=fb, fg=C_TEXT, **lab).pack(anchor="w")
        tk.Label(left, text="빈 줄", font=f, fg=C_SUB, **lab).pack(anchor="w", pady=(S(10), S(2)))
        self.v_blank = tk.StringVar(value=to.get("blank", "keep"))
        rb = dict(cb)
        for val, txt in (("keep", "그대로 두기"), ("remove", "빈 줄 모두 빼기"), ("add", "문단 사이에 빈 줄 한 줄씩")):
            tk.Radiobutton(left, text=txt, variable=self.v_blank, value=val, **rb).pack(anchor="w", padx=(S(10), 0),
                                                                                       pady=S(2))
        self.v_quotes = tk.BooleanVar(value=to.get("quotes", True))
        self.v_ell = tk.BooleanVar(value=to.get("ellipsis", True))
        self.v_ell_to = tk.StringVar(value=to.get("ellipsis_to", "…"))
        self.v_trim = tk.BooleanVar(value=to.get("trim", True))
        tk.Checkbutton(left, text='둥근 따옴표로 바꾸기  ( "말" → “말” )', variable=self.v_quotes, **cb).pack(
            anchor="w", pady=(S(16), S(3)))
        er = tk.Frame(left, **lab)
        er.pack(anchor="w", pady=S(3))
        tk.Checkbutton(er, text="말줄임표 통일 →", variable=self.v_ell, **cb).pack(side="left")
        om = tk.OptionMenu(er, self.v_ell_to, "…", "……", "...")
        om.config(font=f, bg=self.FIELD, fg=C_TEXT, activebackground="#3a3038", activeforeground=C_TEXT,
                  relief="flat", highlightthickness=0, width=5)
        om["menu"].config(font=f, bg=self.FIELD, fg=C_TEXT)
        om.pack(side="left", padx=(S(6), 0))
        tk.Checkbutton(left, text="줄 끝 공백 · 겹친 띄어쓰기 정리", variable=self.v_trim, **cb).pack(anchor="w", pady=S(3))
        bf = tk.Frame(left, **lab)
        bf.pack(anchor="w", pady=(S(20), 0))
        self.button(bf, "정리해서 복사", self.do_tidy, gold=True).pack(side="left")
        self.button(bf, "원래 글로 되돌리기", self.revert).pack(side="left", padx=(S(8), 0))
        self.msg = tk.Label(left, text="", font=fs, fg=C_TYPING, anchor="w", justify="left", wraplength=S(340), **lab)
        self.msg.pack(anchor="w", pady=(S(10), 0))

        # 오른쪽: 반복 단어
        tk.Label(right, text="반복 단어", font=fb, fg=C_TEXT, **lab).pack(anchor="w")
        rr = tk.Frame(right, **lab)
        rr.pack(anchor="w", pady=(S(8), S(8)))
        self.v_rep = tk.StringVar(value="word")
        tk.Radiobutton(rr, text="단어", variable=self.v_rep, value="word", command=self.show_repeats, **rb).pack(side="left")
        tk.Radiobutton(rr, text="두 단어 표현", variable=self.v_rep, value="pair", command=self.show_repeats,
                       **rb).pack(side="left", padx=(S(10), 0))
        self.rep_lb = self.boxed_list(right, height=12, width=42)
        tk.Label(right, text="조사만 다른 말(고개를·고개가)은 하나로 묶어요", font=fs, fg=HINT, **lab).pack(
            anchor="w", pady=(S(8), 0))

        # 아래: 오늘 작업한 글자 수
        tk.Frame(w, bg="#3a3038", height=1).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(S(22), S(16)))
        bot = tk.Frame(w, **lab)
        bot.grid(row=5, column=0, columnspan=3, sticky="ew")
        head = tk.Frame(bot, **lab)
        head.pack(fill="x")
        tk.Label(head, text="오늘 작업한 글자 수", font=fb, fg=C_TEXT, **lab).pack(side="left")
        self.total = tk.Label(head, text="", font=f, fg=C_GOLD, **lab)
        self.total.pack(side="left", padx=(S(14), 0))
        self.button(head, "제거하기", self.remove).pack(side="right")
        self.button(head, "더하기", self.add, gold=True).pack(side="right", padx=(0, S(8)))
        self.pc_lb = self.boxed_list(bot, height=4, fill=True, top=S(10))
        self.msg2 = tk.Label(bot, text="같은 화를 고쳐서 다시 더하면 두 번 세지 않고 새 글자 수로 바꿔요 (첫 줄로 알아봐요)",
                             font=fs, fg=HINT, anchor="w", **lab)
        self.msg2.pack(anchor="w", pady=(S(8), 0))
        w.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_pieces()
        self.load(quiet=True)

    def boxed_list(self, parent, height, width=None, fill=False, top=0):
        """목록 둘레에 여백을 둬서 덜 빽빽하게"""
        S = self.app.S
        box = tk.Frame(parent, bg=self.FIELD, padx=S(12), pady=S(10))
        box.pack(anchor="w", fill="x" if fill else None, pady=(top, 0))
        kw = dict(height=height, font=self.fl, bg=self.FIELD, fg="#f3e7da", relief="flat", bd=0,
                  highlightthickness=0, selectbackground="#5a4a52", selectforeground="#fff6ea", activestyle="none")
        if width:
            kw["width"] = width
        lb = tk.Listbox(box, **kw)
        lb.pack(fill="both", expand=True)
        return lb

    def button(self, parent, text, cmd, gold=False):
        bf = (self.app.f_ko, 15) if self.app.round else (self.app.f_ko, 12, "bold")
        kw = dict(text=text, font=bf, command=cmd, relief="flat",
                  bd=0, padx=self.app.S(14), pady=self.app.S(6), cursor="hand2")
        if gold:
            kw.update(bg=C_GOLD, fg="#3a2a1c", activebackground="#ffe2a3", activeforeground="#3a2a1c")
        else:
            kw.update(bg="#3a3038", fg=C_TEXT, activebackground="#4a3d44", activeforeground=C_TEXT)
        return tk.Button(parent, **kw)

    def opts(self):
        o = {"blank": self.v_blank.get(), "quotes": bool(self.v_quotes.get()), "ellipsis": bool(self.v_ell.get()),
             "ellipsis_to": self.v_ell_to.get(), "trim": bool(self.v_trim.get())}
        self.app.set["tidy"] = o
        return o

    def read_clip(self):
        try:
            return self.app.root.clipboard_get()
        except tk.TclError:
            return ""

    def write_clip(self, text):
        r = self.app.root
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()

    def set_text(self, text):
        self.cur = text
        sp, ns = count_chars(text)
        fl = first_line(text)
        fl = fl[:22] + ("…" if len(fl) > 22 else "")
        self.info.config(text=f"불러온 글  {sp:,}자 (공백 제외 {ns:,}자)   ·   첫 줄: {fl}")
        self.show_repeats()

    def clear_loaded(self):
        self.orig = self.cur = ""
        self.info.config(text="비웠어요. 새 원고를 복사한 뒤 '복사한 글 불러오기'를 눌러 주세요")
        self.rep_lb.delete(0, "end")
        self.msg.config(text="")

    def load(self, quiet=False):
        t = self.read_clip()
        if quiet and t and t == getattr(self.app, "_cleared_clip", None):
            self.clear_loaded()  # 초기화로 비운 글은 저절로 다시 안 불러옴
            return
        if not quiet:
            self.app._cleared_clip = None
        if not t.strip():
            self.info.config(text="복사한 글이 없어요. 한글에서 원고를 복사해 주세요")
            self.orig = self.cur = ""
            self.rep_lb.delete(0, "end")
            return
        self.orig = t
        self.set_text(t)
        if not quiet:
            self.msg.config(text="불러왔어요", fg=C_TYPING)

    def do_tidy(self):
        if not self.orig:
            self.load()
            if not self.orig:
                return
        new = tidy_text(self.orig, self.opts())
        self.write_clip(new)
        self.set_text(new)
        self.app.save_all()
        self.msg.config(text="정리해서 복사했어요! 한글에서 Ctrl+A 한 뒤 Ctrl+V 로 붙여 넣어 주세요", fg=C_TYPING)

    def revert(self):
        if not self.orig:
            return
        self.write_clip(self.orig)
        self.set_text(self.orig)
        self.msg.config(text="원래 글을 다시 복사해 뒀어요", fg=C_TYPING)

    def show_repeats(self):
        lb = self.rep_lb
        lb.delete(0, "end")
        if not self.cur:
            return
        words, pairs = find_repeats(self.cur)
        if self.v_rep.get() == "word":
            for wd, n, forms in words[:60]:
                ex = " · ".join(f"{t} {c}" for t, c in forms if t != wd) if len(forms) > 1 or forms[0][0] != wd else ""
                lb.insert("end", f"{wd}   {n}번" + (f"   ({ex})" if ex else ""))
            if not words:
                lb.insert("end", "(세 번 넘게 나온 단어가 없어요)")
        else:
            for ph, n in pairs[:60]:
                lb.insert("end", f"{ph}   {n}번")
            if not pairs:
                lb.insert("end", "(겹치는 표현이 없어요)")

    def refresh_pieces(self):
        app = self.app
        b = app.set.get("char_basis", "sp")
        lb = self.pc_lb
        lb.delete(0, "end")
        pieces = app.td.get("pieces", [])
        for p in pieces:
            extra = ""
            if p.get("total_" + b, 0) != p.get(b, 0):
                extra = f"   (전체 {int(p.get('total_' + b, 0)):,}자 중 오늘 늘어난 만큼)"
            lb.insert("end", f"{p.get('head') or p.get('key')}   {int(p.get(b, 0)):,}자{extra}")
        if not pieces:
            lb.insert("end", "(아직 더한 글이 없어요. 원고를 불러온 뒤 '더하기'를 눌러 주세요)")
        self.total.config(text=f"{app.day_chars(app.td):,}자  ({app.basis_name()})")

    def add(self):
        if not self.cur:
            self.load()
            if not self.cur:
                return
        r = self.app.add_piece(self.cur)
        if not r:
            self.msg2.config(text="글이 비어 있어요", fg=C_PAUSE)
            return
        kind, rec, before = r
        b = self.app.set.get("char_basis", "sp")
        now = int(rec[b])
        name = rec["head"][:14]
        if kind == "update":
            t = f"같은 화라서 새 글자 수로 바꿨어요: 「{name}」 {before:,} → {now:,}자"
        elif kind == "cont":
            t = f"전에 쓰던 화라서 늘어난 만큼만 더했어요: 「{name}」 +{now:,}자"
        else:
            t = f"더했어요: 「{name}」 {now:,}자"
        self.msg2.config(text=t, fg=C_TYPING)
        self.refresh_pieces()

    def remove(self):
        sel = self.pc_lb.curselection()
        if not sel or not self.app.td.get("pieces"):
            self.msg2.config(text="제거할 글을 목록에서 먼저 골라 주세요", fg=C_PAUSE)
            return
        self.app.remove_piece(sel[0])
        self.msg2.config(text="제거했어요", fg=C_TYPING)
        self.refresh_pieces()

    def close(self):
        self.opts()
        self.app.save_all()
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
SAMPLE_TEXT = '12화. 비 오는 밤\n\n\n"왜 이제 왔어..."  그가 물었다.   \n\'괜찮아\' 하고 고개를 끄덕였다......\n고개를 들었다. 고개가 아팠다. 고개는 무거웠다.'


def text_checks():
    t = tidy_text(SAMPLE_TEXT, {"blank": "remove", "quotes": True, "ellipsis": True, "ellipsis_to": "…", "trim": True})
    words, _ = find_repeats(SAMPLE_TEXT)
    return {
        "quotes": "“왜 이제 왔어…” 그가 물었다." in t,
        "single_quotes": "‘괜찮아’ 하고" in t,
        "ellipsis": "끄덕였다…" in t,
        "blank_removed": "\n\n" not in t,
        "count": count_chars("가 나\n다") == (4, 3),
        "repeat_stem": bool(words) and words[0][0] == "고개" and words[0][1] == 4,
        "add_blank": tidy_text("a\n\n\nb\nc", {"blank": "add"}) == "a\n\nb\n\nc",
    }


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
            root.clipboard_clear()
            root.clipboard_append(SAMPLE_TEXT)
            app.open_tidy()
            tw = app._last_tidy
            tw.do_tidy()
            tw.add()
            report["tidy_result"] = root.clipboard_get()
            report["chars_today"] = app.day_chars(app.td)
            app.do_reset("all")
            if tw.cur or tw.rep_lb.size():
                errors.append("초기화해도 원고 창이 안 비워짐")
            tw.close()
            app.reset_today()
            if not app.canvas.find_withtag("resetmenu"):
                errors.append("초기화 팝업이 안 뜸")
            app.pick_reset("all")
            if app.day_chars(app.td) or app.td["sec"]:
                errors.append("초기화가 안 됨")
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
            report["text_checks"] = text_checks()
            if not all(report["text_checks"].values()):
                errors.append("원고 정리 계산이 틀림")
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
    elif o == "reset":
        root.after(300, app.reset_today)
    elif o == "tidy":
        def _tidy():
            root.clipboard_clear()
            root.clipboard_append(SAMPLE_TEXT * 3)
            app.open_tidy()
            if os.environ.get("TIMER_THEN_RESET"):
                root.after(600, lambda: app.do_reset("all"))
        root.after(300, _tidy)
    elif o == "picker":
        root.after(300, lambda: (app.open_settings(), root.after(300, lambda: WindowPicker(app._last_sw))))
    root.mainloop()
    if SELFTEST:
        rep = load_json(DATA_DIR / "selftest.json", {})
        sys.exit(1 if rep.get("errors") or not rep else 0)
