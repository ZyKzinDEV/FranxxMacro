import customtkinter as ctk
from tkinter import messagebox
import json, threading, time, random, ctypes, ctypes.wintypes, math, atexit, warnings, sys, zipfile, shutil
import os, subprocess, tempfile, urllib.request, urllib.error
warnings.filterwarnings("ignore", category=ResourceWarning)
from pathlib import Path
from collections import deque

# ── Auto-Update ───────────────────────────────────────────────────────────────
APP_VERSION = "4.0.0"   # Versão atual do executável

# URL do ficheiro JSON com a versão mais recente.
# Formato esperado:
#   { "version": "4.1.0",
#     "download_url": "https://github.com/.../releases/download/v4.1.0/FranxxMacro.exe",
#     "changelog": "- Fix X\n- Add Y" }
# ⚠️ Substitui pela URL do teu repositório/pastebin:
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/ZyKzinDEV/FranxxMacro/main/version.json"

# ── Low-level SendInput (bypasses Python/pynput layers) ──────────────────────
# INPUT type constants
_INPUT_KEYBOARD = 1
_INPUT_MOUSE    = 0
_KEYEVENTF_KEYUP        = 0x0002
_KEYEVENTF_EXTENDEDKEY  = 0x0001
_MOUSEEVENTF_LEFTDOWN   = 0x0002
_MOUSEEVENTF_LEFTUP     = 0x0004
_MOUSEEVENTF_RIGHTDOWN  = 0x0008
_MOUSEEVENTF_RIGHTUP    = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP   = 0x0040
_MOUSEEVENTF_WHEEL      = 0x0800
_MOUSEEVENTF_XDOWN      = 0x0080
_MOUSEEVENTF_XUP        = 0x0100
_XBUTTON1 = 0x0001
_XBUTTON2 = 0x0002

# Virtual-key code table for common keys
_VK_MAP = {
    "f": 0x46, "q": 0x51, "e": 0x45, "r": 0x52, "t": 0x54,
    "g": 0x47, "h": 0x48, "y": 0x59, "z": 0x5A, "x": 0x58,
    "c": 0x43, "v": 0x56, "b": 0x42, "n": 0x4E, "m": 0x4D,
    "a": 0x41, "s": 0x53, "d": 0x44, "w": 0x57, "u": 0x55,
    "i": 0x49, "o": 0x4F, "p": 0x50, "j": 0x4A, "k": 0x4B,
    "l": 0x4C,
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39, "0": 0x30,
    "space": 0x20, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11,
    "alt": 0x12, "tab": 0x09, "escape": 0x1B, "backspace": 0x08,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.c_ushort),
        ("wScan",       ctypes.c_ushort),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT_UNION)]

_user32   = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_winmm    = ctypes.windll.winmm
_winmm.timeBeginPeriod(1)   # Resolve o timer do Windows de ~15ms → 1ms (ENORME para CPS alto)

def _sendinput_key(vk: int):
    """Press + release a key via SendInput — one syscall each direction."""
    inputs = (_INPUT * 2)()
    for i, flags in enumerate((0, _KEYEVENTF_KEYUP)):
        inputs[i].type = _INPUT_KEYBOARD
        inputs[i]._input.ki.wVk    = vk
        inputs[i]._input.ki.wScan  = 0
        inputs[i]._input.ki.dwFlags = flags
    _user32.SendInput(2, inputs, ctypes.sizeof(_INPUT))

def _sendinput_mouse(down_flag: int, up_flag: int, data: int = 0):
    """Press + release a mouse button via SendInput."""
    inputs = (_INPUT * 2)()
    for i, flag in enumerate((down_flag, up_flag)):
        inputs[i].type = _INPUT_MOUSE
        inputs[i]._input.mi.dwFlags   = flag
        inputs[i]._input.mi.mouseData = data
    _user32.SendInput(2, inputs, ctypes.sizeof(_INPUT))

# ── High-priority thread helper ───────────────────────────────────────────────
_ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
_HIGH_PRIORITY_CLASS         = 0x00000080
_THREAD_PRIORITY_HIGHEST     = 2

def _boost_current_thread():
    """Raise the current thread to HIGHEST priority to reduce jitter."""
    try:
        handle = _kernel32.GetCurrentThread()
        _kernel32.SetThreadPriority(handle, _THREAD_PRIORITY_HIGHEST)
    except Exception:
        pass

try:
    from PIL import Image as PIL_Image
    from PIL import ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import keyboard
    import mouse
except ImportError:
    raise SystemExit("pip install keyboard mouse")

try:
    import win32gui, win32process, psutil
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    from pynput import keyboard as pynput_keyboard
    from pynput import mouse as pynput_mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    from pypresence import Presence as _Presence
    PYPRESENCE_AVAILABLE = True
except ImportError:
    PYPRESENCE_AVAILABLE = False

# ── Compatibilidade com PyInstaller --onefile ─────────────────────────────────
# ASSET_DIR  -> sys._MEIPASS: pasta temporaria onde o PyInstaller extrai os
#               ficheiros embutidos em runtime. Assets ficam dentro do .exe.
# PROFILE_DIR -> junto ao .exe: os perfis sao dados do utilizador, precisam
#               de persistir e ser editaveis fora do bundle.
if getattr(sys, "frozen", False):
    ASSET_DIR   = Path(sys._MEIPASS) / "assets"
    PROFILE_DIR = Path(sys.executable).parent / "profiles"
else:
    BASE_DIR    = Path(__file__).parent
    ASSET_DIR   = BASE_DIR / "assets"
    PROFILE_DIR = BASE_DIR / "profiles"

PROFILE_DIR.mkdir(exist_ok=True)
BG_IMAGE_PATH = ASSET_DIR / "bg.png"
ICON_PATH = ASSET_DIR / "icon.png"
ICON_ICO_PATH = ASSET_DIR / "icon.ico"

# ── Theme ─────────────────────────────────────────────────────────────────────
BLACK = {
    "bg":        "#09090d",
    "panel":     "transparent",
    "card":      "transparent",
    "accent":    "#c0392b",      # red accent
    "accent2":   "#3a3a3e",
    "success":   "#27ae60",
    "warning":   "#e67e22",
    "text":      "#f0f0f0",
    "subtext":   "#8a8a9a",
    "border":    "#2a2a30",
    "live":      "#2ecc71",
    "live_dim":  "#1a6b3a",
    "highlight": "#e74c3c",
}

DEFAULT_PROFILE = {
    "name": "Default",
    "macros": {
        "click_spam": {
            "enabled": True,
            "key": "f",
            "cps": 30.0,
            "jitter_ms": 0,
            "mode": "toggle",
            "burst_count": 1,
            "burst_gap_ms": 0,
            "hold_mode": False,
            "humanize": False,
        },
        "ability": {
            "enabled": True,
            "key": "q",
            "cps": 10.0,
            "jitter_ms": 4,
            "mode": "toggle",
            "burst_count": 1,
            "burst_gap_ms": 20,
            "hold_mode": False,
            "humanize": True,
        },
        "sequence": {
            "enabled": False,
            "steps": [
                {"key": "shift", "delay_ms": 90},
                {"key": "f",     "delay_ms": 70},
                {"key": "q",     "delay_ms": 150},
            ],
            "loop": True,
        },
    },
    "hotkeys": {
        "start_stop":   "f1",
        "emergency":    "f12",
        "toggle_spam":  "f2",
        "toggle_seq":   "f3",
        "cps_up":       "f5",
        "cps_down":     "f6",
        "hotkey_mode":  "toggle",
    },
    "safety": {
        "roblox_only":      True,
        "test_mode":        False,
        "min_interval_ms":  1,
        "discord_rpc":      True,
    },
}

current_theme = BLACK

# ── Background & glass helpers ────────────────────────────────────────────────
def hex_to_rgb(h):
    return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))


def make_bg(w, h):
    global _bg_pil
    if not PIL_AVAILABLE:
        return None
    img = PIL_Image.new("RGBA", (w, h), (9, 9, 13, 255))
    if BG_IMAGE_PATH.exists():
        try:
            user_img = PIL_Image.open(BG_IMAGE_PATH).convert("RGBA").resize((w, h), PIL_Image.Resampling.LANCZOS)
            dim = PIL_Image.new("RGBA", (w, h), (0, 0, 0, 55))
            img = PIL_Image.alpha_composite(user_img, dim)
        except Exception:
            pass
    else:
        draw = ImageDraw.Draw(img)
        a = hex_to_rgb("#141416")
        b = hex_to_rgb("#1a1a20")
        for x in range(-h, w + h, 80):
            draw.line([(x, 0), (x + h, h)], fill=a + (22,), width=2)
        for y in range(0, h, 96):
            draw.rectangle([0, y, w, y + 40], fill=b + (14,))
    _bg_pil = img
    return ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))


_bg_pil = None


def make_card_image(w, h, alpha=155, radius=14):
    if not PIL_AVAILABLE or _bg_pil is None:
        return None
    try:
        cropped = _bg_pil.resize((w, h), PIL_Image.Resampling.LANCZOS).convert("RGBA")
        overlay = PIL_Image.new("RGBA", (w, h), (10, 10, 16, alpha))
        mask = PIL_Image.new("L", (w, h), 0)
        from PIL import ImageDraw as _ID
        _ID.Draw(mask).rounded_rectangle([0, 0, w-1, h-1], radius=radius, fill=255)
        overlay.putalpha(mask)
        result = PIL_Image.alpha_composite(cropped, overlay)
        border_draw = _ID.Draw(result)
        border_draw.rounded_rectangle([0, 0, w-1, h-1], radius=radius, outline=(60, 60, 80, 160), width=1)
        return ctk.CTkImage(light_image=result, dark_image=result, size=(w, h))
    except Exception:
        return None


class GlassFrame(ctk.CTkFrame):
    def __init__(self, parent, alpha=155, radius=14, **kw):
        kw.setdefault("fg_color", "transparent")
        kw.setdefault("corner_radius", radius)
        kw.setdefault("border_width", 0)
        super().__init__(parent, **kw)
        self._alpha = alpha
        self._radius = radius
        self._img_label = ctk.CTkLabel(self, text="", image=None)
        self._img_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._img_label.lower()
        self._job = None
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(60, self._redraw)

    def _redraw(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        img = make_card_image(w, h, alpha=self._alpha, radius=self._radius)
        if img:
            self._img_label.configure(image=img)


def sf(parent, **kw):
    alpha = kw.pop("alpha", 155)
    use_glass = kw.pop("glass", True)
    radius = kw.get("r", 14)
    t = current_theme
    if use_glass and PIL_AVAILABLE:
        return GlassFrame(parent, alpha=alpha, radius=radius,
                          corner_radius=radius,
                          border_width=kw.get("bw", 0))
    return ctk.CTkFrame(parent,
                        fg_color=kw.get("fg", "transparent"),
                        corner_radius=radius,
                        border_width=kw.get("bw", 1),
                        border_color=kw.get("bc", t["border"]))


def lbl(parent, text, size=13, bold=False, color=None, **kw):
    t = current_theme
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont("Segoe UI", size, weight="bold" if bold else "normal"),
                        text_color=color or t["text"], **kw)


def btn(parent, text, cmd, color=None, width=120, **kw):
    t = current_theme
    return ctk.CTkButton(parent, text=text, command=cmd,
                         fg_color=color or t["accent"],
                         hover_color="#a93226",
                         font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
                         corner_radius=8, width=width, **kw)


# ── Stats ─────────────────────────────────────────────────────────────────────
def gaussian_jitter(base_ms, jitter_ms):
    if jitter_ms <= 0:
        return base_ms
    sigma = jitter_ms / 3.0
    offset = random.gauss(0, sigma)
    offset = max(-jitter_ms, min(jitter_ms, offset))
    return max(1.0, base_ms + offset)


class Stats:
    def __init__(self):
        self.total_clicks = 0
        self.session_clicks = 0
        self.session_start = None
        self._timestamps = deque(maxlen=60)
        self._cps_history = deque(maxlen=300)   # (wall_time, cps) pairs
        self._lock = threading.Lock()
        self.peak_cps = 0.0

    def record(self):
        with self._lock:
            now = time.perf_counter()
            self._timestamps.append(now)
            self.total_clicks += 1
            self.session_clicks += 1

    def live_cps(self):
        with self._lock:
            now = time.perf_counter()
            cutoff = now - 1.0
            cps = float(len([t for t in self._timestamps if t >= cutoff]))
            if cps > self.peak_cps:
                self.peak_cps = cps
            self._cps_history.append((time.time(), cps))
            return cps

    def cps_history_snapshot(self, window_s=30):
        """Returns list of (secs_ago, cps) for the last window_s seconds."""
        with self._lock:
            now = time.time()
            return [(now - t, c) for t, c in self._cps_history if now - t <= window_s]

    def uptime(self):
        if self.session_start is None:
            return "00:00"
        s = int(time.time() - self.session_start)
        return f"{s//60:02d}:{s%60:02d}"

    def reset_session(self):
        self.session_clicks = 0
        self.session_start = time.time()
        self.peak_cps = 0.0

    def stop_session(self):
        self.session_start = None


stats = Stats()


