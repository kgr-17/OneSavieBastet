"""Download the competition source data from the public Azure blob URLs.

The Kaggle dataset `wliilamsam/download-vuln` showed itself as private but its
download-vuln.ipynb notebook simply ran two wget commands against these public
URLs. The 12-character hex IDs in train.csv/test.csv are folder names inside
the zip files — there is no hash function to reverse.

Run from project root:
    python src/pipeline/download_data.py
"""
import os
import sys
import urllib.request

URLS = {
    "data/train.zip": "https://osbastetkagglesa.blob.core.windows.net/kaggle/train.zip",
    "data/test.zip":  "https://osbastetkagglesa.blob.core.windows.net/kaggle/test.zip",
}


def fetch(url: str, dest: str):
    if os.path.exists(dest):
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"  skip {dest} (already present, {size_mb:.0f} MB)")
        return
    print(f"  downloading {url} -> {dest}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", "0"))
        read = 0
        chunk = 1 << 20
        while True:
            buf = r.read(chunk)
            if not buf:
                break
            f.write(buf)
            read += len(buf)
            if total:
                pct = read * 100 / total
                print(f"    {read/1024/1024:.0f} / {total/1024/1024:.0f} MB ({pct:.0f}%)", end="\r", flush=True)
    print()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for dest, url in URLS.items():
        fetch(url, dest)
    print("\nDone. Unzip with:")
    print("  cd data && unzip train.zip && unzip test.zip")


if __name__ == "__main__":
    main()
