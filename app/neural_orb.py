"""Procedural neural sphere. Animation does not load an AI or vision model."""
import math
import time
import tkinter as tk

from voice_core import STATES

PALETTES = {"idle": (240, 180, 77), "connecting": (120, 189, 230),
            "listening": (87, 222, 219), "thinking": (174, 136, 245),
            "speaking": (255, 191, 78), "clarifying": (249, 157, 72),
            "interrupted": (140, 232, 202), "sleeping": (85, 112, 157), "error": (241, 108, 115)}


def color(rgb, brightness=1):
    return "#" + "".join(f"{max(0,min(255,int(c*brightness))):02x}" for c in rgb)


def particle(index, count, elapsed, state, level=0):
    z = 1 - 2 * (index + 0.5) / count
    phi = index * math.pi * (3 - math.sqrt(5))
    radius = math.sqrt(1 - z*z)
    x, y = radius*math.cos(phi), radius*math.sin(phi)
    speed = {"sleeping": 0.025, "thinking": 0.38, "speaking": 0.18, "clarifying": 0.09}.get(state, 0.10)
    a = elapsed*speed
    x, z = x*math.cos(a)+z*math.sin(a), -x*math.sin(a)+z*math.cos(a)
    tilt = 0.22*math.sin(elapsed*0.13)
    y, z = y*math.cos(tilt)-z*math.sin(tilt), y*math.sin(tilt)+z*math.cos(tilt)
    if state == "thinking":
        twist = 1.15*y + elapsed*0.13
        x, z = x*math.cos(twist)+z*math.sin(twist), -x*math.sin(twist)+z*math.cos(twist)
        y *= 0.83
    elif state == "speaking":
        expansion = 1 + level*0.16*math.sin(phi*2+elapsed*8)
        x, y, z = x*expansion, y*expansion, z*expansion
    elif state == "listening":
        x *= 1+level*0.10
        y += 0.04*level*math.sin(phi+elapsed*7)
    elif state == "clarifying":
        x += (0.11 if x>0 else -0.11)*(0.5+0.5*math.sin(elapsed*2))
    elif state == "sleeping":
        y *= 0.48
    elif state == "connecting":
        x, z = math.cos(phi+elapsed)*radius, math.sin(phi+elapsed)*radius
    pulse = 1+0.025*math.sin(elapsed*1.4)
    return x*pulse, y*pulse, z*pulse


class NeuralOrb(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#070d19", highlightthickness=0, **kwargs)
        self.mode = "idle"
        self.input_level = self.output_level = 0.0
        self.preview = False
        self.economy = False
        self.started = time.monotonic()
        self.current_color = PALETTES["idle"]
        self.count = 320
        self.stars = [self.create_oval(0,0,2,2,fill="#152d42",outline="") for _ in range(48)]
        self.rings = [self.create_oval(0,0,1,1,outline="#1c2e3b",width=1) for _ in range(5)]
        self.edges = [self.create_line(0,0,1,1,fill="#233744",width=1) for _ in range(180)]
        self.nodes = [self.create_oval(0,0,2,2,fill="#e5b34b",outline="") for _ in range(self.count)]
        self.wave = self.create_line(0,0,1,1,fill="#f2be69",width=2,smooth=True)
        self.core = [self.create_oval(0,0,1,1,outline="#dba752",width=1) for _ in range(3)]
        self.after_id = self.after(50, self.animate)
        self.bind("<Destroy>", self.destroyed, add="+")

    def destroyed(self, event):
        if event.widget is self and self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def set_state(self, state):
        if state in STATES:
            self.mode = state

    def animate(self):
        if not self.winfo_exists():
            return
        if not self.winfo_viewable():
            self.after_id = self.after(400, self.animate)
            return
        elapsed = time.monotonic()-self.started
        width, height = self.winfo_width(), self.winfo_height()
        cx, cy = width/2, height/2
        radius = min(width,height)*0.42
        level = self.output_level if self.mode == "speaking" else self.input_level
        if self.preview:
            level = 0.3+0.25*math.sin(elapsed*3)
        target = PALETTES[self.mode]
        self.current_color = tuple(a+(b-a)*0.08 for a,b in zip(self.current_color,target))
        rgb = self.current_color
        points = []
        for index, item in enumerate(self.nodes):
            x,y,z = particle(index,self.count,elapsed,self.mode,level)
            perspective = 1/(1.8-z*0.28)
            px,py = cx+x*radius*1.7*perspective, cy+y*radius*1.7*perspective
            light = 0.25+0.68*(z+1)/2
            size = 0.8+1.3*(z+1)/2
            self.coords(item,px-size,py-size,px+size,py+size)
            self.itemconfigure(item,fill=color(rgb,light))
            points.append((px,py,z))
        for index,item in enumerate(self.edges):
            first = (index*2)%self.count
            second = (first+13+(index%3)*8)%self.count
            x,y,z=points[first]
            x2,y2,z2=points[second]
            self.coords(item,x,y,x2,y2)
            self.itemconfigure(item,fill=color(rgb,0.10+0.15*(z+z2+2)/4))
        for index,item in enumerate(self.stars):
            angle=index*2.39996+elapsed*0.018
            dist=radius*(1.18+0.4*math.sin(index*1.71)**2)
            x,y=cx+math.cos(angle)*dist,cy+math.sin(angle)*dist*0.68
            self.coords(item,x-1,y-1,x+1,y+1)
        for index,item in enumerate(self.rings):
            r=radius*(1.02+index*0.055)
            stretch=0.76+0.16*math.sin(elapsed*0.2+index)
            self.coords(item,cx-r,cy-r*stretch,cx+r,cy+r*stretch)
            self.itemconfigure(item,outline=color(rgb,0.09+index*0.018))
        waveform=[]
        amplitude=radius*(0.025+level*0.20) if self.mode in {"speaking","listening"} else radius*0.015
        if self.mode=="sleeping":
            amplitude*=0.3
        for index in range(65):
            x=cx-radius*0.55+index*radius*1.1/64
            envelope=math.sin(math.pi*index/64)**2
            y=cy+math.sin(index*0.42+elapsed*5)*amplitude*envelope
            waveform.extend([x,y])
        self.coords(self.wave,*waveform)
        self.itemconfigure(self.wave,fill=color(rgb,0.83))
        for index,item in enumerate(self.core):
            r=radius*(0.11+index*0.055)*(1+level*0.12)
            self.coords(item,cx-r,cy-r,cx+r,cy+r)
            self.itemconfigure(item,outline=color(rgb,0.58-index*0.13))
        delay = 500 if self.mode=="sleeping" else 200 if self.economy and self.mode=="idle" else 120 if self.mode=="idle" else 100 if self.economy else 50
        self.after_id=self.after(delay,self.animate)
