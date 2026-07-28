import httpx

urls = [
    "https://iskconeducation.org/media_library_old/199620curriculum20correspondence20-20curriculum20topics20-20songs20by20grade20level20-20etiquette.pdf",
    "https://iskconeducation.org/media_library_old/KC20Christmas20Carols20for2080s20Xmas20marathons.pdf",
]
ua = {"User-Agent": "BhavaLibrary/1.0 (+mailto:svarnagaurangdas@gmail.com)"}
for url in urls:
    h = httpx.head(url, headers=ua, follow_redirects=True, timeout=60)
    g = httpx.get(url, headers=ua, follow_redirects=True, timeout=60)
    print("URL", url[-60:])
    print(" HEAD", h.status_code, "cl", h.headers.get("content-length"), "ct", h.headers.get("content-type"))
    print(" GET", g.status_code, "len", len(g.content), "cl", g.headers.get("content-length"), "ct", g.headers.get("content-type"))
    print(" first", g.content[:30])
