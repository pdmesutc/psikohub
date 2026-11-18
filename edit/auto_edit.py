#!/usr/bin/env python3
"""Sessizlik tabanlı jump-cut + ritmik punch-in zoom + loudnorm.
Kullanım: python3 auto_edit.py out.mp4 klip1.mp4 klip2.mp4 ...
"""
import re, subprocess, sys, os

SIL_DB, SIL_MIN = -32, 0.25   # bu eşik/süreden uzun boşluklar kesilir
PAD = 0.06                    # kesimde konuşma kenarında bırakılan pay (sn)
ZOOM_EVERY = 3.0              # en az bu kadar sn'de bir plan değişimi
ZOOMS = [1.0, 1.18, 1.0, 1.28]  # geniş -> yakın -> geniş -> çok yakın
W, H = 392, 848

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def dur(f):
    return float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f]).stdout)

def speech_segments(f):
    d = dur(f)
    err = run(["ffmpeg","-hide_banner","-i",f,"-af",f"silencedetect=n={SIL_DB}dB:d={SIL_MIN}","-vn","-f","null","-"]).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    segs, t = [], 0.0
    for s, e in zip(starts, ends + [None]*(len(starts)-len(ends))):
        if s - t > 0.15: segs.append((max(0,t-PAD) if t>0 else 0, min(d, s+PAD)))
        t = e if e is not None else d
    if t < d - 0.15: segs.append((max(0,t-PAD), d))
    return [(a,b) for a,b in segs if b-a > 0.3]

def main():
    out, clips = sys.argv[1], sys.argv[2:]
    inputs, vf, af, labels = [], [], [], []
    n, acc, zi = 0, 0.0, 0
    for ci, f in enumerate(clips):
        inputs += ["-i", f]
        for a, b in speech_segments(f):
            if acc >= ZOOM_EVERY:
                zi, acc = (zi+1) % len(ZOOMS), 0.0
            z = ZOOMS[zi]
            cw, ch = int(W/z)//2*2, int(H/z)//2*2
            cx, cy = int(W*0.42 - cw/2), int(H*0.40 - ch/2)   # yüze doğru kaydır
            cx, cy = max(0, min(W-cw, cx)), max(0, min(H-ch, cy))
            L = b - a
            vf.append(f"[{ci}:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,crop={cw}:{ch}:{cx}:{cy},scale=720:1556:flags=lanczos,setsar=1[v{n}]")
            af.append(f"[{ci}:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.012,afade=t=out:st={max(0,L-0.012):.3f}:d=0.012[a{n}]")
            print(f"#{n:02d} clip{ci+1} {a:6.2f}-{b:6.2f} ({L:4.2f}s) zoom x{z}")
            labels.append(f"[v{n}][a{n}]"); acc += L; n += 1
    fc = ";".join(vf+af) + ";" + "".join(labels) + f"concat=n={n}:v=1:a=1[v][a0];[a0]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    cmd = ["ffmpeg","-y",*inputs,"-filter_complex",fc,"-map","[v]","-map","[a]",
           "-c:v","libx264","-crf","18","-preset","medium","-pix_fmt","yuv420p","-r","30",
           "-c:a","aac","-b:a","192k","-movflags","+faststart",out]
    r = run(cmd)
    print(r.stderr[-400:] if r.returncode else f"OK -> {out} ({dur(out):.1f}s)")

main()
