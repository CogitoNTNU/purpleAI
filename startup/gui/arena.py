"""Siege — a top-down pixel battle using the Medieval_Pixel_Pack art.

The backdrop is the 3-stage siege map (army arrives -> siege -> ruins), which
advances as the attacker captures flags. Each agent is an elite **commander**
on the field who, while running, sends **foot soldiers** marching on the gate
and speaks its live reasoning in a bubble. The defender cuts soldiers down on a
blocked request.

Public API (called by the control panel):
    set_state(agent, "running"|"queued"|"idle")
    say(agent, text)
    capture(flag)   # a scored flag -> advance the siege / town HP
    leak(agent)     # a soldier bounces off (not scored)
    block()         # defender kills soldiers (blue point)
    reset()
    set_scores(red, blue)

`agent` is one of: "boss", "recon", "sql", "xss", "ssti", "xxe".
"""
from __future__ import annotations

import math
import os
import random
import sys
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

FRAME_W, FRAME_H = 40, 44

# agent -> (elite strip file, team color, label, field position fraction).
# The recon scout rides out FRONT (nearest the gate) — it maps the way in
# before the army commits.
_COMMANDERS = {
    "boss":  ("king_anim_strip_1x.png", "#d2a8ff", "Boss", (0.47, 0.90)),
    "recon": ("emerald_ninja_anim_strip_1x.png", "#2ec27e", "Recon", (0.47, 0.70)),
    "sql":   ("crimson_berserker_anim_strip_1x.png", "#f85149", "SQLi", (0.17, 0.80)),
    "xss":   ("ember_warden_anim_strip_1x.png", "#ff9f1c", "XSS", (0.32, 0.86)),
    "ssti":  ("void_battlemage_anim_strip_1x.png", "#a371f7", "SSTI", (0.62, 0.86)),
    "xxe":   ("frost_halberdier_anim_strip_1x.png", "#58d6c0", "XXE", (0.78, 0.80)),
    "ssrf":  ("templar_knight_anim_strip_1x.png", "#e3b341", "SSRF", (0.88, 0.88)),
}
# agent -> 48x48 portrait for the war-room chat
_PORTRAIT = {
    "boss": "king_portrait_1x.png",
    "recon": "emerald_ninja_portrait_1x.png",
    "sql": "crimson_berserker_portrait_1x.png",
    "xss": "ember_warden_portrait_1x.png",
    "ssti": "void_battlemage_portrait_1x.png",
    "xxe": "frost_halberdier_portrait_1x.png",
    "ssrf": "templar_knight_portrait_1x.png",
}
# agent -> foot soldier walk strip
_SOLDIER = {
    "recon": "green_shinobi_walk_strip_1x.png",
    "sql": "red_axeman_walk_strip_1x.png",
    "xss": "ember_torchbearer_walk_strip_1x.png",
    "ssti": "violet_acolyte_walk_strip_1x.png",
    "xxe": "frost_pikeman_walk_strip_1x.png",
    "ssrf": "templar_sergeant_walk_strip_1x.png",
    "boss": "red_axeman_walk_strip_1x.png",
}
_GATE = (0.47, 0.585)  # where the road meets the castle gate (map fraction)


def _asset(name):
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", "medieval", name)


