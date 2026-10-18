"""Build the static demo site (GitHub Pages / Vercel) from the real dashboard.

    python tools/build_demo.py [out_dir]     # default: site/

The page is the same dashboard/index.html, with window.SAFESIGHT_DEMO=true set
first so it runs its built-in scripted scene instead of connecting to a server.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAG = "<script>window.SAFESIGHT_DEMO = true;</script>\n"


def build(out):
    with open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8") as f:
        html = f.read()
    if "<script>" not in html:
        raise SystemExit("dashboard has no <script> block")
    html = html.replace("<script>", FLAG + "<script>", 1)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    open(os.path.join(out, ".nojekyll"), "w").close()
    print(f"demo site written to {out}/index.html ({len(html)} bytes)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site"))