# ── Macro Recorder ────────────────────────────────────────────────────────────
class MacroRecorder:
    """Records keypresses/clicks in real-time and converts them to sequence steps."""
    def __init__(self):
        self._recording = False
        self._steps = []
        self._last_time = None
        self._listener_kb = None
        self._listener_ms = None
        self._lock = threading.Lock()

    @property
    def recording(self):
        return self._recording

    def start(self):
        if self._recording or not PYNPUT_AVAILABLE:
            return
        self._recording = True
        self._steps = []
        self._last_time = time.perf_counter()

        _BTN_MAP = {
            pynput_mouse.Button.left:   "lmb",
            pynput_mouse.Button.right:  "rmb",
            pynput_mouse.Button.middle: "mmb",
            pynput_mouse.Button.x1:     "x1",
            pynput_mouse.Button.x2:     "x2",
        }

        def _on_key(key):
            if not self._recording:
                return False
            try:
                if hasattr(key, "char") and key.char:
                    k = key.char.lower()
                else:
                    k = str(key).replace("Key.", "").lower()
                self._add_step(k)
            except Exception:
                pass

        def _on_click(x, y, button, pressed):
            if not pressed or not self._recording:
                return
            bn = _BTN_MAP.get(button, "")
            if bn:
                self._add_step(bn)

        self._listener_kb = pynput_keyboard.Listener(on_press=_on_key)
        self._listener_kb.daemon = True
        self._listener_kb.start()
        self._listener_ms = pynput_mouse.Listener(on_click=_on_click)
        self._listener_ms.daemon = True
        self._listener_ms.start()

    def _add_step(self, key):
        with self._lock:
            now = time.perf_counter()
            delay = int((now - self._last_time) * 1000)
            self._last_time = now
            self._steps.append({"key": key, "delay_ms": max(10, delay)})

    def stop(self):
        self._recording = False
        for lst in (self._listener_kb, self._listener_ms):
            if lst:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._listener_kb = None
        self._listener_ms = None

    def get_steps(self):
        with self._lock:
            return list(self._steps)


recorder = MacroRecorder()


# ── Window-profile auto-switcher ──────────────────────────────────────────────
class WindowWatcher:
    """Monitors foreground window title; auto-loads the matching profile."""
    def __init__(self):
        self._rules = {}   # {keyword_lower: profile_name}
        self._running = False
        self._last_win = ""
        self.on_switch = None   # callback(profile_name)

    def set_rules(self, rules: dict):
        self._rules = {k.lower(): v for k, v in rules.items()}

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="win-watcher").start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                if WIN32_AVAILABLE:
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd).lower()
                    if title != self._last_win:
                        self._last_win = title
                        for kw, pname in self._rules.items():
                            if kw in title:
                                try:
                                    if engine.load_profile(pname):
                                        engine.start_hotkeys()
                                        if self.on_switch:
                                            self.on_switch(pname)
                                except Exception:
                                    pass
                                break
            except Exception:
                pass
            time.sleep(1.0)


watcher = WindowWatcher()


# ── Engine ────────────────────────────────────────────────────────────────────
class MacroEngine:
    def __init__(self):
        self.running = False
        self.spam_active = False
        self.seq_active = False
        self.profile = json.loads(json.dumps(DEFAULT_PROFILE))
        # ── Eventos de stop separados por loop ─────────────────────────────
        # Um Event partilhado fazia stop_spam() matar também a seq e vice-versa.
        self._stop_spam = threading.Event()
        self._stop_seq  = threading.Event()
        self._threads = []
        self.status_cb = None
        self.listener = None
        self._listener_lock = threading.Lock()
        self.active_macro = None
        self._suppressor = None
        self._suppress_key = None

    def _focused(self):
        if self.profile["safety"].get("test_mode"):
            return True
        if not WIN32_AVAILABLE:
            return True
        if not self.profile["safety"].get("roblox_only"):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
            return "roblox" in psutil.Process(pid).name().lower()
        except Exception:
            return True

    def _send(self, key):
        if not self._focused():
            return
        k = (key or "").lower().strip()
        if not k:
            return  # tecla vazia — ignora silenciosamente
        try:
            if k in ("lmb", "left_click", "click"):
                _sendinput_mouse(_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP)
            elif k in ("rmb", "right_click"):
                _sendinput_mouse(_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP)
            elif k in ("mmb", "middle_click"):
                _sendinput_mouse(_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP)
            elif k == "scroll_up":
                _sendinput_mouse(_MOUSEEVENTF_WHEEL, _MOUSEEVENTF_WHEEL, 120)
            elif k == "scroll_down":
                _sendinput_mouse(_MOUSEEVENTF_WHEEL, _MOUSEEVENTF_WHEEL, ctypes.c_ulong(-120).value)
            elif k == "x1":
                _sendinput_mouse(_MOUSEEVENTF_XDOWN, _MOUSEEVENTF_XUP, _XBUTTON1)
            elif k == "x2":
                _sendinput_mouse(_MOUSEEVENTF_XDOWN, _MOUSEEVENTF_XUP, _XBUTTON2)
            else:
                vk = _VK_MAP.get(k)
                if vk:
                    _sendinput_key(vk)
                else:
                    # Fallback para teclas não mapeadas (ex: caracteres especiais)
                    keyboard.press_and_release(k)
            stats.record()
        except Exception as exc:
            print(f"[SEND] Erro ao enviar tecla {k!r}: {exc}")

    def _wait_spam(self, ms):
        """Hybrid wait: sleep for most of the interval, spin-wait the last 2ms for precision."""
        if ms <= 0:
            return self._stop_spam.is_set()
        secs = ms / 1000.0
        if ms > 4:
            # Sleep for (ms - 2ms), then spin the rest
            sleep_secs = secs - 0.002
            if self._stop_spam.wait(sleep_secs):
                return True
            deadline = time.perf_counter() + 0.002
            while time.perf_counter() < deadline:
                if self._stop_spam.is_set():
                    return True
            return False
        else:
            # Very short interval — pure spin-wait
            deadline = time.perf_counter() + secs
            while time.perf_counter() < deadline:
                if self._stop_spam.is_set():
                    return True
            return False

    def _wait_seq(self, ms):
        return self._stop_seq.wait(ms / 1000)

    def _start_thread(self, target, *args):
        # Remove threads já terminadas para evitar crescimento ilimitado
        self._threads = [th for th in self._threads if th.is_alive()]
        t = threading.Thread(target=target, args=args, daemon=True)
        self._threads.append(t)
        t.start()
        return t

    def _calc_interval(self, cfg):
        cps = float(cfg.get("cps", 10.0))
        cps = max(1.0, cps)
        return max(1, int(1000 / cps))

    def _spam_loop(self, cfg):
        _boost_current_thread()
        print(f"[LOOP] _spam_loop iniciado: stop={self._stop_spam.is_set()}, spam_active={self.spam_active}, focused={self._focused()}")
        try:
            while not self._stop_spam.is_set() and self.spam_active:
                if not self._focused():
                    if self._wait_spam(50): break
                    continue
                base_ms  = self._calc_interval(cfg)
                jitter   = max(0, int(cfg.get("jitter_ms", 0)))
                burst    = max(1, int(cfg.get("burst_count", 1)))
                gap      = max(0, int(cfg.get("burst_gap_ms", 0)))
                humanize = cfg.get("humanize", True)
                for _ in range(burst):
                    if self._stop_spam.is_set() or not self.spam_active: break
                    self._send(cfg["key"])
                    wt = gaussian_jitter(base_ms, jitter) if humanize else base_ms + (random.randint(0, jitter) if jitter else 0)
                    if self._wait_spam(wt): return
                extra = gaussian_jitter(gap, jitter // 2) if humanize and jitter else gap
                if self._wait_spam(max(0, extra)): break
        except Exception as exc:
            print(f"[SPAM_LOOP] Excepção inesperada: {exc}")
        finally:
            # Garante estado consistente mesmo que a thread morra por erro
            if self.spam_active:
                self.spam_active = False
                self._stop_spam.set()
                self._cb("spam", "stopped")

    def _hold_spam_loop(self, cfg):
        _boost_current_thread()
        try:
            while not self._stop_spam.is_set() and self.spam_active:
                if not self._focused():
                    if self._wait_spam(50): break
                    continue
                base_ms  = self._calc_interval(cfg)
                jitter   = max(0, int(cfg.get("jitter_ms", 0)))
                humanize = cfg.get("humanize", True)
                self._send(cfg["key"])
                wt = gaussian_jitter(base_ms, jitter) if humanize else base_ms + (random.randint(0, jitter) if jitter else 0)
                if self._wait_spam(wt): break
        except Exception as exc:
            print(f"[HOLD_LOOP] Excepção inesperada: {exc}")
        finally:
            if self.spam_active:
                self.spam_active = False
                self._stop_spam.set()
                self._cb("spam", "stopped")

    def _seq_loop(self, steps, loop):
        _boost_current_thread()
        try:
            while not self._stop_seq.is_set() and self.seq_active:
                for step in steps:
                    if self._stop_seq.is_set() or not self.seq_active: break
                    if not self._focused():
                        if self._wait_seq(50): return
                        continue
                    self._send(step["key"])
                    if self._wait_seq(max(10, int(step["delay_ms"]))): return
                if not loop:
                    self.seq_active = False
                    break
        except Exception as exc:
            print(f"[SEQ_LOOP] Excepção inesperada: {exc}")
        finally:
            if self.seq_active:
                self.seq_active = False
                self._stop_seq.set()
                self._cb("seq", "stopped")

    def _cb(self, w, s):
        if self.status_cb:
            self.status_cb(w, s)

    # ── CPU Affinity ────────────────────────────────────────────────────────
    def _set_cpu_affinity(self):
        """Pin macro threads to a dedicated CPU core to reduce OS jitter."""
        try:
            import psutil as _ps
            p = _ps.Process()
            cpus = list(range(_ps.cpu_count()))
            if len(cpus) >= 2:
                p.cpu_affinity([cpus[-1]])   # last core — usually least busy
        except Exception:
            pass

    # ── Sound feedback ──────────────────────────────────────────────────────
    def _beep(self, freq=880, dur=80):
        """Short beep via Windows Beep (no extra libs needed)."""
        try:
            _kernel32.Beep(freq, dur)
        except Exception:
            pass

    # ── Session log ────────────────────────────────────────────────────────
    def _write_session_log(self):
        try:
            log_dir = PROFILE_DIR.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            ts = time.strftime("%Y-%m-%d_%H-%M-%S")
            fname = log_dir / f"session_{ts}.txt"
            duration = stats.uptime()
            lines = [
                f"FranXX Macro — Session Log",
                f"Date/Time  : {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Profile    : {self.profile.get('name', 'Default')}",
                f"Target CPS : {self.profile['macros']['click_spam']['cps']:.1f}",
                f"Peak CPS   : {stats.peak_cps:.1f}",
                f"Session clicks: {stats.session_clicks}",
                f"Total clicks  : {stats.total_clicks}",
                f"Duration   : {duration}",
            ]
            fname.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            print(f"[LOG] Falha ao escrever log: {exc}")

    # ── Countdown then start ────────────────────────────────────────────────
    def start_with_countdown(self, seconds: int, on_tick=None, on_start=None):
        """Count down `seconds`, calling on_tick(n) each second, then start."""
        def _cd():
            for n in range(seconds, 0, -1):
                if on_tick:
                    on_tick(n)
                time.sleep(1.0)
            if on_start:
                on_start()
        threading.Thread(target=_cd, daemon=True).start()

    def start_spam(self):
        cfg = self.profile["macros"]["click_spam"]
        if not cfg["enabled"]:
            print("[SPAM] Bloqueado: click_spam não está enabled no perfil")
            return
        if self.spam_active:
            print("[SPAM] Bloqueado: spam já está ativo")
            return
        self._stop_spam.clear()
        self.spam_active = True
        self.active_macro = "spam"
        stats.reset_session()
        self._start_thread(self._hold_spam_loop if cfg.get("hold_mode") else self._spam_loop, cfg)
        self._cb("spam", "running")
        if self.profile.get("safety", {}).get("discord_rpc", True):
            discord_rpc.notify_start(cfg.get("cps", 30.0), self.profile.get("name", "Default"))

    def stop_spam(self):
        self.spam_active = False
        self._stop_spam.set()
        if self.active_macro == "spam": self.active_macro = None
        stats.stop_session()
        self._cb("spam", "stopped")
        if self.profile.get("safety", {}).get("discord_rpc", True):
            discord_rpc.notify_stop(self.profile.get("name", "Default"))

    def start_seq(self):
        cfg = self.profile["macros"]["sequence"]
        if not cfg["enabled"] or self.seq_active: return
        self._stop_seq.clear()
        self.seq_active = True
        self.active_macro = "seq"
        stats.reset_session()
        self._start_thread(self._seq_loop, cfg["steps"], cfg["loop"])
        self._cb("seq", "running")

    def stop_seq(self):
        self.seq_active = False
        self._stop_seq.set()
        if self.active_macro == "seq": self.active_macro = None
        stats.stop_session()
        self._cb("seq", "stopped")

    def emergency_stop(self):
        self._stop_spam.set()
        self._stop_seq.set()
        self.spam_active  = False
        self.seq_active   = False
        self.running      = False
        self.active_macro = None
        stats.stop_session()
        self._cb("all", "emergency_stop")
        if self.profile.get("safety", {}).get("discord_rpc", True):
            discord_rpc.notify_stop(self.profile.get("name", "Default"))
        # Limpa os eventos em background para não bloquear a GUI
        def _clear():
            time.sleep(0.08)
            self._stop_spam.clear()
            self._stop_seq.clear()
        threading.Thread(target=_clear, daemon=True).start()

    def toggle_master(self):
        if self.running:
            self.stop_spam(); self.stop_seq(); self.running = False
        else:
            self.running = True
            self.start_spam(); self.start_seq()

    def toggle_spam(self):
        if self.spam_active: self.stop_spam()
        else: self.start_spam()

    def toggle_seq(self):
        if self.seq_active: self.stop_seq()
        else: self.start_seq()

    def cps_up(self):
        cfg = self.profile["macros"]["click_spam"]
        cfg["cps"] = round(cfg["cps"] + 5.0, 1)
        self._cb("cps_change", cfg["cps"])

    def cps_down(self):
        cfg = self.profile["macros"]["click_spam"]
        cfg["cps"] = max(0.1, round(cfg["cps"] - 5.0, 1))
        self._cb("cps_change", cfg["cps"])

    # ── Hotkey listener ────────────────────────────────────────────────────
    # ── Listener watchdog ──────────────────────────────────────────────────
    def _listener_alive(self):
        """True se todos os listeners activos estão vivos."""
        for attr in ('listener', '_suppressor_listener', '_mouse_listener'):
            lst = getattr(self, attr, None)
            if lst is not None and not lst.is_alive():
                return False
        return True

    def _start_watchdog(self):
        """Thread que reinicia os hotkeys se um listener morrer inesperadamente."""
        if getattr(self, '_watchdog_running', False):
            return
        self._watchdog_running = True
        def _watch():
            while self._watchdog_running:
                time.sleep(3)
                if not self._listener_alive():
                    print('[WATCHDOG] Listener morreu — a reiniciar hotkeys')
                    try:
                        self.start_hotkeys()
                    except Exception as exc:
                        print(f'[WATCHDOG] Falha ao reiniciar: {exc}')
        threading.Thread(target=_watch, daemon=True, name='hotkey-watchdog').start()

    def start_hotkeys(self):
        if not PYNPUT_AVAILABLE:
            return False

        hk        = self.profile["hotkeys"]
        mode      = hk.get("hotkey_mode", "toggle")
        start_key = hk["start_stop"].lower()

        # Always clean up previous hooks / listeners first
        self._stop_suppressor()

        other_mapped = {
            hk["emergency"].lower():           self.emergency_stop,
            hk["toggle_spam"].lower():         self.toggle_spam,
            hk["toggle_seq"].lower():          self.toggle_seq,
            hk.get("cps_up",   "f5").lower():  self.cps_up,
            hk.get("cps_down", "f6").lower():  self.cps_down,
        }

        # ── helpers ────────────────────────────────────────────────────────
        _MOUSE_BTN_MAP = {
            pynput_mouse.Button.x1:     "x1",
            pynput_mouse.Button.x2:     "x2",
            pynput_mouse.Button.left:   "lmb",
            pynput_mouse.Button.right:  "rmb",
            pynput_mouse.Button.middle: "mmb",
        }

        def _key_name(key):
            try:
                if hasattr(key, "char") and key.char:
                    return key.char.lower()
                return str(key).replace("Key.", "").lower()
            except Exception:
                return ""

        def _is_mouse_key(k):
            return k in ("x1", "x2", "lmb", "rmb", "mmb")

        if mode == "hold":
            # ── Hold mode ──────────────────────────────────────────────────
            self._suppress_key = start_key
            _held = [False]

            # Bloqueia apenas a start_key no nível do driver (só para teclas de teclado)
            if not _is_mouse_key(start_key):
                try:
                    import keyboard as _kb
                    _kb.block_key(start_key)
                    self._blocked_key = start_key
                except Exception:
                    self._blocked_key = None
            else:
                self._blocked_key = None

            def on_press_hold(key):
                try:
                    kn = _key_name(key)
                    if kn == start_key:
                        if not _held[0]:
                            _held[0] = True
                            if not self.running:
                                self.running = True
                                print(f"[HOLD] KEY_DOWN → a iniciar (focused={self._focused()})")
                                self.start_spam()
                                self.start_seq()
                    else:
                        fn = other_mapped.get(kn)
                        if fn:
                            fn()
                except Exception:
                    pass

            def on_release_hold(key):
                try:
                    kn = _key_name(key)
                    if kn == start_key:
                        _held[0] = False
                        if self.running:
                            print("[HOLD] KEY_UP → a parar")
                            self.stop_spam()
                            self.stop_seq()
                            self.running = False
                            if self.status_cb:
                                self.status_cb("all", "stopped")
                except Exception:
                    pass

            # Mouse hold callbacks (for x1/x2/lmb/rmb/mmb as start key)
            def on_mouse_click_hold(x, y, button, pressed):
                try:
                    bn = _MOUSE_BTN_MAP.get(button, "")
                    if bn == start_key:
                        if pressed and not _held[0]:
                            _held[0] = True
                            if not self.running:
                                self.running = True
                                print(f"[HOLD-MOUSE] BTN_DOWN {bn} → a iniciar")
                                self.start_spam()
                                self.start_seq()
                        elif not pressed and _held[0]:
                            _held[0] = False
                            if self.running:
                                print(f"[HOLD-MOUSE] BTN_UP {bn} → a parar")
                                self.stop_spam()
                                self.stop_seq()
                                self.running = False
                                if self.status_cb:
                                    self.status_cb("all", "stopped")
                    elif pressed:
                        fn = other_mapped.get(bn)
                        if fn:
                            fn()
                except Exception:
                    pass

            with self._listener_lock:
                try:
                    if self.listener:
                        self.listener.stop()
                except Exception:
                    pass
                if getattr(self, "_suppressor_listener", None):
                    try:
                        self._suppressor_listener.stop()
                    except Exception:
                        pass
                if getattr(self, "_mouse_listener", None):
                    try:
                        self._mouse_listener.stop()
                    except Exception:
                        pass

                self._suppressor_listener = pynput_keyboard.Listener(
                    on_press=on_press_hold,
                    on_release=on_release_hold,
                    suppress=False,
                )
                self._suppressor_listener.daemon = True
                self._suppressor_listener.start()

                self._mouse_listener = pynput_mouse.Listener(on_click=on_mouse_click_hold)
                self._mouse_listener.daemon = True
                self._mouse_listener.start()

                self.listener = None

        else:
            # ── Toggle mode ────────────────────────────────────────────────
            self._suppress_key = None
            if getattr(self, "_blocked_key", None):
                try:
                    import keyboard as _kb
                    _kb.unblock_key(self._blocked_key)
                except Exception:
                    pass
                self._blocked_key = None

            _toggle_cooldown = [0.0]

            def on_press(key):
                try:
                    kn = _key_name(key)
                    if kn == start_key:
                        now = time.monotonic()
                        if now - _toggle_cooldown[0] < 0.15:
                            return
                        _toggle_cooldown[0] = now
                        self.toggle_master()
                        return
                    fn = other_mapped.get(kn)
                    if fn:
                        fn()
                except Exception:
                    pass

            # Mouse toggle callback (for x1/x2/lmb/rmb/mmb as start key)
            def on_mouse_click_toggle(x, y, button, pressed):
                if not pressed:
                    return
                try:
                    bn = _MOUSE_BTN_MAP.get(button, "")
                    if bn == start_key:
                        now = time.monotonic()
                        if now - _toggle_cooldown[0] < 0.15:
                            return
                        _toggle_cooldown[0] = now
                        self.toggle_master()
                    else:
                        fn = other_mapped.get(bn)
                        if fn:
                            fn()
                except Exception:
                    pass

            with self._listener_lock:
                try:
                    if self.listener:
                        self.listener.stop()
                except Exception:
                    pass
                if getattr(self, "_mouse_listener", None):
                    try:
                        self._mouse_listener.stop()
                    except Exception:
                        pass

                self.listener = pynput_keyboard.Listener(on_press=on_press)
                self.listener.daemon = True
                self.listener.start()

                self._mouse_listener = pynput_mouse.Listener(on_click=on_mouse_click_toggle)
                self._mouse_listener.daemon = True
                self._mouse_listener.start()

        self._start_watchdog()
        return True

    def _stop_suppressor(self):
        """Para todos os listeners e limpa estado de supressão."""
        # Desbloqueia a tecla que foi bloqueada com keyboard.block_key()
        blocked = getattr(self, "_blocked_key", None)
        if blocked:
            try:
                import keyboard as _kb
                _kb.unblock_key(blocked)
            except Exception:
                pass
            self._blocked_key = None
        with self._listener_lock:
            for attr in ("listener", "_suppressor_listener", "_mouse_listener"):
                lst = getattr(self, attr, None)
                if lst:
                    try:
                        lst.stop()
                    except Exception:
                        pass
                    setattr(self, attr, None)
        self._suppress_key = None

    def list_profiles(self):
        return [f.stem for f in PROFILE_DIR.glob("*.json")] or ["Default"]

    def save_profile(self, name):
        """Escrita atómica: escreve para .tmp e faz rename — nunca corrompe o ficheiro."""
        target = PROFILE_DIR / f"{name}.json"
        tmp    = target.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.profile, indent=2), encoding="utf-8")
            tmp.replace(target)
        except Exception as exc:
            print(f"[PROFILE] Erro ao guardar {name!r}: {exc}")
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def load_profile(self, name):
        """Carrega perfil com fallback para backup e merge de campos em falta."""
        path   = PROFILE_DIR / f"{name}.json"
        backup = path.with_suffix(".bak")

        def _merge(base, override):
            """Aplica override sobre base recursivamente — garante campos novos do DEFAULT."""
            result = json.loads(json.dumps(base))
            for k, v in override.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k] = _merge(result[k], v)
                else:
                    result[k] = v
            return result

        for candidate in (path, backup):
            if not candidate.exists():
                continue
            try:
                raw  = candidate.read_text(encoding="utf-8")
                data = json.loads(raw)
                self.profile = _merge(json.loads(json.dumps(DEFAULT_PROFILE)), data)
                # Cria backup do ficheiro bom
                if candidate == path:
                    try:
                        backup.write_text(raw, encoding="utf-8")
                    except Exception:
                        pass
                return True
            except Exception as exc:
                print(f"[PROFILE] Ficheiro corrompido {candidate.name}: {exc} — a tentar backup")
        return False

    def new_profile(self, name):
        self.profile = json.loads(json.dumps(DEFAULT_PROFILE))
        self.profile["name"] = name


