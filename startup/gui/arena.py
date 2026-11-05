"""Siege — a top-down pixel map where red commanders besiege a walled town.

The defender is a walled town (grass, river, stone walls, red-roofed towers and
houses). Each planted flag is a building inside. The attacker agents are
**commanders** out on the field; while running they **send out little soldiers**
that march on the gate. When an agent captures a flag through its own
vulnerability the matching building burns down; take them all and the town is
overrun. The defender fights back: a blocked request cuts soldiers down.

Public API (called by the control panel):
    set_state(agent, "running"|"queued"|"idle")
    say(agent, text)      # reasoning bubble over the commander
    capture(flag)         # scored -> building burns
    leak(agent)           # a soldier bounces off (not scored)
    block()               # defender kills soldiers (blue point)
    reset()               # new engagement
    set_scores(red, blue)

`agent` is one of: "boss", "sql", "xss", "ssti".
"""
from __future__ import annotations

import math
import random
import time
import tkinter as tk
from tkinter import ttk

# Flag -> interior building id (draw order inside the town).
_FLAG_BUILDING = {
    "FLAG{sql_login_bypass_success}": "b_gate",
    "FLAG{sql_union_injection_found}": "b_sw",
    "FLAG{reflected_xss}": "b_nw",
    "FLAG{stored_xss_dom}": "b_ne",
    "FLAG{server_side_template_injection}": "keep",
}

_TEAM = {
    "boss": "#d2a8ff", "sql": "#f85149", "xss": "#ff9f1c", "ssti": "#a371f7",
}
_LABEL = {"boss": "Boss", "sql": "SQLi", "xss": "XSS", "ssti": "SSTI"}


