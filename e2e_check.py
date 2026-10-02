# -*- coding: utf-8 -*-
"""End-to-end check against your real Google account -- run it after setup, and after changing the tool.

    python e2e_check.py

It runs the same commands the README shows, as subprocesses, and checks what a stranger would see:
  1. publish a small text file into a throwaway Drive folder
  2. fetch the link WITHOUT signing in: it must open (not redirect to a login page)
  3. read the permissions back: exactly one public permission, anyone/reader
  4. change the file and publish again: the link must stay the same and serve the new content's md5
  5. create a throwaway spreadsheet, run link-cell with --row-match/--col-header, read the cell back
  6. run link-cell on a cell that holds someone else's text: it must refuse
Everything it created is deleted at the end (files the tool created only).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gdrive_publish as gp  # noqa: E402

FOLDER = "gdrive-publish e2e check"


def run(*args, ok=True):
    r = subprocess.run([sys.executable, os.path.join(HERE, "gdrive_publish.py")] + list(args),
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout + r.stderr).strip()
    print("  $ gdrive_publish.py %s\n    %s" % (" ".join(args), out.replace("\n", "\n    ")))
    if ok and r.returncode != 0:
        raise SystemExit("FAIL: command failed")
    if not ok and r.returncode == 0:
        raise SystemExit("FAIL: command should have refused")
    return out


def link_of(out):
    return next(l.strip()[len("link: "):] for l in out.splitlines() if l.strip().startswith("link: "))


def main():
    d = tempfile.mkdtemp()
    f = os.path.join(d, "e2e.txt")
    reg = os.path.join(d, "registry.json")
    open(f, "w", encoding="utf-8").write("first version %s\n" % time.time())
    drive, sheets = gp._services(gp.credentials())
    created = []
    try:
        print("1. publish")
        url = link_of(run("publish", f, "--folder", FOLDER, "--registry", reg))
        data = json.load(open(reg, encoding="utf-8"))
        fid = next(iter(data["files"].values()))["id"]
        created += [fid, data["folders"][FOLDER]]

        print("2. anonymous fetch")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            final, body = resp.geturl(), resp.read(200000).decode("utf-8", "ignore")
        assert "accounts.google.com" not in final, "redirected to sign-in: %s" % final
        assert "e2e.txt" in body, "page does not show the file"
        print("  opens without sign-in")

        print("3. permissions")
        perms = drive.permissions().list(fileId=fid, fields="permissions(type,role)").execute()["permissions"]
        pub = [(p["type"], p["role"]) for p in perms if p["type"] in ("anyone", "domain")]
        assert pub == [("anyone", "reader")], pub
        print("  public access:", pub)

        print("4. republish changed content")
        open(f, "w", encoding="utf-8").write("second version %s\n" % time.time())
        url2 = link_of(run("publish", f, "--folder", FOLDER, "--registry", reg))
        assert url2 == url, "link changed: %s -> %s" % (url, url2)
        md5 = drive.files().get(fileId=fid, fields="md5Checksum").execute()["md5Checksum"]
        assert md5 == gp._md5(f), "Drive content is not the new version"
        print("  same link, new content")

        print("5. link-cell")
        ss = sheets.spreadsheets().create(body={"properties": {"title": "gdrive-publish e2e"}},
                                          fields="spreadsheetId").execute()["spreadsheetId"]
        created.append(ss)
        sheets.spreadsheets().values().update(
            spreadsheetId=ss, range="A1", valueInputOption="RAW",
            body={"values": [["Week", "Topic", "Slides"], ["1", "Intro", ""], ["2", "Regression", "someone else's note"]]}).execute()
        run("link-cell", ss, url, "--label", "e2e.txt", "--row-match", "Intro", "--col-header", "Slides")
        back = sheets.spreadsheets().values().get(spreadsheetId=ss, range="C2",
                                                  valueRenderOption="FORMULA").execute()["values"][0][0]
        assert url in back, back
        print("  C2 =", back[:60], "...")

        print("6. refuse to overwrite")
        run("link-cell", ss, url, "--label", "e2e.txt", "--row-match", "Regression", "--col-header", "Slides", ok=False)
        print("\nE2E OK")
    finally:
        for x in created:
            try:
                drive.files().delete(fileId=x).execute()
            except Exception as e:
                print("  cleanup: could not delete %s (%r)" % (x, e))


if __name__ == "__main__":
    main()
