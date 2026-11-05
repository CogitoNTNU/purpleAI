"""Siege — a pixel-art castle-defence view for the PurpleAI control panel.

The defender is a castle; each planted flag is a structure (gate / wall / tower
/ keep). The red attacker agents (SQL / XSS / SSTI, led by the Boss) besiege it,
speaking their live reasoning in bubbles. When an agent captures a flag through
its own vulnerability, the matching structure crumbles and the castle loses a
piece; capture them all and the castle falls. The defender fights back: every
blocked request fires a volley that knocks an attacker down.

The scene is driven entirely by calls from the control panel:
    set_state(agent, "running"|"queued"|"idle")
    say(agent, text)          # show reasoning in that agent's bubble
    capture(flag)             # a flag was scored -> crumble its structure
    leak(agent)               # a near miss (leaked, not scored)
    block()                   # defender blocked an attack (blue point)
    reset()                   # new engagement

`agent` is one of: "boss", "sql", "xss", "ssti".
"""
from __future__ import annotations

import math
import random
import time
import tkinter as tk
from tkinter import ttk

# --------------------------------------------------------------------------- #
# Pixel sprites                                                               #
# --------------------------------------------------------------------------- #
# Hooded attacker. C=cloak, S=skin, E=eye, B=body, K=boots, W=weapon.
_ATK_IDLE = [
    "..CCCC..",
    ".CCCCCC.",
    ".CSSSSC.",
    ".CSEESC.",
    ".CSSSSC.",
    ".CCCCCC.",
    "..CBBC..",
    ".CBBBBC.",
    "CBBBBBBC",
    ".BB..BB.",
    ".BB..BB.",
    ".KK..KK.",
]
_ATK_SWING = [
    "..CCCC.W",
    ".CCCCCCW",
    ".CSSSSCW",
    ".CSEESC.",
    ".CSSSSC.",
    ".CCCCCC.",
    "..CBBC..",
    ".CBBBBC.",
    "CBBBBBBC",
    ".BB..BB.",
    ".BB..BB.",
    ".KK..KK.",
]
# Boss has a crown (Y) and a cape.
_BOSS_IDLE = [
    ".Y.YY.Y.",
    ".YYYYYY.",
    "..CCCC..",
    ".CSSSSC.",
    ".CSEESC.",
    ".CSSSSC.",
    ".CCCCCC.",
    ".CBBBBC.",
    "CBBBBBBC",
    ".BB..BB.",
    ".BB..BB.",
    ".KK..KK.",
]


def _palette(cloak, body, extra=None):
    p = {
        "C": cloak, "B": body, "S": "#e8c9a0", "E": "#0d1117",
        "K": "#30363d", "W": "#c9d1d9", "Y": "#ffd33d",
    }
    if extra:
        p.update(extra)
    return p


def _make_sprite(pixmap, palette, scale):
    h = len(pixmap)
    w = max(len(r) for r in pixmap)
    img = tk.PhotoImage(width=w * scale, height=h * scale)
    for y, row in enumerate(pixmap):
        for x, ch in enumerate(row):
            col = palette.get(ch)
            if not col:
                continue
            x0, y0 = x * scale, y * scale
            img.put(col, to=(x0, y0, x0 + scale, y0 + scale))
    return img


# Which castle structure each flag maps to, in draw order.
_FLAG_STRUCT = {
    "FLAG{sql_login_bypass_success}": "gate",
    "FLAG{sql_union_injection_found}": "wall_l",
    "FLAG{reflected_xss}": "tower_l",
    "FLAG{stored_xss_dom}": "tower_r",
    "FLAG{server_side_template_injection}": "keep",
}
# Where each agent's attack bolts fly.
_AGENT_TARGET = {"sql": "gate", "xss": "tower_l", "ssti": "keep", "boss": "keep"}


