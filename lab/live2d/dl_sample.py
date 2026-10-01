import json, os, urllib.request
API = "https://api.github.com/repos/Live2D/CubismWebSamples/contents/Samples/Resources/Haru"
DST = "build/live2d_sample/Haru"
os.makedirs(DST, exist_ok=True)
items = json.load(urllib.request.urlopen(API + "?ref=develop", timeout=30))
print("目录下有 %d 个条目" % len(items))
def fetch(url, path):
    with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
for it in items:
    p = os.path.join(DST, it["name"])
    if it["type"] == "dir":
        sub = json.load(urllib.request.urlopen(it["url"], timeout=30))
        os.makedirs(p, exist_ok=True)
        for s in sub:
            fetch(s["download_url"], os.path.join(p, s["name"]))
    else:
        fetch(it["download_url"], p)
print("下载完成 ->", DST)
for root, _d, fs in os.walk(DST):
    for f in fs: print("  ", os.path.relpath(os.path.join(root,f), DST))