# ── Discord Rich Presence ─────────────────────────────────────────────────────
# Uses a public Blade Ball community App ID — no account needed.
# Falls back silently if Discord is not running or pypresence is missing.
_DISCORD_CLIENT_ID = "1505710238136013002"   # Franxx Macro App ID

class DiscordRPC:
    def __init__(self):
        self._rpc = None
        self._connected = False
        self._enabled = True
        self._start_ts = None
        self._lock = threading.Lock()
        self._thread = None
        self._stop_evt = threading.Event()

    def enable(self, on: bool):
        self._enabled = on
        if on:
            self._ensure_connected()
            import time as _time; _time.sleep(0.5)
            self._push("idle")
        else:
            self._disconnect()

    def _ensure_connected(self):
        if not PYPRESENCE_AVAILABLE or not self._enabled:
            return
        if self._connected:
            return
        try:
            self._rpc = _Presence(_DISCORD_CLIENT_ID)
            self._rpc.connect()
            self._connected = True
        except Exception:
            self._connected = False
            self._rpc = None

    def _disconnect(self):
        try:
            if self._rpc:
                self._rpc.close()
        except Exception:
            pass
        self._rpc = None
        self._connected = False

    # Substitui os placeholders pelos links reais quando tiveres.
    _BUTTONS = [
        {"label": "⬇ Download Macro",     "url": "https://example.com/download"},
        # {"label": "⚔ Jogar Blade Ball", "url": "https://www.roblox.com/games/13772394625"},
    ]

    def _push(self, state: str, cps: float = 0.0, profile: str = "Default"):
        if not PYPRESENCE_AVAILABLE or not self._enabled:
            return
        self._ensure_connected()
        if not self._connected:
            return
        try:
            if state == "running":
                details   = f"⚡ Spamming  •  {cps:.0f} CPS"
                status    = f"🗡 Profile: {profile}"
                small_img = "sword"
                small_txt = "🟢 Macro ON"
                if self._start_ts is None:
                    self._start_ts = int(time.time())
            elif state == "idle":
                details   = "💤 Macro Stopped  •  Waiting"
                status    = f"📁 Profile: {profile}"
                small_img = "idle"
                small_txt = "🔴 Macro Off"
                self._start_ts = None
            else:
                details   = "🎮 Using Franxx Macro"
                status    = ""
                small_img = "idle"
                small_txt = "Franxx Macro"
                self._start_ts = None

            self._rpc.update(
                details=details,
                state=status,
                start=self._start_ts,
                large_image="icon",
                large_text="FRANXX MACRO",
                small_image=small_img,
                small_text=small_txt,
                buttons=self._BUTTONS,
            )
        except Exception:
            # Lost connection -- try to reconnect next time
            self._connected = False
            self._rpc = None

    def notify_start(self, cps: float, profile: str):
        threading.Thread(target=self._push, args=("running", cps, profile), daemon=True).start()

    def notify_stop(self, profile: str):
        threading.Thread(target=self._push, args=("idle", 0.0, profile), daemon=True).start()


discord_rpc = DiscordRPC()

engine = MacroEngine()