class ArenaTab(ttk.Frame):
    def __init__(self, master, pal, flags):
        super().__init__(master)
        self.pal = pal
        self.canvas = tk.Canvas(self, bg=pal["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        S = 4  # sprite pixel scale
        self.sprites = {
            "sql": {"idle": _make_sprite(_ATK_IDLE, _palette("#f85149", "#a01f1a"), S),
                    "swing": _make_sprite(_ATK_SWING, _palette("#f85149", "#a01f1a"), S)},
            "xss": {"idle": _make_sprite(_ATK_IDLE, _palette("#ff9f1c", "#b35e00"), S),
                    "swing": _make_sprite(_ATK_SWING, _palette("#ff9f1c", "#b35e00"), S)},
            "ssti": {"idle": _make_sprite(_ATK_IDLE, _palette("#a371f7", "#6b3fb0"), S),
                     "swing": _make_sprite(_ATK_SWING, _palette("#a371f7", "#6b3fb0"), S)},
            "boss": {"idle": _make_sprite(_BOSS_IDLE, _palette("#d2a8ff", "#8957e5"), S),
                     "swing": _make_sprite(_BOSS_IDLE, _palette("#d2a8ff", "#8957e5"), S)},
        }

        self.agents = {}
        order = [("boss", "Boss"), ("sql", "SQLi"), ("xss", "XSS"), ("ssti", "SSTI")]
        for key, label in order:
            self.agents[key] = {
                "label": label, "state": "idle", "bubble": "", "bubble_t": 0.0,
                "phase": random.random() * 6.28, "knock": 0.0,
            }

        self.structures = {"gate", "wall_l", "wall_r", "tower_l", "tower_r", "keep"}
        self.flag_struct = dict(_FLAG_STRUCT)
        self.reachable = set(self.flag_struct.values())
        self.captured_structs: set[str] = set()
        self.flash: dict[str, float] = {}     # struct -> flash end time
        self.bolts: list[dict] = []           # attacker -> castle
        self.arrows: list[dict] = []          # castle -> attacker (defence)
        self.shield_t = 0.0
        self.won = False
        self.red = 0
        self.blue = 0

        self._rain = []
        self._last = time.time()
        self.after(60, self._tick)

    # -- public API -------------------------------------------------------- #
    def set_scores(self, red, blue):
        self.red, self.blue = red, blue

    def set_state(self, agent, state):
        a = self.agents.get(agent)
        if a:
            a["state"] = state

    def say(self, agent, text):
        a = self.agents.get(agent)
        if a and text:
            a["bubble"] = " ".join(str(text).split())[:120]
            a["bubble_t"] = time.time() + 9.0

    def capture(self, flag):
        st = self.flag_struct.get(flag)
        if st and st not in self.captured_structs:
            self.captured_structs.add(st)
            self.flash[st] = time.time() + 0.8
            if self.reachable and self.reachable <= self.captured_structs:
                self.won = True

    def leak(self, agent):
        a = self.agents.get(agent)
        if a:
            self._spawn_bolt(agent, leaked=True)

    def block(self):
        # Pick an active attacker to shove back.
        actives = [k for k, a in self.agents.items()
                   if k != "boss" and a["state"] in ("running", "queued")]
        target = random.choice(actives) if actives else random.choice(["sql", "xss", "ssti"])
        self.arrows.append({"target": target, "t": 0.0})
        self.shield_t = time.time() + 0.4
        a = self.agents.get(target)
        if a:
            a["knock"] = 1.0

    def reset(self):
        self.captured_structs.clear()
        self.flash.clear()
        self.bolts.clear()
        self.arrows.clear()
        self.won = False
        for a in self.agents.values():
            a["state"] = "idle"
            a["bubble"] = ""
            a["knock"] = 0.0

    # -- geometry ---------------------------------------------------------- #
    def _layout(self):
        w = self.canvas.winfo_width() or 900
        h = self.canvas.winfo_height() or 560
        # castle occupies the right ~45%
        cw = int(w * 0.40)
        cx = int(w * 0.56)
        gy = int(h * 0.86)                      # ground line
        return w, h, cx, cw, gy

    def _struct_rects(self, cx, cw, gy):
        """Return {name: (x0, y0, x1, y1)} for each castle piece."""
        u = cw / 10.0
        base = gy
        r = {}
        r["wall_l"] = (cx, base - 3.2 * u, cx + 3 * u, base)
        r["wall_r"] = (cx + 7 * u, base - 3.2 * u, cx + 10 * u, base)
        r["gate"] = (cx + 3.6 * u, base - 3.0 * u, cx + 6.4 * u, base)
        r["tower_l"] = (cx - 0.6 * u, base - 5.0 * u, cx + 2.2 * u, base)
        r["tower_r"] = (cx + 7.8 * u, base - 5.0 * u, cx + 10.6 * u, base)
        r["keep"] = (cx + 3.4 * u, base - 6.6 * u, cx + 6.6 * u, base - 2.6 * u)
        return {k: tuple(map(int, v)) for k, v in r.items()}

    def _agent_pos(self, key, w, h, gy):
        idx = {"boss": 0, "sql": 1, "xss": 2, "ssti": 3}[key]
        x = int(w * 0.07) + (idx % 2) * int(w * 0.11)
        y = gy - 56 - (idx // 2) * 120 if False else gy - 44 - idx * 0  # simple column
        # stack vertically on the left battlefield
        y = int(h * 0.20) + idx * int(h * 0.19)
        return x, y

    # -- animation --------------------------------------------------------- #
    def _spawn_bolt(self, agent, leaked=False):
        self.bolts.append({"agent": agent, "t": 0.0, "leaked": leaked})

    def _tick(self):
        now = time.time()
        dt = now - self._last
        self._last = now
        # occasionally spawn attack bolts for running agents
        for key, a in self.agents.items():
            if key != "boss" and a["state"] == "running" and random.random() < 0.08:
                self._spawn_bolt(key)
            if a["knock"] > 0:
                a["knock"] = max(0.0, a["knock"] - dt * 1.6)
        for b in self.bolts:
            b["t"] += dt * 1.4
        self.bolts = [b for b in self.bolts if b["t"] < 1.0]
        for ar in self.arrows:
            ar["t"] += dt * 1.6
        self.arrows = [ar for ar in self.arrows if ar["t"] < 1.0]
        try:
            self._render(now)
        except tk.TclError:
            return  # widget gone
        self.after(60, self._tick)

    def _render(self, now):
        c = self.canvas
        c.delete("all")
        w, h, cx, cw, gy = self._layout()
        pal = self.pal
        if w < 10:
            return

        # --- matrix rain backdrop ---
        if not self._rain or len(self._rain) != max(8, w // 22):
            self._rain = [{"x": i * 22 + 8, "y": random.randint(-h, h),
                           "s": random.uniform(40, 120)} for i in range(max(8, w // 22))]
        glyphs = "01<>{}[]#$%&/\\|=+*ｱｲｳｴｵﾊﾋﾌ"
        for col in self._rain:
            col["y"] += col["s"] * 0.06
            if col["y"] > h:
                col["y"] = random.randint(-80, 0)
            for k in range(5):
                yy = col["y"] - k * 16
                if 0 <= yy <= h:
                    shade = "#113311" if k else "#1f7a1f"
                    c.create_text(col["x"], yy, text=random.choice(glyphs),
                                  fill=shade, font=("Consolas", 10))

        # --- ground ---
        c.create_rectangle(0, gy, w, h, fill="#0a1a0a", width=0)
        c.create_line(0, gy, w, gy, fill="#18381a")

        # --- castle ---
        rects = self._struct_rects(cx, cw, gy)
        draw_order = ["tower_l", "tower_r", "wall_l", "wall_r", "keep", "gate"]
        for name in draw_order:
            x0, y0, x1, y1 = rects[name]
            broken = name in self.captured_structs
            flashing = self.flash.get(name, 0) > now
            self._draw_structure(name, x0, y0, x1, y1, broken, flashing)
        # defender shield shimmer
        if self.shield_t > now:
            c.create_arc(cx - 16, gy - 7.2 * (cw / 10.0), cx + cw + 16, gy + 40,
                         start=0, extent=180, style="arc", outline=pal["blue"], width=3)

        # --- attacker bolts (red) ---
        for b in self.bolts:
            self._draw_bolt(b, w, h, gy, rects)
        # --- defender arrows (blue) ---
        for ar in self.arrows:
            self._draw_arrow(ar, w, h, gy)

        # --- agents + bubbles ---
        for key, a in self.agents.items():
            self._draw_agent(key, a, now, w, h, gy)

        # --- HUD ---
        self._draw_hud(now, w, h, cx, cw, gy)

    def _draw_structure(self, name, x0, y0, x1, y1, broken, flashing):
        c = self.canvas
        pal = self.pal
        if broken:
            # rubble
            c.create_rectangle(x0, (y0 + y1) / 2, x1, y1, fill="#2b2b2b", width=0)
            for _ in range(6):
                rx = random.randint(int(x0), int(x1) - 4)
                ry = random.randint(int((y0 + y1) / 2), int(y1) - 3)
                c.create_rectangle(rx, ry, rx + 4, ry + 3, fill="#3a3a3a", width=0)
            c.create_text((x0 + x1) / 2, y1 - 8, text="💥", font=("Segoe UI", 12))
            return
        stone = "#6ea8d8" if flashing else "#3b6ea5"
        edge = "#8fc4ef" if flashing else "#28527a"
        c.create_rectangle(x0, y0, x1, y1, fill=stone, outline=edge, width=2)
        # crenellations
        step = max(6, int((x1 - x0) / 5))
        for xx in range(int(x0), int(x1) - 2, step * 2):
            c.create_rectangle(xx, y0 - 6, xx + step, y0, fill=stone, outline=edge)
        # archer on towers / keep
        if name in ("tower_l", "tower_r", "keep"):
            ax = (x0 + x1) / 2
            c.create_rectangle(ax - 3, y0 - 14, ax + 3, y0 - 6, fill=pal["blue"], width=0)
            c.create_oval(ax - 3, y0 - 20, ax + 3, y0 - 14, fill="#cfe6ff", width=0)
        if name == "gate":
            c.create_rectangle(x0 + 6, y0 + 8, x1 - 6, y1, fill="#24405e", outline=edge)
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="🛡", font=("Segoe UI", 12))

    def _draw_bolt(self, b, w, h, gy, rects):
        key = b["agent"]
        ax, ay = self._agent_pos(key, w, h, gy)
        tx0, ty0, tx1, ty1 = rects.get(_AGENT_TARGET.get(key, "gate"))
        tx, ty = (tx0 + tx1) / 2, (ty0 + ty1) / 2
        t = b["t"]
        x = ax + (tx - ax) * t
        y = ay + (ty - ay) * t - math.sin(t * math.pi) * 40
        col = "#8b949e" if b.get("leaked") else "#ff5a4f"
        self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=col, width=0)
        if b.get("leaked") and t > 0.85:
            self.canvas.create_text(x, y - 10, text="📄", font=("Segoe UI", 10))

    def _draw_arrow(self, ar, w, h, gy):
        key = ar["target"]
        ax, ay = self._agent_pos(key, w, h, gy)
        # arrow comes from the right (castle) to the agent
        sx, sy = w * 0.6, gy - 80
        t = ar["t"]
        x = sx + (ax - sx) * t
        y = sy + (ay - sy) * t
        self.canvas.create_line(x, y, x + 10, y - 3, fill=self.pal["blue"], width=2)

    def _draw_agent(self, key, a, now, w, h, gy):
        c = self.canvas
        pal = self.pal
        x, y = self._agent_pos(key, w, h, gy)
        running = a["state"] == "running"
        bob = math.sin(now * 4 + a["phase"]) * (4 if running else 2)
        knock = a["knock"] * 18
        img = self.sprites[key]["swing" if (running and int(now * 4) % 2 == 0) else "idle"]
        c.create_image(x - knock, y + bob, image=img, anchor="center")
        # nameplate + state dot
        col = {"running": pal["green"], "queued": pal["amber"]}.get(a["state"], pal["idle"])
        c.create_oval(x - 26, y + 26, x - 20, y + 32, fill=col, width=0)
        c.create_text(x - 14, y + 29, text=a["label"], anchor="w",
                      fill=pal["text"], font=("Segoe UI Semibold", 9))
        # speech bubble
        if a["bubble"] and a["bubble_t"] > now:
            self._draw_bubble(x + 24, y - 34, a["bubble"], key)

    def _draw_bubble(self, x, y, text, key):
        c = self.canvas
        pal = self.pal
        bw = 240
        c.create_rectangle(x, y, x + bw, y + 54, fill="#0c1622",
                           outline=pal["accent"], width=1)
        c.create_polygon(x, y + 40, x - 10, y + 48, x, y + 30,
                         fill="#0c1622", outline=pal["accent"])
        c.create_text(x + 8, y + 6, text=text, anchor="nw", width=bw - 16,
                      fill="#7ee787", font=("Consolas", 9))

    def _draw_hud(self, now, w, h, cx, cw, gy):
        c = self.canvas
        pal = self.pal
        total = len(self.reachable) or 1
        standing = total - len(self.captured_structs & self.reachable)
        # castle HP bar
        bx, by, bw = cx, 18, cw
        c.create_text(bx, by - 4, text="CASTLE", anchor="w",
                      fill=pal["blue"], font=("Segoe UI Semibold", 9))
        c.create_rectangle(bx + 56, by - 8, bx + bw, by + 6, outline=pal["border"], width=1)
        frac = standing / total
        c.create_rectangle(bx + 56, by - 8, bx + 56 + (bw - 56) * frac, by + 6,
                           fill=pal["blue"] if frac > 0.33 else pal["red"], width=0)
        # score line
        c.create_text(12, 16, text=f"🔴 {self.red}", anchor="w",
                      fill=pal["red"], font=("Segoe UI", 14, "bold"))
        c.create_text(12, 40, text=f"🔵 {self.blue}", anchor="w",
                      fill=pal["blue"], font=("Segoe UI", 14, "bold"))
        if self.won:
            c.create_rectangle(w / 2 - 170, h / 2 - 36, w / 2 + 170, h / 2 + 36,
                               fill="#1a0b0b", outline=pal["red"], width=3)
            c.create_text(w / 2, h / 2, text="⚔  THE CASTLE HAS FALLEN — RED WINS",
                          fill=pal["red"], font=("Segoe UI", 13, "bold"))