class ArenaTab(ttk.Frame):
    def __init__(self, master, pal, flags):
        super().__init__(master)
        self.pal = pal

        self.canvas = tk.Canvas(self, bg="#3f7a34", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        # War-room chat on the right: a running feed of what the agents think.
        chat_frame = tk.Frame(self, width=330, bg=pal["panel"])
        chat_frame.pack(side="right", fill="y")
        chat_frame.pack_propagate(False)
        head = tk.Frame(chat_frame, bg=pal["panel"])
        head.pack(fill="x", pady=(8, 4))
        tk.Label(head, text="  💬  WAR ROOM", bg=pal["panel"], fg=pal["muted"],
                 font=("Segoe UI Semibold", 10), anchor="w").pack(side="left")
        tk.Button(head, text="⤓ Export", command=self._export_chat,
                  bg=pal["panel"], fg=pal["text"], activebackground=pal["log"],
                  activeforeground=pal["text"], relief="flat", borderwidth=0,
                  font=("Segoe UI", 8), cursor="hand2", padx=8).pack(side="right", padx=6)
        wrap = tk.Frame(chat_frame, bg=pal["panel"])
        wrap.pack(fill="both", expand=True)
        sb = tk.Scrollbar(wrap)
        sb.pack(side="right", fill="y")
        self.chat = tk.Text(wrap, bg=pal["log"], fg=pal["text"], wrap="word",
                            relief="flat", borderwidth=0, font=("Segoe UI", 9),
                            state="disabled", yscrollcommand=sb.set,
                            padx=8, pady=8, spacing1=2, spacing3=6)
        self.chat.pack(side="left", fill="both", expand=True)
        sb.config(command=self.chat.yview)
        self.chat.tag_configure("msg", foreground="#c9d1d9", lmargin1=6, lmargin2=6)
        for key, (_, color, label, _pos) in _COMMANDERS.items():
            self.chat.tag_configure(f"name_{key}", foreground=color,
                                    font=("Segoe UI Semibold", 9))
        self._chat_lines = 0
        # Per-instance War Room history so switching instances never loses chat.
        # cur = the instance id currently shown; each instance keeps its own
        # transcript + a seen-set so re-polls/re-tails don't duplicate lines.
        self.transcripts: dict = {}   # instance id -> [(agent, text), ...]
        self.seen: dict = {}          # instance id -> {(agent, text), ...}
        self.cur = None

        self.reachable_total = len(flags) if flags else 5
        self.captured: set[str] = set()
        self.flash_t = 0.0
        self.won = False
        self.red = 0
        self.blue = 0

        self.commanders = {}
        for key, (_, color, label, pos) in _COMMANDERS.items():
            self.commanders[key] = {"color": color, "label": label, "pos": pos,
                                    "state": "idle", "bubble": "", "bubble_t": 0.0,
                                    "spawn_cd": random.uniform(0.3, 1.0),
                                    "phase": random.random() * 6.28}
        self.soldiers: list[dict] = []
        self.sparks: list[dict] = []

        # -- load art (graceful fallback if missing) --
        self._keep = []
        self.ok = False
        self.cmd_frames = {}
        self.sol_frames = {}
        self.maps_raw = {}
        self.portraits = {}
        try:
            for key, (strip, *_rest) in _COMMANDERS.items():
                self.cmd_frames[key] = self._slice(_asset(strip), 8)
            for key, strip in _SOLDIER.items():
                self.sol_frames[key] = self._slice(_asset(strip), 4)
            for key, pfile in _PORTRAIT.items():
                img = tk.PhotoImage(file=_asset(pfile))
                self._keep.append(img)
                self.portraits[key] = img
            for i, nm in enumerate(["stage1_army_arrives_1x.png",
                                    "stage2_siege_1x.png", "stage3_ruins_1x.png"]):
                img = tk.PhotoImage(file=_asset(nm))
                self._keep.append(img)
                self.maps_raw[i] = img
            self.ok = True
        except Exception:  # noqa: BLE001  (fall back to shapes)
            self.ok = False

        self._maps_scaled = {}
        self._map_rect = (0, 0, 1, 1)   # ox, oy, zoom*w, zoom*h cached
        self._tsize = (0, 0)
        self._last = time.time()

        # Top-right field controls (placed as child widgets so the per-frame
        # canvas redraw doesn't wipe them): End engagement on top, the Grand
        # Strategist portrait below. Both call back into the control panel.
        self.on_strategist = None
        self.on_end = None
        try:
            simg = tk.PhotoImage(file=_asset("grand_strategist_portrait_1x.png"))
            self._keep.append(simg)
            panel = tk.Frame(self.canvas, bg="#3f7a34")  # blends with the field
            tk.Button(panel, text="⛔ End engagement", command=self._fire_end,
                      bd=0, relief="flat", bg="#b3443b", fg="#ffffff",
                      activebackground="#c9524a", activeforeground="#ffffff",
                      font=("Segoe UI Semibold", 9), cursor="hand2",
                      padx=8, pady=5).pack(fill="x", pady=(0, 6))
            holder = tk.Frame(panel, bg="#161b22", highlightthickness=2,
                              highlightbackground="#d2a8ff")
            tk.Button(holder, image=simg, bd=0, relief="flat", bg="#161b22",
                      activebackground="#21262d", cursor="hand2",
                      command=self._fire_strategist).pack()
            tk.Label(holder, text="Strategist", bg="#161b22", fg="#d2a8ff",
                     font=("Segoe UI Semibold", 8), cursor="hand2").pack(fill="x")
            holder.pack()
            panel.place(relx=1.0, x=-12, y=12, anchor="ne")
        except Exception:  # noqa: BLE001  (buttons are optional)
            pass

        self.after(60, self._tick)

    def _fire_strategist(self):
        cb = self.on_strategist
        if callable(cb):
            cb()

    def _fire_end(self):
        cb = self.on_end
        if callable(cb):
            cb()

    # -- asset helpers ----------------------------------------------------- #
    def _slice(self, path, n):
        strip = tk.PhotoImage(file=path)
        self._keep.append(strip)
        frames = []
        for i in range(n):
            fr = tk.PhotoImage(width=FRAME_W, height=FRAME_H)
            fr.tk.call(str(fr), "copy", str(strip), "-from",
                       i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_H, "-to", 0, 0)
            self._keep.append(fr)
            frames.append(fr)
        return frames

    def _scale_maps(self, w, h):
        if not self.ok:
            return
        z = max(1, min(w // 288, h // 198))
        ox, oy = (w - 288 * z) // 2, (h - 198 * z) // 2
        self._map_rect = (ox, oy, z)
        self._maps_scaled = {}
        for i, img in self.maps_raw.items():
            self._maps_scaled[i] = img.zoom(z)
            self._keep.append(self._maps_scaled[i])  # keep ref alive

    # -- public API -------------------------------------------------------- #
    def set_scores(self, red, blue):
        self.red, self.blue = red, blue

    def set_state(self, agent, state):
        c = self.commanders.get(agent)
        if c:
            c["state"] = state

    def say(self, agent, text):
        c = self.commanders.get(agent)
        if not (c and text):
            return
        clean = " ".join(str(text).split())
        c["bubble"] = clean[:120]
        c["bubble_t"] = time.time() + 9.0
        inst = self.cur
        if inst is None:            # no instance context yet: just render
            self._chat(agent, clean)
            return
        seen = self.seen.setdefault(inst, set())
        key = (agent, clean)
        if key in seen:            # dedup: re-poll/re-tail won't double up
            return
        seen.add(key)
        tr = self.transcripts.setdefault(inst, [])
        tr.append((agent, clean))
        if len(tr) > 600:          # bound memory; rebuild seen from the kept tail
            del tr[:len(tr) - 600]
            self.seen[inst] = set(tr)
        self._chat(agent, clean)

    def set_view(self, inst_id):
        """Show instance `inst_id`'s preserved chat. Switching restores that
        instance's full transcript instead of wiping — nothing is lost."""
        self.cur = inst_id
        self.transcripts.setdefault(inst_id, [])
        self.seen.setdefault(inst_id, set())
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._chat_lines = 0
        for agent, text in self.transcripts[inst_id]:
            self._chat(agent, text)

    def _export_chat(self):
        """Save the War Room feed to a .txt the operator picks."""
        try:
            text = self.chat.get("1.0", "end").strip()
        except Exception:  # noqa: BLE001
            text = ""
        if not text:
            messagebox.showinfo("Export chat log", "The War Room is empty — "
                                "nothing to export yet.")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title="Export War Room chat log",
            defaultextension=".txt",
            initialfile=f"warroom_{stamp}.txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        header = f"PurpleAI War Room chat — exported {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(header + "=" * len(header.strip()) + "\n\n" + text + "\n")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export chat log", f"Could not save:\n{exc}")
            return
        messagebox.showinfo("Export chat log", f"Saved to:\n{path}")

    def _chat(self, agent, text):
        c = self.commanders.get(agent)
        if not c:
            return
        self.chat.configure(state="normal")
        if self.portraits.get(agent):
            self.chat.image_create("end", image=self.portraits[agent], padx=2)
        self.chat.insert("end", f"  {c['label']}\n", (f"name_{agent}",))
        self.chat.insert("end", f"{text}\n\n", ("msg",))
        self._chat_lines += 1
        if self._chat_lines > 120:  # trim old history
            self.chat.delete("1.0", "40.0")
            self._chat_lines -= 20
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def capture(self, flag):
        if flag and flag not in self.captured:
            self.captured.add(flag)
            self.flash_t = time.time() + 1.0
            if len(self.captured) >= self.reachable_total:
                self.won = True

    def leak(self, agent):
        self._spawn_soldier(agent, leaked=True)

    def block(self):
        live = sorted([s for s in self.soldiers if s["alive"]],
                      key=lambda s: -(s["y"]))  # nearest the castle (higher y marched up)
        for s in live[:3]:
            s["alive"] = False
            self.sparks.append({"x": s["x"], "y": s["y"], "t": 0.0, "kind": "kill"})

    def reset(self, inst_id=None):
        """Clear the siege/chat. With inst_id, clear only that instance's
        transcript; without, wipe everything (the global Reset)."""
        self.captured.clear()
        self.soldiers.clear()
        self.sparks.clear()
        self.won = False
        for c in self.commanders.values():
            c["state"] = "idle"
            c["bubble"] = ""
        if inst_id is None:
            self.transcripts.clear()
            self.seen.clear()
        else:
            self.transcripts.pop(inst_id, None)
            self.seen.pop(inst_id, None)
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._chat_lines = 0

    # -- geometry ---------------------------------------------------------- #
    def _mapcoord(self, fx, fy):
        ox, oy, z = self._map_rect
        return ox + fx * 288 * z, oy + fy * 198 * z

    def _cmd_xy(self, key):
        fx, fy = self.commanders[key]["pos"]
        return self._mapcoord(fx, fy)

    # -- soldiers ---------------------------------------------------------- #
    def _spawn_soldier(self, agent, leaked=False):
        if len([s for s in self.soldiers if s["alive"]]) > 40 or self._tsize == (0, 0):
            return
        cx, cy = self._cmd_xy(agent)
        gx, gy = self._mapcoord(*_GATE)
        self.soldiers.append({
            "x": cx + random.uniform(-10, 10), "y": cy + random.uniform(-4, 10),
            "tx": gx + random.uniform(-16, 16), "ty": gy + random.uniform(-6, 6),
            "agent": agent, "alive": True, "leaked": leaked,
            "phase": random.random() * 6.28})

    def _tick(self):
        now = time.time()
        dt = min(0.1, now - self._last)
        self._last = now
        for key, c in self.commanders.items():
            if c["state"] == "running":
                c["spawn_cd"] -= dt
                if c["spawn_cd"] <= 0:
                    self._spawn_soldier(key)
                    c["spawn_cd"] = random.uniform(0.6, 1.3)
        for s in self.soldiers:
            if not s["alive"]:
                continue
            dx, dy = s["tx"] - s["x"], s["ty"] - s["y"]
            dist = math.hypot(dx, dy) or 1
            if dist < 8:
                self.sparks.append({"x": s["x"], "y": s["y"], "t": 0.0,
                                    "kind": "leak" if s["leaked"] else "hit"})
                s["alive"] = False
            else:
                spd = 46 * dt
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
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 50 or h < 50:
            return
        if (w, h) != self._tsize:
            self._tsize = (w, h)
            self._scale_maps(w, h)

        cap = len(self.captured)
        stage = 0 if cap <= 1 else (1 if cap <= 3 else 2)

        if self.ok and self._maps_scaled:
            ox, oy, z = self._map_rect
            c.create_image(ox, oy, image=self._maps_scaled[stage], anchor="nw")
        else:
            c.create_rectangle(0, 0, w, h, fill="#3f7a34", width=0)
            c.create_text(w / 2, 40, text="(siege art missing — rebuild with assets)",
                          fill="#e6edf3", font=("Segoe UI", 10))

        # fire flash on capture
        if self.flash_t > now:
            gx, gy = self._mapcoord(0.5, 0.42)
            for _ in range(8):
                c.create_text(gx + random.randint(-70, 70), gy + random.randint(-50, 50),
                              text="🔥", font=("Segoe UI", 13))

        # soldiers (behind commanders)
        for s in self.soldiers:
            frames = self.sol_frames.get(s["agent"])
            if self.ok and frames:
                fr = frames[int(now * 8 + s["phase"]) % len(frames)]
                c.create_image(s["x"], s["y"], image=fr, anchor="center")
            else:
                col = "#9aa0a6" if s["leaked"] else self.commanders[s["agent"]]["color"]
                c.create_oval(s["x"] - 3, s["y"] - 3, s["x"] + 3, s["y"] + 3, fill=col, width=0)

        # sparks
        for sp in self.sparks:
            self._spark(sp)

        # commanders + bubbles
        for key, cm in self.commanders.items():
            self._commander(key, cm, now)

        self._hud(now, w, h, cap)

    def _spark(self, sp):
        c = self.canvas
        x, y, t = sp["x"], sp["y"], sp["t"]
        if sp["kind"] == "kill":
            c.create_text(x, y - t * 12, text="✖", fill="#58a6ff", font=("Segoe UI", 12))
        elif sp["kind"] == "leak":
            c.create_text(x, y - t * 8, text="📄", font=("Segoe UI", 10))
        else:
            r = 3 + t * 7
            c.create_oval(x - r, y - r, x + r, y + r, outline="#ffd33d", width=1)

    def _commander(self, key, cm, now):
        c = self.canvas
        pal = self.pal
        x, y = self._cmd_xy(key)
        running = cm["state"] == "running"
        bob = math.sin(now * 4 + cm["phase"]) * (2 if running else 1)
        y += bob
        frames = self.cmd_frames.get(key)
        if self.ok and frames:
            fr = frames[int(now * 6) % len(frames)] if running else frames[0]
            c.create_image(x, y, image=fr, anchor="center")
        else:
            c.create_rectangle(x - 8, y - 8, x + 8, y + 10, fill=cm["color"], width=0)
        # nameplate
        sc = {"running": pal["green"], "queued": pal["amber"]}.get(cm["state"], pal["idle"])
        c.create_rectangle(x - 26, y + 24, x + 26, y + 38, fill="#0c1622",
                           outline=cm["color"])
        c.create_oval(x - 22, y + 28, x - 16, y + 34, fill=sc, width=0)
        c.create_text(x - 12, y + 31, text=cm["label"], anchor="w",
                      fill="#e6edf3", font=("Segoe UI Semibold", 9))
        # Reasoning is shown in the War Room chat, not as on-map bubbles.

    def _bubble(self, x, y, text):
        c = self.canvas
        pal = self.pal
        bw = 220
        c.create_rectangle(x, y, x + bw, y + 48, fill="#0c1622", outline=pal["accent"])
        c.create_polygon(x, y + 36, x - 9, y + 44, x, y + 26,
                         fill="#0c1622", outline=pal["accent"])
        c.create_text(x + 7, y + 5, text=text, anchor="nw", width=bw - 14,
                      fill="#7ee787", font=("Consolas", 9))

    def _hud(self, now, w, h, cap):
        c = self.canvas
        pal = self.pal
        total = self.reachable_total
        standing = total - min(cap, total)
        c.create_rectangle(8, 8, 158, 92, fill="#0c1622", outline=pal["border"])
        c.create_text(18, 24, text=f"🔴 {self.red}", anchor="w",
                      fill=pal["red"], font=("Segoe UI", 14, "bold"))
        c.create_text(18, 48, text=f"🔵 {self.blue}", anchor="w",
                      fill=pal["blue"], font=("Segoe UI", 14, "bold"))
        c.create_text(18, 72, text=f"town {standing}/{total}", anchor="w",
                      fill=pal["muted"], font=("Segoe UI", 9))
        frac = standing / total if total else 1
        c.create_rectangle(86, 66, 150, 78, outline=pal["border"])
        c.create_rectangle(86, 66, 86 + 64 * frac, 78,
                           fill=pal["blue"] if frac > 0.34 else pal["red"], width=0)
        if self.won:
            c.create_rectangle(w / 2 - 200, h / 2 - 32, w / 2 + 200, h / 2 + 32,
                               fill="#1a0b0b", outline=pal["red"], width=3)
            c.create_text(w / 2, h / 2, text="⚔  THE TOWN HAS FALLEN — RED WINS",
                          fill=pal["red"], font=("Segoe UI", 14, "bold"))