# ── GUI ───────────────────────────────────────────────────────────────────────
# ── Auto-Updater ──────────────────────────────────────────────────────────────
class AutoUpdater:
    """Verifica atualizações em background e mostra dialogo se existir versão nova."""

    def __init__(self, app: "BladeBallMacro"):
        self.app = app
        self._dl_thread: threading.Thread | None = None
        # Verifica após 3 s para não bloquear o startup
        app.after(3000, self._start_check)

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_version(v: str) -> tuple:
        """Converte '4.1.0' → (4, 1, 0). Ignora prefix 'v'."""
        try:
            return tuple(int(x) for x in v.strip().lstrip("v").split("."))
        except Exception:
            return (0,)

    def _is_newer(self, remote: str, local: str) -> bool:
        return self._parse_version(remote) > self._parse_version(local)

    # ── check ─────────────────────────────────────────────────────────────────
    def _start_check(self):
        threading.Thread(target=self._check_thread, daemon=True).start()

    def _check_thread(self):
        try:
            req = urllib.request.Request(
                UPDATE_CHECK_URL,
                headers={"User-Agent": f"FranxxMacro/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            remote_ver = data.get("version", "0.0.0")
            if self._is_newer(remote_ver, APP_VERSION):
                self.app.after(0, lambda: self._show_update_dialog(data))
        except Exception:
            pass   # Sem internet ou URL inválida — ignora silenciosamente

    # ── dialog ────────────────────────────────────────────────────────────────
    def _show_update_dialog(self, data: dict):
        """Mostra banner de atualização no canto da janela principal."""
        t = current_theme
        remote_ver  = data.get("version", "?")
        download_url = data.get("download_url", "")
        changelog   = data.get("changelog", "Sem notas de versão.")

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Atualização Disponível")
        dlg.geometry("440x320")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color="#09090d")
        dlg.grab_set()

        # ── header ──
        hdr = ctk.CTkFrame(dlg, fg_color=t["accent"], corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr,
                     text=f"⬆  Nova versão disponível: v{remote_ver}",
                     font=ctk.CTkFont("Segoe UI", 13, weight="bold"),
                     text_color="white").pack(padx=16, pady=10, anchor="w")

        # ── current vs new ──
        ver_row = ctk.CTkFrame(dlg, fg_color="transparent")
        ver_row.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(ver_row,
                     text=f"Atual:  v{APP_VERSION}   →   Nova:  v{remote_ver}",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=t["subtext"]).pack(anchor="w")

        # ── changelog ──
        ctk.CTkLabel(dlg, text="Novidades:",
                     font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
                     text_color=t["subtext"]).pack(anchor="w", padx=16, pady=(10, 2))
        log_box = ctk.CTkTextbox(dlg, height=100, fg_color="#13131a",
                                 font=ctk.CTkFont("Segoe UI", 11),
                                 text_color=t["text"], corner_radius=8)
        log_box.pack(fill="x", padx=16)
        log_box.insert("end", changelog)
        log_box.configure(state="disabled")

        # ── progress bar (oculta até ao download) ──
        self._progress_var = ctk.DoubleVar(value=0)
        self._progress_bar = ctk.CTkProgressBar(dlg, variable=self._progress_var,
                                                  fg_color="#1a1a22",
                                                  progress_color=t["accent"],
                                                  height=8, corner_radius=4)
        self._progress_bar.pack(fill="x", padx=16, pady=(8, 0))
        self._progress_bar.pack_forget()   # esconde por defeito

        self._status_lbl = ctk.CTkLabel(dlg, text="",
                                         font=ctk.CTkFont("Segoe UI", 10),
                                         text_color=t["subtext"])
        self._status_lbl.pack(pady=(2, 0))

        # ── buttons ──
        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(8, 14))
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self._dl_btn = ctk.CTkButton(
            btn_row,
            text="⬇  Instalar Atualização",
            font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
            fg_color=t["accent"], hover_color="#a93226",
            corner_radius=8, height=34,
            command=lambda: self._start_download(download_url, dlg),
        )
        self._dl_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_row,
            text="Agora não",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#1a1a22", hover_color="#2a2a35",
            corner_radius=8, height=34,
            command=dlg.destroy,
        ).grid(row=0, column=1, sticky="ew")

    # ── download & replace ────────────────────────────────────────────────────
    def _start_download(self, url: str, dlg: ctk.CTkToplevel):
        if not url:
            messagebox.showerror("Erro", "URL de download não definida no version.json.")
            return
        self._dl_btn.configure(state="disabled", text="A transferir...")
        self._progress_bar.pack(fill="x", padx=16, pady=(8, 0))
        self._dl_thread = threading.Thread(
            target=self._download_thread, args=(url, dlg), daemon=True
        )
        self._dl_thread.start()

    def _download_thread(self, url: str, dlg: ctk.CTkToplevel):
        try:
            tmp_dir  = tempfile.mkdtemp(prefix="franxx_upd_")
            tmp_exe  = os.path.join(tmp_dir, "FranxxMacro_new.exe")

            # ── download com progresso ──
            req = urllib.request.Request(url, headers={"User-Agent": f"FranxxMacro/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 65536   # 64 KB
                with open(tmp_exe, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if total > 0:
                            progress = downloaded / total
                            self.app.after(0, lambda p=progress: (
                                self._progress_var.set(p),
                                self._status_lbl.configure(
                                    text=f"A transferir... {downloaded // 1024} KB / {total // 1024} KB"
                                )
                            ))

            self.app.after(0, lambda: self._apply_update(tmp_exe, dlg))

        except Exception as e:
            self.app.after(0, lambda err=str(e): (
                messagebox.showerror("Erro de download", f"Não foi possível transferir a atualização:\n{err}"),
                self._dl_btn.configure(state="normal", text="⬇  Instalar Atualização"),
                self._progress_bar.pack_forget(),
            ))

    def _apply_update(self, new_exe: str, dlg: ctk.CTkToplevel):
        """Cria batch de substituição, lança-o e fecha a app atual."""
        self._status_lbl.configure(text="A instalar…")

        if getattr(sys, "frozen", False):
            current_exe = sys.executable
        else:
            # Modo dev: não substitui nada, abre o ficheiro na pasta
            messagebox.showinfo(
                "Modo Dev",
                f"Novo executável transferido para:\n{new_exe}\n\nEm produção (.exe) seria aplicado automaticamente.",
            )
            dlg.destroy()
            return

        # ── bat de substituição ──
        bat_path = os.path.join(os.path.dirname(new_exe), "_franxx_update.bat")
        bat_content = (
            "@echo off\n"
            "title FranXX Macro - Updater\n"
            "echo A aguardar fecho da app...\n"
            f":wait\n"
            f"tasklist /fi \"PID eq {os.getpid()}\" 2>nul | find \"{os.getpid()}\" >nul\n"
            "if not errorlevel 1 (\n"
            "    timeout /t 1 /nobreak >nul\n"
            "    goto wait\n"
            ")\n"
            "echo A instalar atualização...\n"
            f"copy /y \"{new_exe}\" \"{current_exe}\"\n"
            f"start \"\" \"{current_exe}\"\n"
            "del \"%~f0\"\n"   # auto-delete do batch
        )
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        dlg.destroy()
        self.app.destroy()

    # ── verificação manual ────────────────────────────────────────────────────
    def check_manual(self):
        """Chamado pelo botão 'Verificar Atualizações' nas definições."""
        threading.Thread(target=self._check_manual_thread, daemon=True).start()

    def _check_manual_thread(self):
        try:
            req = urllib.request.Request(
                UPDATE_CHECK_URL,
                headers={"User-Agent": f"FranxxMacro/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            remote_ver = data.get("version", "0.0.0")
            if self._is_newer(remote_ver, APP_VERSION):
                self.app.after(0, lambda: self._show_update_dialog(data))
            else:
                self.app.after(0, lambda: messagebox.showinfo(
                    "Atualização", f"✅  Já tens a versão mais recente (v{APP_VERSION})."
                ))
        except Exception as e:
            self.app.after(0, lambda err=str(e): messagebox.showerror(
                "Erro", f"Não foi possível verificar atualizações:\n{err}"
            ))


class BladeBallMacro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("FranXX Macro")
        self.geometry("1100x720")
        self.minsize(940, 600)
        self.configure(fg_color="#09090d")
        ctk.set_appearance_mode("dark")
        self.attributes("-alpha", 0.97)

        # Ícone — guardamos o path e aplicamos via after() para
        # garantir que o customtkinter nao o reseta durante o init.
        if ICON_PATH.exists() and PIL_AVAILABLE:
            try:
                _img = PIL_Image.open(ICON_PATH).convert("RGBA")
                icon_ctk = ctk.CTkImage(light_image=_img, dark_image=_img, size=(32, 32))
                self._icon_ctk = icon_ctk
            except Exception:
                pass


        self.capture_target = None
        self._bg_image = None
        self._resize_job = None
        self._bg_label = ctk.CTkLabel(self, text="", image=None)
        self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._cps_labels = {}
        # Dummy label — substituído pelo real depois do build_spam_tab
        self.quick_cps_lbl = ctk.CTkLabel(self, text="")

        self._build_sidebar()
        self._build_main()

        engine.status_cb = self._on_status
        engine.start_hotkeys()
        # Init Discord RPC if enabled in profile
        if engine.profile.get("safety", {}).get("discord_rpc", True):
            threading.Thread(target=discord_rpc.enable, args=(True,), daemon=True).start()
        self._poll()
        self.after(120, self._draw_bg)
        self.after(200, self._apply_icon)
        self.after(600, self._apply_icon)   # segunda passagem — garante title bar depois do CTk inicializar
        self.bind("<Configure>", self._on_configure)
        atexit.register(self._autosave)
        self._start_autosave_loop()
        self.after(600, self._setup_tray)
        self.updater = AutoUpdater(self)

    def _apply_icon(self):
        """Aplica o icone da janela e barra de tarefas apos o CTk inicializar."""
        try:
            if ICON_PATH.exists() and PIL_AVAILABLE:
                from PIL import ImageTk
                _img = PIL_Image.open(ICON_PATH).convert("RGBA")
                self._icon_tk_large = ImageTk.PhotoImage(_img.resize((64, 64)))
                self._icon_tk_small = ImageTk.PhotoImage(_img.resize((32, 32)))
                # iconphoto no root Tk real — e o que o Windows usa para o title bar
                self.iconphoto(True, self._icon_tk_large, self._icon_tk_small)
                # wm_iconphoto no widget raiz (CTk por vezes tem um Tk interno separado)
                try:
                    root_tk = self._w  # referencia interna do Tk
                    self.tk.call("wm", "iconphoto", root_tk, self._icon_tk_large, self._icon_tk_small)
                except Exception:
                    pass
            # iconbitmap por ultimo — garante icone na taskbar do Windows
            if ICON_ICO_PATH.exists():
                self.iconbitmap(default=str(ICON_ICO_PATH))
        except Exception as exc:
            print(f"[ICON] Falha ao aplicar icone: {exc}")

    def _autosave(self):
        """Called on exit — stop engine, save current profile."""
        try:
            engine.emergency_stop()
        except Exception:
            pass
        try:
            engine._stop_suppressor()
        except Exception:
            pass
        try:
            engine.save_profile(self.profile_var.get().strip() or "Default")
        except Exception:
            pass

    def _start_autosave_loop(self):
        """Saves the current profile every 60 seconds in the background."""
        def _loop():
            while True:
                time.sleep(60)
                try:
                    name = self.profile_var.get().strip() or "Default"
                    engine.save_profile(name)
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True, name="autosave")
        t.start()

    def _export_profiles(self):
        """Exports all profiles to a zip file chosen by the user."""
        from tkinter import filedialog
        profiles = list(PROFILE_DIR.glob("*.json"))
        if not profiles:
            messagebox.showwarning("Export", "No profiles found to export.")
            return
        # Save current profile first so it is included
        try:
            engine.save_profile(self.profile_var.get().strip() or "Default")
        except Exception:
            pass
        dest = filedialog.asksaveasfilename(
            title="Export profiles",
            defaultextension=".zip",
            filetypes=[("Zip archive", "*.zip")],
            initialfile="franxx_profiles_backup.zip",
        )
        if not dest:
            return
        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in PROFILE_DIR.glob("*.json"):
                    zf.write(p, p.name)
            messagebox.showinfo("Export", f"Profiles exported successfully!\n{dest}")
        except Exception as exc:
            messagebox.showerror("Export error", f"Could not export profiles:\n{exc}")

    def _import_profiles(self):
        """Imports profiles from a previously exported zip file."""
        from tkinter import filedialog
        src = filedialog.askopenfilename(
            title="Import profiles",
            filetypes=[("Zip archive", "*.zip")],
        )
        if not src:
            return
        try:
            with zipfile.ZipFile(src, "r") as zf:
                names = [n for n in zf.namelist() if n.endswith(".json")]
                if not names:
                    messagebox.showwarning("Import", "No profiles found in the selected file.")
                    return
                zf.extractall(PROFILE_DIR)
            self.profile_menu.configure(values=engine.list_profiles())
            messagebox.showinfo("Import", f"{len(names)} profile(s) imported successfully!")
        except Exception as exc:
            messagebox.showerror("Import error", f"Could not import profiles:\n{exc}")

    def _on_configure(self, event):
        if event.widget is self:
            if self._resize_job: self.after_cancel(self._resize_job)
            self._resize_job = self.after(120, self._draw_bg)

    def _draw_bg(self):
        try:
            w, h = self.winfo_width(), self.winfo_height()
            if w < 80 or h < 80:
                self.after(100, self._draw_bg); return
            self._bg_image = make_bg(w, h)
            if self._bg_image:
                self._bg_label.configure(image=self._bg_image)
            self.after(80, self._refresh_glass_frames)
        except Exception:
            self.after(150, self._draw_bg)

    def _refresh_glass_frames(self):
        def _r(widget):
            if isinstance(widget, GlassFrame): widget._redraw()
            for c in widget.winfo_children(): _r(c)
        _r(self)

    # ── Key capture ────────────────────────────────────────────────────────
    def _bind_capture(self):
        self.bind_all("<KeyPress>",    self._capture_key)
        self.bind_all("<Button-1>",    self._capture_mouse)
        self.bind_all("<Button-2>",    self._capture_mouse)
        self.bind_all("<Button-3>",    self._capture_mouse)
        self.bind_all("<MouseWheel>",  self._capture_mousewheel)
        # Botões laterais (X1/X2) não chegam ao tkinter via <Button-8/9> no Windows.
        # Usamos um pynput listener temporário só durante a captura.
        self._start_capture_mouse_listener()

    def _start_capture_mouse_listener(self):
        """Inicia um pynput mouse listener temporário para capturar X1/X2 durante a captura."""
        if not PYNPUT_AVAILABLE:
            return
        self._stop_capture_listener()  # limpa qualquer listener anterior

        _BTN_MAP = {
            pynput_mouse.Button.x1:     "x1",
            pynput_mouse.Button.x2:     "x2",
            pynput_mouse.Button.left:   "lmb",
            pynput_mouse.Button.right:  "rmb",
            pynput_mouse.Button.middle: "mmb",
        }

        def _on_click(x, y, button, pressed):
            if not pressed:
                return
            # Só X1/X2 — os outros são capturados pelo tkinter normalmente
            bn = _BTN_MAP.get(button, "")
            if bn in ("x1", "x2") and self.capture_target:
                # Envia para o thread da GUI via after() — thread-safe
                self.after(0, lambda b=bn: self._finish_capture(b))

        self._capture_mouse_listener = pynput_mouse.Listener(on_click=_on_click)
        self._capture_mouse_listener.daemon = True
        self._capture_mouse_listener.start()

    def _stop_capture_listener(self):
        """Para e limpa o listener pynput temporário de captura."""
        lst = getattr(self, "_capture_mouse_listener", None)
        if lst:
            try:
                lst.stop()
            except Exception:
                pass
            self._capture_mouse_listener = None

    def _unbind_capture(self):
        for ev in ("<KeyPress>", "<Button-1>", "<Button-2>", "<Button-3>", "<MouseWheel>"):
            self.unbind_all(ev)
        self._stop_capture_listener()
        self.capture_target = None

    def _start_capture(self, macro_name, target_var, label_widget):
        self.capture_target = ("macro", macro_name, target_var, label_widget)
        label_widget.configure(text="↩ press a key or button…", text_color=current_theme["warning"])
        self._bind_capture()

    def _start_hotkey_capture(self, hk_key, var, label):
        self.capture_target = ("hotkey", hk_key, var, label)
        label.configure(text="↩ press a key or button…", text_color=current_theme["warning"])
        self._bind_capture()

    def _start_capture_step(self, idx, var, label):
        self.capture_target = ("step", idx, var, label)
        label.configure(text="↩ press a key or button…", text_color=current_theme["warning"])
        self._bind_capture()

    def _finish_capture(self, key):
        if not self.capture_target: return
        kind, ref, var, label = self.capture_target
        display = key.upper() if key else "—"
        var.set(key)
        label.configure(text=display, text_color=current_theme["text"])
        if kind == "hotkey":
            engine.profile["hotkeys"][ref] = key
            engine.start_hotkeys()
        elif kind == "step":
            engine.profile["macros"]["sequence"]["steps"][ref]["key"] = key
        else:
            engine.profile["macros"][ref]["key"] = key
        self._unbind_capture()

    def _capture_key(self, event):
        if not self.capture_target: return
        key = (event.keysym or "").lower()
        aliases = {"shift_l": "shift", "shift_r": "shift",
                   "control_l": "ctrl", "control_r": "ctrl",
                   "alt_l": "alt", "alt_r": "alt", "option": "alt"}
        key = aliases.get(key, key)
        self._finish_capture(key)

    def _capture_mousewheel(self, event):
        if not self.capture_target: return
        self._finish_capture("scroll_up" if getattr(event, "delta", 0) > 0 else "scroll_down")

    def _capture_mouse(self, event):
        if not self.capture_target: return
        mapping = {1: "lmb", 2: "mmb", 3: "rmb", 8: "x1", 9: "x2"}
        self._finish_capture(mapping.get(getattr(event, "num", None), f"mouse{event.num}"))

    def _clear_macro_key(self, mk, var, label):
        var.set("")
        label.configure(text="—", text_color=current_theme["subtext"])
        engine.profile["macros"][mk]["key"] = ""

    def _clear_step_key(self, idx, var, label):
        var.set("")
        label.configure(text="—", text_color=current_theme["subtext"])
        engine.profile["macros"]["sequence"]["steps"][idx]["key"] = ""

    # ── Sidebar ────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        t = current_theme
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color="#0d0d12",
                                    corner_radius=0, border_width=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # Logo
        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))
        if ICON_PATH.exists() and PIL_AVAILABLE:
            try:
                ic = PIL_Image.open(ICON_PATH)
                ic_ctk = ctk.CTkImage(light_image=ic, dark_image=ic, size=(44, 44))
                ctk.CTkLabel(logo, text="", image=ic_ctk).pack()
            except Exception:
                ctk.CTkLabel(logo, text="⚔", font=ctk.CTkFont("Segoe UI", 32, weight="bold"),
                             text_color=t["accent"]).pack()
        else:
            ctk.CTkLabel(logo, text="⚔", font=ctk.CTkFont("Segoe UI", 32, weight="bold"),
                         text_color=t["accent"]).pack()
        ctk.CTkLabel(logo, text="FranXX Macro",
                     font=ctk.CTkFont("Segoe UI", 13, weight="bold"),
                     text_color=t["text"]).pack()
        ctk.CTkLabel(logo, text="discord.gg/HYpA5bEjrZ",
                     font=ctk.CTkFont("Segoe UI", 9),
                     text_color=t["subtext"]).pack()

        ctk.CTkFrame(self.sidebar, height=1, fg_color=t["border"]).grid(
            row=1, column=0, sticky="ew", padx=14, pady=6)

        # ── START / STOP ──
        self.master_btn = ctk.CTkButton(
            self.sidebar, text="▶  START  (F1)", command=self._toggle_master_ui,
            font=ctk.CTkFont("Segoe UI", 14, weight="bold"),
            fg_color=t["success"], hover_color="#1e8449",
            text_color="#fff", corner_radius=10, height=48)
        self.master_btn.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 4))

        ctk.CTkButton(self.sidebar, text="🛑  EMERGENCY  (F12)",
                      command=engine.emergency_stop,
                      fg_color="#2a0a0a", hover_color="#3d1010", text_color="#ff6060",
                      font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
                      corner_radius=8, height=30).grid(
            row=3, column=0, sticky="ew", padx=14, pady=(0, 6))

        ctk.CTkFrame(self.sidebar, height=1, fg_color=t["border"]).grid(
            row=4, column=0, sticky="ew", padx=14, pady=4)

        # ── Live status ──
        si = sf(self.sidebar, alpha=180)
        si.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 4))
        si.grid_columnconfigure(0, weight=1)
        self.spam_ind     = lbl(si, "● Spam: OFF",    size=10, color=t["subtext"])
        self.seq_ind      = lbl(si, "● Seq:  OFF",    size=10, color=t["subtext"])
        self.roblox_ind   = lbl(si, "● Roblox: …",   size=10, color=t["subtext"])
        self.live_cps_ind = lbl(si, "⚡ Live CPS: 0", size=10, color=t["subtext"])
        for i, w in enumerate([self.spam_ind, self.seq_ind, self.roblox_ind, self.live_cps_ind]):
            w.grid(row=i, column=0, sticky="w", padx=10,
                   pady=(6 if i == 0 else 1, 6 if i == 3 else 1))

        ctk.CTkFrame(self.sidebar, height=1, fg_color=t["border"]).grid(
            row=6, column=0, sticky="ew", padx=14, pady=4)

        # ── Nav ──
        nf = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nf.grid(row=7, column=0, sticky="ew", padx=8)
        nf.grid_columnconfigure(0, weight=1)
        self.nav_btns = {}
        nav_items = [
            ("🗡  Click Spam",    "spam"),
            ("⚡  Sequences",     "seq"),
            ("⏺  Recorder",      "recorder"),
            ("🔑  Hotkeys",       "bindings"),
            ("🛡  Safety",         "safety"),
            ("📊  Statistics",    "stats"),
            ("🪟  Auto-Profile",  "autopro"),
        ]
        for i, (txt, key) in enumerate(nav_items):
            b = ctk.CTkButton(nf, text=txt, command=lambda k=key: self._switch_tab(k),
                              fg_color="transparent", hover_color="#1e1e28",
                              text_color=t["text"], anchor="w",
                              font=ctk.CTkFont("Segoe UI", 12), corner_radius=8, height=36)
            b.grid(row=i, column=0, sticky="ew", pady=1)
            self.nav_btns[key] = b

        ctk.CTkFrame(self.sidebar, height=1, fg_color=t["border"]).grid(
            row=8, column=0, sticky="ew", padx=14, pady=4)

        # ── Profile ──
        pf = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        pf.grid(row=9, column=0, sticky="ew", padx=14, pady=(0, 6))
        pf.grid_columnconfigure(0, weight=1)
        lbl(pf, "PROFILE", size=9, color=t["subtext"]).grid(row=0, column=0, sticky="w")
        self.profile_var = ctk.StringVar(value="Default")
        self.profile_menu = ctk.CTkOptionMenu(
            pf, variable=self.profile_var, values=engine.list_profiles(),
            fg_color="#1a1a22", button_color=t["accent2"], text_color=t["text"],
            command=self._load_profile_by_name, height=28)
        self.profile_menu.grid(row=1, column=0, sticky="ew", pady=(3, 4))
        bf = ctk.CTkFrame(pf, fg_color="transparent")
        bf.grid(row=2, column=0, sticky="ew")
        bf.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(bf, text="💾 Save", command=self._save_profile,
                      font=ctk.CTkFont("Segoe UI", 10), height=26, corner_radius=7,
                      fg_color=t["accent2"], hover_color="#555").grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(bf, text="✨ New", command=self._new_profile,
                      font=ctk.CTkFont("Segoe UI", 10), height=26, corner_radius=7,
                      fg_color="#2a2a35", hover_color="#3a3a45").grid(row=0, column=1, sticky="ew")
        ef = ctk.CTkFrame(pf, fg_color="transparent")
        ef.grid(row=3, column=0, sticky="ew", pady=(3, 0))
        ef.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(ef, text="📤 Export", command=self._export_profiles,
                      font=ctk.CTkFont("Segoe UI", 10), height=26, corner_radius=7,
                      fg_color="#1a2a1a", hover_color="#253525",
                      text_color="#7ec87e").grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(ef, text="📥 Import", command=self._import_profiles,
                      font=ctk.CTkFont("Segoe UI", 10), height=26, corner_radius=7,
                      fg_color="#1a1a2a", hover_color="#252535",
                      text_color="#7e9ec8").grid(row=0, column=1, sticky="ew")
        lbl(pf, "Export before updating — Import to restore", size=8,
            color=t["subtext"]).grid(row=4, column=0, sticky="w", pady=(3, 0))

        # ── Overlay button ──
        ctk.CTkFrame(self.sidebar, height=1, fg_color=t["border"]).grid(
            row=10, column=0, sticky="ew", padx=14, pady=(8, 4))
        btn(self.sidebar, "🪟  Overlay", self._open_overlay,
            color=t["accent2"], width=180, height=30
            ).grid(row=11, column=0, sticky="ew", padx=14, pady=(0, 6))

        # ── Update check + version ──
        ctk.CTkFrame(self.sidebar, height=1, fg_color=t["border"]).grid(
            row=12, column=0, sticky="ew", padx=14, pady=(4, 4))
        upd_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        upd_row.grid(row=13, column=0, sticky="ew", padx=14, pady=(0, 4))
        upd_row.grid_columnconfigure(0, weight=1)
        btn(upd_row, "🔄  Verificar Updates",
            lambda: self.updater.check_manual(),
            color="#1a2a1a", width=180, height=26
            ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(upd_row,
                     text=f"v{APP_VERSION}",
                     font=ctk.CTkFont("Segoe UI", 9),
                     text_color=t["subtext"]).grid(row=1, column=0, sticky="e", pady=(2, 0))

    # ── Main content ───────────────────────────────────────────────────────
    def _build_main(self):
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=18, pady=16)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.tabs = {}
        for key in ("spam", "seq", "recorder", "bindings", "safety", "stats", "autopro"):
            f = ctk.CTkFrame(self.content, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_rowconfigure(0, weight=1)
            f.grid_columnconfigure(0, weight=1)
            self.tabs[key] = f
        self._build_spam_tab(self.tabs["spam"])
        self._build_seq_tab(self.tabs["seq"])
        self._build_recorder_tab(self.tabs["recorder"])
        self._build_bindings_tab(self.tabs["bindings"])
        self._build_safety_tab(self.tabs["safety"])
        self._build_stats_tab(self.tabs["stats"])
        self._build_autopro_tab(self.tabs["autopro"])
        self._switch_tab("spam")

    def _switch_tab(self, key):
        self.tabs[key].tkraise()
        t = current_theme
        for k, b in self.nav_btns.items():
            b.configure(fg_color=t["accent"] if k == key else "transparent")

    # ── SPAM TAB ───────────────────────────────────────────────────────────
    def _build_spam_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        lbl(hdr, "🗡  Click Spam", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "Set a key and CPS for each spam slot.  Press START or F1 to activate.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        scroll = ctk.CTkScrollableFrame(wrap, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        scroll.grid_columnconfigure(0, weight=1)

        presets = [10, 15, 20, 25, 30, 40, 50]

        for idx, (mk, title, icon) in enumerate([
            ("click_spam", "Parry / Block Spam",  "🗡"),
            ("ability",    "Ability Spam",          "⚡"),
        ]):
            cfg  = engine.profile["macros"][mk]
            card = sf(scroll, alpha=155)
            card.grid(row=idx, column=0, sticky="ew", pady=6, padx=3)
            card.grid_columnconfigure(0, weight=1)

            en_var    = ctk.BooleanVar(value=cfg["enabled"])
            hold_var  = ctk.BooleanVar(value=cfg.get("hold_mode", False))
            human_var = ctk.BooleanVar(value=cfg.get("humanize", True))

            # ── Title row ──
            title_row = ctk.CTkFrame(card, fg_color="transparent")
            title_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
            title_row.grid_columnconfigure(0, weight=1)
            lbl(title_row, f"{icon}  {title}", size=15, bold=True).grid(row=0, column=0, sticky="w")
            ctk.CTkSwitch(title_row, text="Enabled", variable=en_var, width=46,
                          command=lambda v=en_var, m=mk: self._set_macro_enabled(m, v),
                          progress_color=t["success"], button_color=t["accent2"]
                          ).grid(row=0, column=1, sticky="e")

            # ── Key + CPS row ──
            row1 = ctk.CTkFrame(card, fg_color="transparent")
            row1.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
            row1.grid_columnconfigure(1, weight=1)

            # Key block
            kf = sf(row1, alpha=80, r=8)
            kf.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            lbl(kf, "KEY", size=9, color=t["subtext"]).pack(anchor="w", padx=10, pady=(8, 2))
            kv = ctk.StringVar(value=cfg["key"])
            key_disp = lbl(kf, kv.get().upper() or "—", size=20, bold=True, color=t["text"])
            key_disp.pack(anchor="w", padx=12)
            kb_row = ctk.CTkFrame(kf, fg_color="transparent")
            kb_row.pack(anchor="w", padx=8, pady=(6, 8))
            btn(kb_row, "Set key", lambda m=mk, v=kv, l=key_disp: self._start_capture(m, v, l),
                width=80, height=28).pack(side="left", padx=(0, 4))
            btn(kb_row, "Clear", lambda m=mk, v=kv, l=key_disp: self._clear_macro_key(m, v, l),
                color=t["accent2"], width=58, height=28).pack(side="left")

            # CPS block
            cf = sf(row1, alpha=80, r=8)
            cf.grid(row=0, column=1, sticky="nsew")
            lbl(cf, "CLICKS PER SECOND  (CPS)", size=9, color=t["subtext"]).pack(anchor="w", padx=10, pady=(8, 2))
            cv = ctk.StringVar(value=f"{float(cfg.get('cps', 10.0)):.1f}")
            vcmd = (self.register(self._validate_float_input), "%P")
            cl = lbl(cf, f"{float(cfg.get('cps', 10.0)):.1f}", size=22, bold=True, color=t["accent"])
            cl.pack(anchor="w", padx=12)
            if mk == "click_spam":
                self._cps_labels[mk] = cl
            # Preset buttons (most useful ones only)
            pr = ctk.CTkFrame(cf, fg_color="transparent")
            pr.pack(anchor="w", padx=8, pady=(4, 0))
            for p in presets:
                ctk.CTkButton(pr, text=str(p), width=34, height=26, corner_radius=6,
                              fg_color=t["accent2"], hover_color=t["accent"],
                              font=ctk.CTkFont("Segoe UI", 11),
                              command=lambda x=p, m=mk, la=cl, va=cv: self._set_cps_preset(m, x, va, la)
                              ).pack(side="left", padx=2)
            # Manual entry
            entry_row = ctk.CTkFrame(cf, fg_color="transparent")
            entry_row.pack(anchor="w", padx=8, pady=(4, 8))
            cps_e = ctk.CTkEntry(entry_row, textvariable=cv, width=80, height=28,
                                 validate="key", validatecommand=vcmd)
            cps_e.pack(side="left", padx=(0, 6))
            btn(entry_row, "Apply", lambda m=mk, v=cv, l=cl: self._set_cps_entry(m, v, l),
                width=70, height=28).pack(side="left")

            # ── Options row ──
            opt_row = ctk.CTkFrame(card, fg_color="transparent")
            opt_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
            ctk.CTkSwitch(opt_row, text="Hold to activate  (hold key instead of toggle)",
                          variable=hold_var,
                          command=lambda v=hold_var, m=mk: self._set_hold_mode(m, v),
                          font=ctk.CTkFont("Segoe UI", 11)).pack(side="left", padx=(0, 24))
            ctk.CTkSwitch(opt_row, text="Humanize  (vary timing slightly)",
                          variable=human_var,
                          command=lambda v=human_var, m=mk: self._set_humanize(m, v),
                          progress_color=t["live_dim"],
                          font=ctk.CTkFont("Segoe UI", 11)).pack(side="left")

        # Tip
        tip = sf(scroll, alpha=100, r=10)
        tip.grid(row=2, column=0, sticky="ew", pady=(4, 2), padx=3)
        lbl(tip, "💡  Recommended settings for Blade Ball", size=11, bold=True, color="#d4d460").pack(anchor="w", padx=14, pady=(10, 4))
        for line in [
            "CPS: 25–35  •  Humanize: OFF  •  Hold to activate: ON",
            "Above 35 CPS, Roblox starts dropping inputs — more isn't better.",
        ]:
            lbl(tip, line, size=10, color="#a0a060").pack(anchor="w", padx=14)
        lbl(tip, "", size=4).pack()

    # ── SEQ TAB ────────────────────────────────────────────────────────────
    def _build_seq_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        lbl(hdr, "⚡  Sequences", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "A sequence presses multiple keys in order, one after another.  Enable Loop to repeat.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        ctrl = ctk.CTkFrame(wrap, fg_color="transparent")
        ctrl.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        ctrl.grid_columnconfigure(3, weight=1)
        se = ctk.BooleanVar(value=engine.profile["macros"]["sequence"]["enabled"])
        le = ctk.BooleanVar(value=engine.profile["macros"]["sequence"]["loop"])
        ctk.CTkSwitch(ctrl, text="Enable sequence", variable=se,
                      command=lambda: self._set_seq_opt("enabled", se.get()),
                      font=ctk.CTkFont("Segoe UI", 12)).grid(row=0, column=0, padx=(0, 20))
        ctk.CTkSwitch(ctrl, text="Loop", variable=le,
                      command=lambda: self._set_seq_opt("loop", le.get()),
                      font=ctk.CTkFont("Segoe UI", 12)).grid(row=0, column=1, padx=(0, 20))
        btn(ctrl, "+ Add step", self._add_seq_step, width=100, height=32).grid(row=0, column=2, padx=(0, 8))
        btn(ctrl, "Reset", self._clear_seq, color=t["accent2"], width=80, height=32).grid(row=0, column=3, sticky="e")

        self.seq_frame = ctk.CTkScrollableFrame(wrap, fg_color="transparent")
        self.seq_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.seq_frame.grid_columnconfigure(0, weight=1)
        self._refresh_seq_ui()

    def _refresh_seq_ui(self):
        for w in self.seq_frame.winfo_children():
            w.destroy()
        t = current_theme
        for i, step in enumerate(engine.profile["macros"]["sequence"]["steps"]):
            row = sf(self.seq_frame, alpha=145)
            row.grid(row=i, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(2, weight=1)

            lbl(row, f"Step {i+1}", size=12, bold=True, color=t["accent"]
                ).grid(row=0, column=0, padx=14, pady=12)
            kv = ctk.StringVar(value=step["key"])
            key_disp = lbl(row, kv.get().upper() or "—", size=14, bold=True, color=t["text"], width=90)
            key_disp.grid(row=0, column=1, padx=8, pady=12)
            btn(row, "Set key", lambda v=kv, l=key_disp, idx=i: self._start_capture_step(idx, v, l),
                width=80, height=30).grid(row=0, column=2, padx=4)
            lbl(row, "then wait", size=10, color=t["subtext"]).grid(row=0, column=3, padx=(12, 4))
            dv = ctk.IntVar(value=step["delay_ms"])
            de = ctk.CTkEntry(row, textvariable=dv, width=70, height=30, corner_radius=6)
            de.grid(row=0, column=4, padx=4, pady=12)
            de.bind("<FocusOut>", lambda e, v=dv, idx=i: self._set_step_delay(idx, v))
            lbl(row, "ms", size=10, color=t["subtext"]).grid(row=0, column=5, padx=(0, 8))
            btn(row, "✕", lambda idx=i: self._del_seq_step(idx),
                color="#2a0a0a", width=32, height=30).grid(row=0, column=6, padx=(0, 10))

    # ── BINDINGS TAB ───────────────────────────────────────────────────────
    def _build_bindings_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        lbl(hdr, "🔑  Hotkeys", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "Click SET and press any key or mouse button to assign it.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        keys_card = sf(wrap, alpha=145)
        keys_card.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 8))
        keys_card.grid_columnconfigure((0,1,2,3,4,5), weight=1)

        bindings = [
            ("start_stop",  "▶ Start / Stop",  "f1"),
            ("emergency",   "🛑 Emergency",     "f12"),
            ("toggle_spam", "🗡 Spam on/off",   "f2"),
            ("toggle_seq",  "⚡ Seq on/off",    "f3"),
            ("cps_up",      "⬆ CPS +5",         "f5"),
            ("cps_down",    "⬇ CPS −5",         "f6"),
        ]
        for col, (hk_key, desc, default) in enumerate(bindings):
            f = ctk.CTkFrame(keys_card, fg_color="transparent")
            f.grid(row=0, column=col, padx=10, pady=16, sticky="nsew")
            lbl(f, desc, size=10, bold=True, color=t["text"]).pack(anchor="w")
            v = ctk.StringVar(value=engine.profile["hotkeys"].get(hk_key, default))
            disp = lbl(f, v.get().upper(), size=15, bold=True, color=t["accent"])
            disp.pack(anchor="w", pady=(8, 8))
            btn(f, "Set",
                lambda var=v, lab=disp, key=hk_key: self._start_hotkey_capture(key, var, lab),
                width=72, height=28).pack(anchor="w")
            lbl(f, f"default: {default}", size=9, color=t["subtext"]).pack(anchor="w", pady=(4, 0))

        # Mode selector
        mode_card = sf(wrap, alpha=140)
        mode_card.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))
        mode_card.grid_columnconfigure((0, 1), weight=1)

        lbl(mode_card, "⚙  How does the Start/Stop key work?", size=13, bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8))

        current_mode = engine.profile["hotkeys"].get("hotkey_mode", "toggle")
        self._hotkey_mode_var = ctk.StringVar(value=current_mode)

        def _set_mode(m):
            engine.profile["hotkeys"]["hotkey_mode"] = m
            self._hotkey_mode_var.set(m)
            engine.start_hotkeys()

        for col, (mode, title, color, lines) in enumerate([
            ("toggle", "Toggle",
             t["text"], ["Press once → macro starts", "Press again → macro stops"]),
            ("hold",   "Hold to run",
             t["live"], ["Hold the key → macro runs", "Release → macro stops immediately",
                         "Key won't type anything in-game"]),
        ]):
            mf = ctk.CTkFrame(mode_card, fg_color="transparent")
            mf.grid(row=1, column=col, padx=16, pady=(0, 16), sticky="nsew")
            ctk.CTkRadioButton(mf, text=title, variable=self._hotkey_mode_var, value=mode,
                               command=lambda m=mode: _set_mode(m),
                               font=ctk.CTkFont("Segoe UI", 13, weight="bold"),
                               text_color=color,
                               fg_color=t["accent"] if mode == "toggle" else t["live_dim"],
                               ).pack(anchor="w")
            for line in lines:
                lbl(mf, line, size=10, color=t["subtext"]).pack(anchor="w", pady=2)

        lbl(wrap, "ℹ  Hotkeys work even when Roblox is not the active window.",
            size=10, color=t["subtext"]).grid(row=3, column=0, sticky="w", padx=16, pady=(0, 12))

    # ── SAFETY TAB ────────────────────────────────────────────────────────
    def _build_safety_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        lbl(hdr, "🛡  Safety & Testing", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "Control when and how the macro is allowed to run.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        inner = sf(wrap, alpha=145)
        inner.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 8))
        inner.grid_columnconfigure(0, weight=1)

        rv = ctk.BooleanVar(value=engine.profile["safety"]["roblox_only"])
        tv = ctk.BooleanVar(value=engine.profile["safety"]["test_mode"])
        dv = ctk.BooleanVar(value=engine.profile["safety"].get("discord_rpc", True))

        def _sw(parent, text, subtext, var, cmd, row, pc=None):
            """Helper: switch + description label."""
            fr = ctk.CTkFrame(parent, fg_color="transparent")
            fr.grid(row=row, column=0, sticky="ew", padx=14, pady=(12, 0))
            fr.grid_columnconfigure(1, weight=1)
            kw = {"progress_color": pc} if pc else {}
            ctk.CTkSwitch(fr, text=text, variable=var, command=cmd,
                          font=ctk.CTkFont("Segoe UI", 12), **kw).grid(row=0, column=0, sticky="w")
            if subtext:
                lbl(fr, subtext, size=9, color=t["subtext"]).grid(row=1, column=0, sticky="w", padx=2, pady=(2, 0))

        _sw(inner, "Only run when Roblox is the active window",
            "Macro pauses automatically if you alt-tab away.",
            rv, lambda: self._set_safety("roblox_only", rv.get()), row=0)
        _sw(inner, "Test mode  (run in any window)",
            "Useful for testing — try it in Notepad before Roblox.",
            tv, lambda: self._set_safety("test_mode", tv.get()), row=1)

        ctk.CTkFrame(inner, height=1, fg_color=t["border"]).grid(
            row=2, column=0, sticky="ew", padx=14, pady=(14, 0))

        _sw(inner, "Show on Discord (Rich Presence)",
            "Displays what you're doing in your Discord profile.",
            dv, lambda: self._toggle_discord_rpc(dv.get()), row=3, pc="#5865F2")

        lbl(inner, "", size=6).grid(row=4, column=0)  # spacer

        # ── Extra options card ──
        extra = sf(wrap, alpha=145)
        extra.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        extra.grid_columnconfigure(0, weight=1)

        lbl(extra, "⚙  Extra Options", size=13, bold=True).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        # Countdown
        cd_row = ctk.CTkFrame(extra, fg_color="transparent")
        cd_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        cd_row.grid_columnconfigure(2, weight=1)
        self._countdown_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(cd_row, text="Countdown before start",
                      variable=self._countdown_var,
                      font=ctk.CTkFont("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
        lbl(cd_row, "  seconds:", size=11, color=t["subtext"]).grid(row=0, column=1, padx=(16, 4))
        self._countdown_secs = ctk.CTkEntry(cd_row, width=50, height=28)
        self._countdown_secs.insert(0, "3")
        self._countdown_secs.grid(row=0, column=2, sticky="w")
        self._countdown_lbl = lbl(cd_row, "", size=22, bold=True, color=t["warning"])
        self._countdown_lbl.grid(row=0, column=3, padx=(16, 0))

        # Sound feedback
        snd_row = ctk.CTkFrame(extra, fg_color="transparent")
        snd_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        self._sound_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(snd_row, text="Sound feedback (beep on start/stop)",
                      variable=self._sound_var,
                      font=ctk.CTkFont("Segoe UI", 12)).pack(side="left")

        # CPU affinity
        aff_row = ctk.CTkFrame(extra, fg_color="transparent")
        aff_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 8))
        self._affinity_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(aff_row, text="Pin macro to last CPU core  (reduces jitter)",
                      variable=self._affinity_var,
                      font=ctk.CTkFont("Segoe UI", 12)).pack(side="left")

        # Session log
        log_row = ctk.CTkFrame(extra, fg_color="transparent")
        log_row.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 12))
        self._log_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(log_row, text="Save session log after each session",
                      variable=self._log_var,
                      font=ctk.CTkFont("Segoe UI", 12)).pack(side="left", padx=(0, 16))
        btn(log_row, "📂 Open logs folder", self._open_logs_folder,
            color=t["accent2"], width=150, height=28).pack(side="left")

    # ── STATS TAB ─────────────────────────────────────────────────────────
    def _reset_stats(self):
        stats.session_clicks = 0
        stats.session_start  = time.time() if (engine.spam_active or engine.seq_active) else None

    def _on_status(self, what, state):
        t = current_theme
        on_c, off_c = t["live"], t["subtext"]
        if what in ("spam", "all"):
            r = state == "running"
            self.spam_ind.configure(text=f"● Spam: {'ON' if r else 'OFF'}",
                                    text_color=on_c if r else off_c)
            self.master_btn.configure(
                text="⏹  STOP  (F1)" if engine.running else "▶  START  (F1)",
                fg_color=t["accent"]  if engine.running else t["success"],
                hover_color="#a93226" if engine.running else "#1e8449",
                text_color="#fff")
        if what in ("seq", "all"):
            r = state == "running"
            self.seq_ind.configure(text=f"● Seq: {'ON' if r else 'OFF'}",
                                   text_color=on_c if r else off_c)
        if state == "emergency_stop":
            self.master_btn.configure(text="▶  START  (F1)",
                                      fg_color=t["success"], hover_color="#1e8449",
                                      text_color="#fff")
        if what == "cps_change":
            try: self.quick_cps_lbl.configure(text=f"{state:.1f}")
            except Exception: pass
            if "click_spam" in self._cps_labels:
                self._cps_labels["click_spam"].configure(text=f"{state:.1f}")
            try: self.stat_config_cps.configure(text=f"{state:.1f}")
            except Exception: pass

    def _poll(self):
        try:
            t = current_theme
            if engine.profile["safety"].get("test_mode"):
                self.roblox_ind.configure(text="● Test: ON", text_color=t["warning"])
            elif WIN32_AVAILABLE:
                f = engine._focused()
                self.roblox_ind.configure(
                    text="● Roblox: active" if f else "● Roblox: not focused",
                    text_color=t["live"] if f else t["subtext"])
            cps_val = stats.live_cps()
            self.live_cps_ind.configure(
                text=f"⚡ Live CPS: {cps_val:.1f}",
                text_color=t["live"] if cps_val > 0 else t["subtext"])
            self.stat_live_cps.configure(text=f"{cps_val:.1f}")
            self.stat_session.configure(text=str(stats.session_clicks))
            self.stat_total.configure(text=str(stats.total_clicks))
            self.stat_uptime.configure(text=stats.uptime())
            self.stat_config_cps.configure(text=f"{engine.profile['macros']['click_spam']['cps']:.1f}")
        except Exception:
            pass  # widgets podem estar destruídos durante o fecho
        self.after(200, self._poll)

    # ── Helpers ────────────────────────────────────────────────────────────
    def _validate_float_input(self, value):
        if value in ("", ".", ","): return True
        try: float(value.replace(",", ".")); return True
        except Exception: return False

    def _set_cps_entry(self, mk, var, lbl_widget):
        try:
            cps = max(0.1, float(var.get().strip().replace(",", ".")))
            engine.profile["macros"][mk]["cps"] = cps
            lbl_widget.configure(text=f"{cps:.1f}")
            var.set(f"{cps:.1f}")
            if mk == "click_spam":
                try: self.quick_cps_lbl.configure(text=f"{cps:.1f}")
                except Exception: pass
        except Exception:
            messagebox.showwarning("Invalid CPS", "Enter a valid number, e.g. 12.5")

    def _set_cps_preset(self, mk, cps, var, label):
        var.set(f"{float(cps):.1f}")
        label.configure(text=f"{float(cps):.1f}")
        engine.profile["macros"][mk]["cps"] = float(cps)
        if mk == "click_spam":
            try: self.quick_cps_lbl.configure(text=f"{float(cps):.1f}")
            except Exception: pass

    def _set_hold_mode(self, mk, var):
        engine.profile["macros"][mk]["hold_mode"] = bool(var.get())

    def _set_humanize(self, mk, var):
        engine.profile["macros"][mk]["humanize"] = bool(var.get())

    def _slider_cb(self, mk, field, val, lbl_widget):
        v = int(float(val))
        engine.profile["macros"][mk][field] = v
        lbl_widget.configure(text=f"{v} ms")

    def _set_macro_enabled(self, mk, var):
        engine.profile["macros"][mk]["enabled"] = bool(var.get())

    def _set_int(self, mk, field, var):
        try: engine.profile["macros"][mk][field] = int(var.get())
        except Exception: pass

    def _set_safety(self, k, val):
        engine.profile["safety"][k] = val

    def _toggle_discord_rpc(self, enabled: bool):
        engine.profile["safety"]["discord_rpc"] = enabled
        threading.Thread(target=discord_rpc.enable, args=(enabled,), daemon=True).start()

    def _open_logs_folder(self):
        import subprocess
        log_dir = PROFILE_DIR.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        try:
            subprocess.Popen(["explorer", str(log_dir)])
        except Exception:
            pass

    def _toggle_master_ui(self):
        """START/STOP with optional countdown, sound, affinity, and log."""
        if engine.running:
            self._do_stop_macro()
        else:
            use_cd = getattr(self, "_countdown_var", None) and self._countdown_var.get()
            if use_cd:
                try:
                    secs = int(self._countdown_secs.get())
                except Exception:
                    secs = 3
                def _tick(n):
                    self.after(0, lambda v=n: self._countdown_lbl.configure(text=str(v)))
                def _go():
                    self.after(0, lambda: self._countdown_lbl.configure(text=""))
                    self._do_start_macro()
                engine.start_with_countdown(secs, on_tick=_tick, on_start=_go)
            else:
                self._do_start_macro()

    def _do_start_macro(self):
        """Actually starts the macro — called directly or after countdown."""
        if getattr(self, "_sound_var", None) and self._sound_var.get():
            threading.Thread(target=lambda: engine._beep(880, 80), daemon=True).start()
        if getattr(self, "_affinity_var", None) and self._affinity_var.get():
            threading.Thread(target=engine._set_cpu_affinity, daemon=True).start()
        engine.running = True
        engine.start_spam()
        engine.start_seq()

    def _do_stop_macro(self):
        """Stops the macro and optionally writes log."""
        engine.stop_spam()
        engine.stop_seq()
        engine.running = False
        if getattr(self, "_sound_var", None) and self._sound_var.get():
            threading.Thread(target=lambda: engine._beep(440, 80), daemon=True).start()
        if getattr(self, "_log_var", None) and self._log_var.get():
            threading.Thread(target=engine._write_session_log, daemon=True).start()

    def _set_seq_opt(self, k, val):
        engine.profile["macros"]["sequence"][k] = val

    def _add_seq_step(self):
        engine.profile["macros"]["sequence"]["steps"].append({"key": "f", "delay_ms": 100})
        self._refresh_seq_ui()

    def _del_seq_step(self, idx):
        s = engine.profile["macros"]["sequence"]["steps"]
        if len(s) > 1: s.pop(idx)
        self._refresh_seq_ui()

    def _clear_seq(self):
        engine.profile["macros"]["sequence"]["steps"] = [{"key": "f", "delay_ms": 100}]
        self._refresh_seq_ui()

    def _set_step_delay(self, idx, var):
        try: engine.profile["macros"]["sequence"]["steps"][idx]["delay_ms"] = int(var.get())
        except Exception: pass

    def _save_profile(self):
        name = self.profile_var.get().strip() or "Default"
        try:
            engine.save_profile(name)
            self.profile_menu.configure(values=engine.list_profiles())
            messagebox.showinfo("Saved", f"Profile '{name}' saved successfully!")
        except Exception as exc:
            messagebox.showerror("Save error", f"Could not save profile '{name}':\n{exc}")

    def _new_profile(self):
        d = ctk.CTkInputDialog(text="New profile name:", title="New Profile")
        name = d.get_input()
        if not name: return
        engine.new_profile(name)
        self.profile_var.set(name)
        self._save_profile()

    def _load_profile_by_name(self, name):
        if engine.load_profile(name):
            # Reinicia os hotkeys com as keybinds do novo perfil
            engine.start_hotkeys()
            # Atualiza o label de CPS rápido
            try:
                cps = engine.profile["macros"]["click_spam"]["cps"]
                self.quick_cps_lbl.configure(text=f"{cps:.1f}")
            except Exception:
                pass
            messagebox.showinfo("Loaded", f"Profile '{name}' loaded!")
        else:
            messagebox.showwarning("Error", f"Could not load profile '{name}'.")


    # ── RECORDER TAB ───────────────────────────────────────────────────────
    def _build_recorder_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        lbl(hdr, "⏺  Macro Recorder", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "Record your keypresses in real-time — the timing is captured automatically.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        ctrl = ctk.CTkFrame(wrap, fg_color="transparent")
        ctrl.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        ctrl.grid_columnconfigure(3, weight=1)

        self._rec_status_lbl = lbl(ctrl, "● IDLE", size=13, bold=True, color=t["subtext"])
        self._rec_status_lbl.grid(row=0, column=0, padx=(0, 16))

        self._rec_btn = btn(ctrl, "⏺  Start Recording", self._toggle_recording,
                            color=t["accent"], width=160, height=36)
        self._rec_btn.grid(row=0, column=1, padx=(0, 8))

        btn(ctrl, "💾  Save to Sequence", self._save_recording_to_seq,
            color=t["success"], width=160, height=36).grid(row=0, column=2, padx=(0, 8))

        btn(ctrl, "🗑  Clear", self._clear_recording,
            color=t["accent2"], width=80, height=36).grid(row=0, column=3, sticky="w")

        self._rec_scroll = ctk.CTkScrollableFrame(wrap, fg_color="transparent")
        self._rec_scroll.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._rec_scroll.grid_columnconfigure(0, weight=1)

        lbl(wrap, "ℹ  Start recording, do your actions in-game, then click Stop. Save to Sequence to use it.",
            size=9, color=t["subtext"]).grid(row=3, column=0, sticky="w", padx=16, pady=(0, 8))

    def _toggle_recording(self):
        t = current_theme
        if recorder.recording:
            recorder.stop()
            self._rec_btn.configure(text="⏺  Start Recording", fg_color=t["accent"])
            self._rec_status_lbl.configure(text="● IDLE", text_color=t["subtext"])
            self._refresh_recording_ui()
        else:
            recorder.start()
            self._rec_btn.configure(text="⏹  Stop Recording", fg_color="#8b0000")
            self._rec_status_lbl.configure(text="● RECORDING", text_color="#ff4444")
            # Poll to update step count while recording
            self._poll_recorder()

    def _poll_recorder(self):
        if not recorder.recording:
            return
        steps = recorder.get_steps()
        # Update count label
        try:
            self._rec_status_lbl.configure(text=f"● RECORDING  ({len(steps)} steps)")
        except Exception:
            pass
        self.after(200, self._poll_recorder)

    def _refresh_recording_ui(self):
        for w in self._rec_scroll.winfo_children():
            w.destroy()
        t = current_theme
        steps = recorder.get_steps()
        if not steps:
            lbl(self._rec_scroll, "No steps recorded yet. Click Start Recording and press some keys.",
                size=11, color=t["subtext"]).grid(row=0, column=0, padx=16, pady=24)
            return
        for i, step in enumerate(steps):
            row = sf(self._rec_scroll, alpha=130)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(2, weight=1)
            lbl(row, f"#{i+1}", size=11, color=t["subtext"]).grid(row=0, column=0, padx=12, pady=8)
            lbl(row, step["key"].upper(), size=14, bold=True, color=t["accent"]).grid(row=0, column=1, padx=12)
            lbl(row, f"then wait {step['delay_ms']} ms", size=10, color=t["subtext"]).grid(row=0, column=2, sticky="w")

    def _save_recording_to_seq(self):
        steps = recorder.get_steps()
        if not steps:
            messagebox.showwarning("Recorder", "Nothing recorded yet!")
            return
        engine.profile["macros"]["sequence"]["steps"] = steps
        engine.profile["macros"]["sequence"]["enabled"] = True
        self._refresh_seq_ui()
        messagebox.showinfo("Recorder", f"{len(steps)} steps saved to Sequence tab!")
        self._switch_tab("seq")

    def _clear_recording(self):
        recorder.stop()
        recorder._steps = []
        t = current_theme
        self._rec_btn.configure(text="⏺  Start Recording", fg_color=t["accent"])
        self._rec_status_lbl.configure(text="● IDLE", text_color=t["subtext"])
        self._refresh_recording_ui()

    # ── AUTO-PROFILE TAB ───────────────────────────────────────────────────
    def _build_autopro_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        lbl(hdr, "🪟  Auto-Profile by Window", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "Automatically load a profile when a specific window becomes active.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        ctrl = ctk.CTkFrame(wrap, fg_color="transparent")
        ctrl.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        self._watcher_var = ctk.BooleanVar(value=False)
        self._watcher_status = lbl(ctrl, "Auto-switch: OFF", size=12, color=t["subtext"])
        self._watcher_status.pack(side="left", padx=(0, 12))
        ctk.CTkSwitch(ctrl, text="Enable", variable=self._watcher_var,
                      command=self._toggle_watcher,
                      progress_color=t["success"]).pack(side="left")

        # Rules list
        self._rules_frame = ctk.CTkScrollableFrame(wrap, fg_color="transparent")
        self._rules_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
        self._rules_frame.grid_columnconfigure(0, weight=1)

        self._autopro_rules = []   # list of (keyword_var, profile_var)
        self._refresh_rules_ui()

        add_row = ctk.CTkFrame(wrap, fg_color="transparent")
        add_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 4))
        btn(add_row, "+ Add Rule", self._add_autopro_rule, width=120, height=32).pack(side="left", padx=(0, 8))
        btn(add_row, "Apply Rules", self._apply_autopro_rules, color=t["success"], width=120, height=32).pack(side="left")

        lbl(wrap, "ℹ  Keyword is matched against the window title (case-insensitive). Example: 'Roblox' → 'BladeBall'",
            size=9, color=t["subtext"]).grid(row=4, column=0, sticky="w", padx=16, pady=(0, 8))

        # Seed with a default rule
        if not self._autopro_rules:
            self._add_autopro_rule(keyword="Roblox", profile="Default")

    def _refresh_rules_ui(self):
        for w in self._rules_frame.winfo_children():
            w.destroy()
        t = current_theme
        lbl(self._rules_frame, "Window keyword", size=9, color=t["subtext"]).grid(row=0, column=0, padx=8, sticky="w")
        lbl(self._rules_frame, "Load profile", size=9, color=t["subtext"]).grid(row=0, column=1, padx=8, sticky="w")
        for i, (kv, pv) in enumerate(self._autopro_rules):
            r = i + 1
            ctk.CTkEntry(self._rules_frame, textvariable=kv, width=200, height=30
                         ).grid(row=r, column=0, padx=8, pady=4, sticky="ew")
            ctk.CTkOptionMenu(self._rules_frame, variable=pv,
                              values=engine.list_profiles(),
                              width=160, height=30
                              ).grid(row=r, column=1, padx=8, pady=4)
            btn(self._rules_frame, "✕", lambda idx=i: self._del_autopro_rule(idx),
                color="#2a0a0a", width=32, height=30).grid(row=r, column=2, padx=4)

    def _add_autopro_rule(self, keyword="", profile="Default"):
        kv = ctk.StringVar(value=keyword)
        pv = ctk.StringVar(value=profile)
        self._autopro_rules.append((kv, pv))
        self._refresh_rules_ui()

    def _del_autopro_rule(self, idx):
        if 0 <= idx < len(self._autopro_rules):
            self._autopro_rules.pop(idx)
        self._refresh_rules_ui()

    def _apply_autopro_rules(self):
        rules = {kv.get(): pv.get() for kv, pv in self._autopro_rules if kv.get().strip()}
        watcher.set_rules(rules)
        messagebox.showinfo("Auto-Profile", f"{len(rules)} rule(s) applied.")

    def _toggle_watcher(self):
        t = current_theme
        if self._watcher_var.get():
            self._apply_autopro_rules()
            watcher.on_switch = lambda name: self.after(0, lambda n=name: (
                self.profile_var.set(n),
                messagebox.showinfo("Auto-Profile", f"Switched to profile: {n}")
            ))
            watcher.start()
            self._watcher_status.configure(text="Auto-switch: ON", text_color=t["live"])
        else:
            watcher.stop()
            self._watcher_status.configure(text="Auto-switch: OFF", text_color=t["subtext"])

    # ── STATS TAB (override with CPS graph) ────────────────────────────────
    def _build_stats_tab(self, parent):
        t = current_theme
        wrap = sf(parent, alpha=110)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure((0, 1, 2), weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        hdr = ctk.CTkFrame(wrap, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 4))
        lbl(hdr, "📊  Statistics", size=18, bold=True).grid(row=0, column=0, sticky="w")
        lbl(hdr, "Real-time stats for the current session.",
            size=10, color=t["subtext"]).grid(row=1, column=0, sticky="w")

        def stat_card(col, title, attr, color=None):
            c = sf(wrap, alpha=155)
            c.grid(row=1, column=col, padx=6, pady=8, sticky="nsew")
            lbl(c, title, size=10, color=t["subtext"]).pack(pady=(14, 2), padx=16)
            val = lbl(c, "0", size=28, bold=True, color=color or t["live"])
            val.pack(pady=(0, 4), padx=16)
            setattr(self, attr, val)

        stat_card(0, "⚡ Live CPS",        "stat_live_cps")
        stat_card(1, "🏆 Peak CPS",        "stat_peak_cps", color=t["warning"])
        stat_card(2, "🖱 Clicks (session)", "stat_session")

        r2 = ctk.CTkFrame(wrap, fg_color="transparent")
        r2.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=6, pady=(0, 4))
        r2.grid_columnconfigure(0, weight=1)
        r2.grid_rowconfigure(0, weight=1)

        # CPS graph canvas
        graph_card = sf(r2, alpha=145)
        graph_card.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        graph_card.grid_rowconfigure(1, weight=1)
        graph_card.grid_columnconfigure(0, weight=1)
        lbl(graph_card, "⚡ CPS over time (last 30s)", size=10, color=t["subtext"]
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        import tkinter as _tk
        self._cps_canvas = _tk.Canvas(graph_card, bg="#0d0d14", highlightthickness=0, height=120)
        self._cps_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        bottom = ctk.CTkFrame(wrap, fg_color="transparent")
        bottom.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 4))
        bottom.grid_columnconfigure((0, 1, 2), weight=1)

        c_up = sf(bottom, alpha=145)
        c_up.grid(row=0, column=0, padx=6, sticky="nsew")
        lbl(c_up, "⏱ Uptime", size=10, color=t["subtext"]).pack(pady=(12, 2), padx=16)
        self.stat_uptime = lbl(c_up, "00:00", size=24, bold=True, color=t["live"])
        self.stat_uptime.pack(pady=(0, 12), padx=16)

        c_tot = sf(bottom, alpha=145)
        c_tot.grid(row=0, column=1, padx=6, sticky="nsew")
        lbl(c_tot, "🌍 Total Clicks", size=10, color=t["subtext"]).pack(pady=(12, 2), padx=16)
        self.stat_total = lbl(c_tot, "0", size=24, bold=True, color=t["accent"])
        self.stat_total.pack(pady=(0, 12), padx=16)

        c_cfg = sf(bottom, alpha=145)
        c_cfg.grid(row=0, column=2, padx=6, sticky="nsew")
        lbl(c_cfg, "🎯 Target CPS", size=10, color=t["subtext"]).pack(pady=(12, 2), padx=16)
        self.stat_config_cps = lbl(c_cfg, f"{engine.profile['macros']['click_spam']['cps']:.1f}",
                                   size=24, bold=True, color=t["accent"])
        self.stat_config_cps.pack(pady=(0, 12), padx=16)

        btn(wrap, "🔄 Reset Session", self._reset_stats, width=160, color=t["accent2"]
            ).grid(row=4, column=0, columnspan=3, pady=(0, 12))

        self._draw_cps_graph()

    def _draw_cps_graph(self):
        try:
            canvas = self._cps_canvas
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 20 or h < 20:
                self.after(300, self._draw_cps_graph)
                return
            canvas.delete("all")
            history = stats.cps_history_snapshot(30)
            t = current_theme
            # Grid lines
            max_cps = max((c for _, c in history), default=10.0)
            max_cps = max(max_cps, 10.0)
            for i in range(5):
                y = int(h * i / 4)
                canvas.create_line(0, y, w, y, fill="#1a1a24", width=1)
                cps_label = f"{max_cps * (1 - i/4):.0f}"
                canvas.create_text(4, y + 2, text=cps_label, fill="#444460", font=("Segoe UI", 7), anchor="nw")
            # Plot
            if len(history) >= 2:
                pts = []
                for secs_ago, cps in history:
                    x = w - int((secs_ago / 30) * w)
                    y = h - int((cps / max_cps) * (h - 4))
                    pts.append((x, y))
                pts.sort(key=lambda p: p[0])
                # Fill area
                poly_pts = [(pts[0][0], h)] + pts + [(pts[-1][0], h)]
                canvas.create_polygon(poly_pts, fill="#1a0a0a", outline="")
                # Line
                for i in range(len(pts) - 1):
                    canvas.create_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                                       fill=t["accent"], width=2, smooth=True)
        except Exception:
            pass
        self.after(500, self._draw_cps_graph)

    # ── Overlay window ─────────────────────────────────────────────────────
    def _open_overlay(self):
        if getattr(self, "_overlay", None) and self._overlay.winfo_exists():
            self._overlay.lift()
            return
        self._overlay = OverlayWindow(self)

    # ── Tray icon ──────────────────────────────────────────────────────────
    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image as _PIL
            # Create a simple red icon
            img = _PIL.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill=(192, 57, 43, 255))
            draw.text((20, 18), "F", fill="white")

            menu = pystray.Menu(
                pystray.MenuItem("Show",  lambda: self.after(0, self.deiconify)),
                pystray.MenuItem("Overlay", lambda: self.after(0, self._open_overlay)),
                pystray.MenuItem("Quit",  lambda: self.after(0, self.destroy)),
            )
            icon = pystray.Icon("FranXX", img, "FranXX Macro", menu)
            self._tray_icon = icon
            threading.Thread(target=icon.run, daemon=True).start()

            def _on_close():
                self.withdraw()  # minimize to tray instead of closing
            self.protocol("WM_DELETE_WINDOW", _on_close)
        except ImportError:
            pass  # pystray not installed — skip tray


    # ── Extra sidebar buttons (overlay + tray) ─────────────────────────────
    # ── _reset_stats ───────────────────────────────────────────────────────
    # ── _poll override: add peak CPS ──────────────────────────────────────
