"""Optional design preview from the same geometry, with explicitly simulated audio levels."""
import math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from neural_orb import particle,PALETTES,color
from paths import DATA


def main():
    font=ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf",19)
    small=ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf",12)
    states=[("idle","Siaga"),("listening","Mendengar"),("thinking","Menyiapkan jawaban"),
            ("speaking","Berbicara"),("clarifying","Perlu penjelasan"),("sleeping","Tidur")]
    frames=[]
    for number,(state,label) in enumerate(states):
        for frame in range(12):
            elapsed=number*1.2+frame/10
            level=0.4+0.3*math.sin(elapsed*4)
            image=Image.new("RGB",(600,480),"#070d19")
            draw=ImageDraw.Draw(image)
            rgb=PALETTES[state]
            draw.text((28,18),"LEVA / NEURAL VOICE",font=font,fill=color(rgb))
            draw.text((28,49),"Pratinjau pola · mikrofon mati · level audio disimulasikan",font=small,fill="#8aa1b8")
            cx,cy,radius=300,248,153
            for ring in range(5):
                r=radius*(1.02+ring*0.055)
                stretch=0.76+0.16*math.sin(elapsed*0.2+ring)
                draw.ellipse((cx-r,cy-r*stretch,cx+r,cy+r*stretch),outline=color(rgb,0.13))
            points=[]
            for index in range(320):
                x,y,z=particle(index,320,elapsed,state,level)
                scale=1/(1.8-z*0.28)
                points.append((cx+x*radius*1.7*scale,cy+y*radius*1.7*scale,z))
            for index in range(180):
                first=(index*2)%320;second=(first+13+(index%3)*8)%320
                x,y,z=points[first];x2,y2,z2=points[second]
                draw.line((x,y,x2,y2),fill=color(rgb,0.10+0.15*(z+z2+2)/4))
            for x,y,z in sorted(points,key=lambda p:p[2]):
                r=0.8+1.3*(z+1)/2
                draw.ellipse((x-r,y-r,x+r,y+r),fill=color(rgb,0.25+0.68*(z+1)/2))
            waveform=[]
            amplitude=radius*(0.025+level*0.20) if state in {"speaking","listening"} else radius*0.015
            for index in range(65):
                waveform.append((cx-radius*0.55+index*radius*1.1/64,
                                 cy+math.sin(index*0.42+elapsed*5)*amplitude*math.sin(math.pi*index/64)**2))
            draw.line(waveform,fill=color(rgb,0.8),width=2)
            for index in range(3):
                r=radius*(0.11+index*0.055)
                draw.ellipse((cx-r,cy-r,cx+r,cy+r),outline=color(rgb,0.58-index*0.13))
            draw.text((300,427),label,font=font,fill=color(rgb),anchor="mm")
            frames.append(image)
    target=DATA/"verification"
    target.mkdir(parents=True,exist_ok=True)
    frames[36].save(target/"neural-preview-still.png")
    frames[0].save(target/"neural-states-preview.gif",save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True)
    print(str(target/"neural-states-preview.gif"))


if __name__=="__main__":
    main()
