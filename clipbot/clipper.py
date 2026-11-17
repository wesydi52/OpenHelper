"""Вырезка клипа ffmpeg'ом; опционально 9:16 и вшитые субтитры."""
import subprocess

VERTICAL_VF = ("split[a][b];[a]scale=1080:1920,boxblur=30:5[bg];"
               "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def cut(src, start, duration, dst, vertical=True, srt=None):
    vf = []
    if vertical:
        vf.append(VERTICAL_VF)
    if srt:
        esc = srt.replace("\\", "/").replace(":", r"\:")
        vf.append(f"subtitles='{esc}':force_style='FontSize=14,Outline=2,Alignment=2,MarginV=120'")
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{max(start, 0):.2f}", "-i", src,
           "-t", f"{duration:.2f}"]
    if vf:
        # цепочки фильтров вертикали и субтитров объединяем через запятую
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)
    return dst