# ── Floating Overlay Window ───────────────────────────────────────────────────
class OverlayWindow(ctk.CTkToplevel):
    """Small always-on-top HUD window showing live CPS and macro status."""

    def __init__(self, master):
        super().__init__(master)
        self.title("")
        self.geometry("200x90+20+20")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.85)
        self.overrideredirect(True)   # no title bar
        self.configure(fg_color="#0d0d14")

        t = current_theme

        # Drag support
        self._drag_x = 0
        self._drag_y = 0
        self.bind("<ButtonPress-1>",   self._drag_start)
        self.bind("<B1-Motion>",       self._drag_move)

        # Content
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 2))
        top.columnconfigure(0, weight=1)

        lbl(top, "FranXX  ⚡", size=10, bold=True, color=t["accent"]).grid(row=0, column=0, sticky="w")
        close_btn = ctk.CTkButton(top, text="✕", width=22, height=22,
                                  fg_color="transparent", hover_color="#3a0a0a",
                                  text_color=t["subtext"], font=ctk.CTkFont("Segoe UI", 10),
                                  command=self.destroy)
        close_btn.grid(row=0, column=1, sticky="e")

        self._cps_lbl = lbl(self, "0.0  CPS", size=26, bold=True, color=t["live"])
        self._cps_lbl.pack()

        self._status_lbl = lbl(self, "● OFF", size=10, color=t["subtext"])
        self._status_lbl.pack()

        # Opacity slider
        slider_row = ctk.CTkFrame(self, fg_color="transparent")
        slider_row.pack(fill="x", padx=8, pady=(2, 4))
        lbl(slider_row, "opacity", size=8, color="#444").pack(side="left")
        ctk.CTkSlider(slider_row, from_=0.3, to=1.0, number_of_steps=14,
                      width=110, height=14,
                      command=lambda v: self.attributes("-alpha", round(float(v), 2))
                      ).pack(side="left", padx=4)

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        x = self.winfo_x() + dx
        y = self.winfo_y() + dy
        self.geometry(f"+{x}+{y}")

    def update_stats(self, cps: float, running: bool):
        t = current_theme
        try:
            self._cps_lbl.configure(
                text=f"{cps:.1f}  CPS",
                text_color=t["live"] if cps > 0 else t["subtext"])
            self._status_lbl.configure(
                text="● ACTIVE" if running else "● OFF",
                text_color=t["live"] if running else t["subtext"])
        except Exception:
            pass


if __name__ == "__main__":
    app = BladeBallMacro()
    app.mainloop()
