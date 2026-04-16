import sys, os, requests, yt_dlp

url = sys.argv[1]
webhook = sys.argv[2]

DOWNLOAD_DIR = "/teamspace/studios/this_studio/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

ydl_opts = {
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
    "merge_output_format": "mp4",
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = os.path.join(DOWNLOAD_DIR, f"{info['id']}.mp4")

    requests.post(webhook, json={
        "status": "success",
        "title": info.get("title", ""),
        "channel": info.get("uploader", ""),
        "duration": info.get("duration", 0),
        "filepath": filepath,
        "url": url
    })

except Exception as e:
    requests.post(webhook, json={
        "status": "error",
        "error": str(e),
        "url": url
    })