class ArenaTab(ttk.Frame):
    def __init__(self, master, pal, flags):
        super().__init__(master)
        self.pal = pal
        self.canvas = tk.Canvas(self, bg="#5c9346", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.flag_building = dict(_FLAG_BUILDING)
        self.reachable = set(self.flag_building.values())
        self.captured: set[str] = set()
        self.flash: dict[str, float] = {}

        self.commanders = {}
        for i, key in enumerate(("boss", "sql", "xss", "ssti")):
            self.commanders[key] = {
                "label": _LABEL[key], "color": _TEAM[key], "state": "idle",
                "bubble": "", "bubble_t": 0.0, "spawn_cd": random.uniform(0.3, 1.0),
                "xf": 0.08 + (i % 2) * 0.12, "yf": 0.18 + i * 0.19,
                "phase": random.random() * 6.28,
            }
        self.soldiers: list[dict] = []
        self.sparks: list[dict] = []      # transient hit/arrow effects
        self.won = False
        self.red = 0
        self.blue = 0

        self._terrain = None
        self._tsize = (0, 0)
        self._last = time.time()
        self.after(60, self._tick)

    # -- public API -------------------------------------------------------- #
    def set_scores(self, red, blue):
        self.red, self.blue = red, blue

    def set_state(self, agent, state):
        c = self.commanders.get(agent)
        if c:
            c["state"] = state

    def say(self, agent, text):
        c = self.commanders.get(agent)
        if c and text:
            c["bubble"] = " ".join(str(text).split())[:120]
            c["bubble_t"] = time.time() + 9.0

    def capture(self, flag):
        b = self.flag_building.get(flag)
        if b and b not in self.captured:
            self.captured.add(b)
            self.flash[b] = time.time() + 1.2
            if self.reachable and self.reachable <= self.captured:
                self.won = True

    def leak(self, agent):
        c = self.commanders.get(agent)
        if c:
            self._spawn_soldier(agent, leaked=True)

    def block(self):
        live = [s for s in self.soldiers if s["alive"]]
        live.sort(key=lambda s: -s["x"])  # nearest the town first
        for s in live[:3]:
            s["alive"] = False
            self.sparks.append({"x": s["x"], "y": s["y"], "t": 0.0, "kind": "kill"})

    def reset(self):
        self.captured.clear()
        self.flash.clear()
        self.soldiers.clear()
        self.sparks.clear()
        self.won = False
        for c in self.commanders.values():
            c["state"] = "idle"
            c["bubble"] = ""

    # -- terrain (precomputed, stable across frames) ----------------------- #
    def _layout(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 50 or h < 50:
            return w, h  # not laid out yet; caller bails
        if (w, h) != self._tsize:
            self._tsize = (w, h)
            self._build_terrain(w, h)
        return w, h

    def _build_terrain(self, w, h):
        rnd = random.Random(1234)
        patches = [(rnd.randint(0, w), rnd.randint(0, h),
                    rnd.randint(14, 40), rnd.choice(["#558a42", "#6fab53", "#4f803c"]))
                   for _ in range(70)]
        # town compound on the right
        tx0, ty0 = int(w * 0.42), int(h * 0.14)
        tx1, ty1 = int(w * 0.90), int(h * 0.90)
        gate = (tx0, int((ty0 + ty1) / 2))
        # river meanders down the far-right background
        rv = [(int(w * 0.95 + math.sin(k / 3.0) * w * 0.03), int(h * k / 10))
              for k in range(11)]
        # trees scattered on the field (avoid the compound)
        trees = []
        for _ in range(26):
            x, y = rnd.randint(10, w - 10), rnd.randint(10, h - 10)
            if tx0 - 10 < x < tx1 + 10 and ty0 - 10 < y < ty1 + 10:
                continue
            trees.append((x, y))
        # interior buildings (fractions of the compound)
        def box(fx0, fy0, fx1, fy1):
            return (int(tx0 + (tx1 - tx0) * fx0), int(ty0 + (ty1 - ty0) * fy0),
                    int(tx0 + (tx1 - tx0) * fx1), int(ty0 + (ty1 - ty0) * fy1))
        buildings = {
            "keep":   box(0.40, 0.38, 0.62, 0.62),
            "b_nw":   box(0.14, 0.14, 0.34, 0.30),
            "b_ne":   box(0.66, 0.16, 0.86, 0.32),
            "b_sw":   box(0.16, 0.68, 0.36, 0.84),
            "b_gate": box(0.18, 0.42, 0.34, 0.58),
            "b_dec1": box(0.64, 0.64, 0.84, 0.80),
            "b_dec2": box(0.40, 0.70, 0.58, 0.86),
        }
        towers = [(tx0, ty0), (tx1, ty0), (tx0, ty1), (tx1, ty1)]
        self._terrain = {
            "patches": patches, "compound": (tx0, ty0, tx1, ty1), "gate": gate,
            "river": rv, "trees": trees, "buildings": buildings, "towers": towers,
        }

    # -- soldiers ---------------------------------------------------------- #
    def _cmd_pos(self, c, w, h):
        return c["xf"] * w, c["yf"] * h

    def _spawn_soldier(self, agent, leaked=False):
        if not self._terrain or len([s for s in self.soldiers if s["alive"]]) > 44:
            return
        w, h = self._tsize
        c = self.commanders[agent]
        cx, cy = self._cmd_pos(c, w, h)
        gx, gy = self._terrain["gate"] if self._terrain else (w * 0.42, h * 0.5)
        self.soldiers.append({
            "x": cx + random.uniform(-8, 8), "y": cy + random.uniform(-8, 8),
            "tx": gx + random.uniform(-10, 24), "ty": gy + random.uniform(-40, 40),
            "color": c["color"], "alive": True, "leaked": leaked,
            "phase": random.random() * 6.28,
        })

    def _tick(self):
        now = time.time()
        dt = min(0.1, now - self._last)
        self._last = now
        w, h = self._tsize or (900, 560)
        for key, c in self.commanders.items():
            if c["state"] == "running":
                c["spawn_cd"] -= dt
                if c["spawn_cd"] <= 0:
                    self._spawn_soldier(key)
                    c["spawn_cd"] = random.uniform(0.5, 1.1)
        for s in self.soldiers:
            if not s["alive"]:
                continue
            dx, dy = s["tx"] - s["x"], s["ty"] - s["y"]
            dist = math.hypot(dx, dy) or 1
            spd = 48 * dt
            if dist < 6:
                self.sparks.append({"x": s["x"], "y": s["y"], "t": 0.0,
                                    "kind": "leak" if s["leaked"] else "hit"})
                s["alive"] = False
            else:
                s["x"] += dx / dist * spd
                s["y"] += dy / dist * spd
        self.soldiers = [s for s in self.soldiers if s["alive"]]
        for sp in self.sparks:
            sp["t"] += dt * 2.2
        self.sparks = [sp for sp in self.sparks if sp["t"] < 1.0]
        try:
            self._render(now)
        except tk.TclError:
            return
        self.after(60, self._tick)

    # -- rendering --------------------------------------------------------- #
    def _render(self, now):
        c = self.canvas
        c.delete("all")
        w, h = self._layout()
        if w < 50 or h < 50 or not self._terrain:
            return
        T = self._terrain
        pal = self.pal

        # grass patches
        for (x, y, r, col) in T["patches"]:
            c.create_oval(x - r, y - r // 2, x + r, y + r // 2, fill=col, width=0)
        # river
        pts = T["river"]
        for i in range(len(pts) - 1):
            c.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                          fill="#4a90c2", width=14, capstyle="round")
            c.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                          fill="#6fb6e0", width=5, capstyle="round")
        # background trees
        for (x, y) in T["trees"]:
            self._tree(x, y)

        # town: ground, walls, towers, buildings
        tx0, ty0, tx1, ty1 = T["compound"]
        c.create_rectangle(tx0, ty0, tx1, ty1, fill="#9a9589", width=0)  # courtyard
        self._walls(tx0, ty0, tx1, ty1, T["gate"])
        for (bx, by) in T["towers"]:
            self._tower(bx, by)
        for name, (x0, y0, x1, y1) in T["buildings"].items():
            burning = self.flash.get(name, 0) > now
            down = name in self.captured
            self._house(x0, y0, x1, y1, down, burning)

        # soldiers
        for s in self.soldiers:
            self._soldier(s, now)
        # sparks / arrows
        for sp in self.sparks:
            self._spark(sp)

        # commanders + bubbles
        for key, cm in self.commanders.items():
            self._commander(key, cm, now, w, h)

        self._hud(now, w, h, T)

    def _tree(self, x, y):
        c = self.canvas
        c.create_rectangle(x - 1, y, x + 1, y + 4, fill="#6b4a2b", width=0)
        c.create_oval(x - 6, y - 10, x + 6, y + 2, fill="#2f6b34", width=0)
        c.create_oval(x - 4, y - 12, x + 4, y - 2, fill="#3f8a44", width=0)

    def _walls(self, x0, y0, x1, y1, gate):
        c = self.canvas
        wcol, edge = "#9a9a9a", "#6f6f6f"
        tkk = 8
        for (ax0, ay0, ax1, ay1) in [
            (x0, y0, x1, y0 + tkk), (x0, y1 - tkk, x1, y1),
            (x0, y0, x0 + tkk, y1), (x1 - tkk, y0, x1, y1)]:
            c.create_rectangle(ax0, ay0, ax1, ay1, fill=wcol, outline=edge)
        # crenellations along the top wall
        for xx in range(int(x0), int(x1), 16):
            c.create_rectangle(xx, y0 - 4, xx + 8, y0 + 2, fill=wcol, outline=edge)
        # gate opening on the left wall
        gx, gy = gate
        c.create_rectangle(x0 - 2, gy - 18, x0 + tkk + 2, gy + 18, fill="#5a4a33", outline=edge)
        c.create_text(x0 + 3, gy, text="🚪", font=("Segoe UI", 11))

    def _tower(self, x, y):
        c = self.canvas
        c.create_rectangle(x - 9, y - 9, x + 9, y + 9, fill="#b0b0b0", outline="#6f6f6f", width=2)
        c.create_polygon(x - 11, y - 7, x + 11, y - 7, x, y - 20, fill="#b0503f", outline="#7a3328")
        c.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#58a6ff", width=0)  # archer

    def _house(self, x0, y0, x1, y1, down, burning):
        c = self.canvas
        if down:
            c.create_rectangle(x0, y0, x1, y1, fill="#4a4a46", width=0)
            for _ in range(5):
                rx = random.randint(int(x0), int(x1) - 3)
                ry = random.randint(int(y0), int(y1) - 3)
                c.create_rectangle(rx, ry, rx + 3, ry + 3, fill="#5a5a55", width=0)
            return
        c.create_rectangle(x0, y0, x1, y1, fill="#c9b79a", outline="#8a7a5f")  # walls
        roof = "#c86a56" if burning else "#b0503f"
        c.create_rectangle(x0 + 2, y0 + 2, x1 - 2, (y0 + y1) / 2, fill=roof, outline="#7a3328")
        c.create_line(x0 + 2, (y0 + y1) / 2, x1 - 2, (y0 + y1) / 2, fill="#7a3328")
        if burning:
            for _ in range(4):
                fx = random.randint(int(x0), int(x1))
                fy = random.randint(int(y0) - 6, int(y0) + 4)
                c.create_text(fx, fy, text=random.choice(["🔥", "🔥"]), font=("Segoe UI", 10))

    def _soldier(self, s, now):
        c = self.canvas
        x, y = s["x"], s["y"]
        bob = math.sin(now * 8 + s["phase"]) * 1.2
        col = "#9aa0a6" if s["leaked"] else s["color"]
        c.create_oval(x - 3, y - 3 + bob, x + 3, y + 3 + bob, fill=col, width=0)
        c.create_oval(x - 1.5, y - 5 + bob, x + 1.5, y - 2 + bob, fill="#e8c9a0", width=0)

    def _spark(self, sp):
        c = self.canvas
        x, y, t = sp["x"], sp["y"], sp["t"]
        if sp["kind"] == "kill":
            c.create_text(x, y - t * 10, text="✖", fill="#58a6ff", font=("Segoe UI", 11))
        elif sp["kind"] == "leak":
            c.create_text(x, y - t * 8, text="📄", font=("Segoe UI", 9))
        else:
            r = 3 + t * 6
            c.create_oval(x - r, y - r, x + r, y + r, outline="#ffd33d", width=1)

    def _commander(self, key, cm, now, w, h):
        c = self.canvas
        pal = self.pal
        x, y = self._cmd_pos(cm, w, h)
        running = cm["state"] == "running"
        bob = math.sin(now * 4 + cm["phase"]) * (2 if running else 1)
        y += bob
        col = cm["color"]
        # body (top-down) + head + banner
        c.create_rectangle(x - 7, y - 7, x + 7, y + 9, fill=col, outline="#1b1f24", width=1)
        c.create_oval(x - 5, y - 11, x + 5, y - 1, fill="#e8c9a0", width=0)
        c.create_line(x + 8, y - 14, x + 8, y + 8, fill="#6b4a2b", width=2)
        c.create_polygon(x + 8, y - 14, x + 22, y - 11, x + 8, y - 6, fill=col, outline="#1b1f24")
        # state dot + name
        sc = {"running": pal["green"], "queued": pal["amber"]}.get(cm["state"], pal["idle"])
        c.create_oval(x - 16, y + 12, x - 10, y + 18, fill=sc, width=0)
        c.create_text(x - 7, y + 15, text=cm["label"], anchor="w",
                      fill="#101418", font=("Segoe UI Semibold", 9))
        if cm["bubble"] and cm["bubble_t"] > now:
            self._bubble(x + 24, y - 40, cm["bubble"])

    def _bubble(self, x, y, text):
        c = self.canvas
        pal = self.pal
        bw = 230
        c.create_rectangle(x, y, x + bw, y + 50, fill="#0c1622",
                           outline=pal["accent"], width=1)
        c.create_polygon(x, y + 38, x - 9, y + 46, x, y + 28,
                         fill="#0c1622", outline=pal["accent"])
        c.create_text(x + 7, y + 5, text=text, anchor="nw", width=bw - 14,
                      fill="#7ee787", font=("Consolas", 9))

    def _hud(self, now, w, h, T):
        c = self.canvas
        pal = self.pal
        total = len(self.reachable) or 1
        standing = total - len(self.captured & self.reachable)
        # panel
        c.create_rectangle(8, 8, 150, 86, fill="#0c1622", outline=pal["border"])
        c.create_text(18, 24, text=f"🔴 {self.red}", anchor="w",
                      fill=pal["red"], font=("Segoe UI", 14, "bold"))
        c.create_text(18, 48, text=f"🔵 {self.blue}", anchor="w",
                      fill=pal["blue"], font=("Segoe UI", 14, "bold"))
        frac = standing / total
        c.create_text(18, 70, text=f"town {standing}/{total}", anchor="w",
                      fill=pal["muted"], font=("Segoe UI", 9))
        c.create_rectangle(78, 64, 142, 74, outline=pal["border"])
        c.create_rectangle(78, 64, 78 + 64 * frac, 74,
                           fill=pal["blue"] if frac > 0.34 else pal["red"], width=0)
        if self.won:
            c.create_rectangle(w / 2 - 190, h / 2 - 32, w / 2 + 190, h / 2 + 32,
                               fill="#1a0b0b", outline=pal["red"], width=3)
            c.create_text(w / 2, h / 2, text="⚔  THE TOWN IS OVERRUN — RED WINS",
                          fill=pal["red"], font=("Segoe UI", 13, "bold"))
