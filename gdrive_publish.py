# -*- coding: utf-8 -*-
"""gdrive_publish -- put a local file in your own Google Drive and get a view-only share link that never changes.

    python gdrive_publish.py setup                        # once per computer: sign in and allow
    python gdrive_publish.py publish FILE --folder "Drive folder name"
    python gdrive_publish.py status FILE
    python gdrive_publish.py link-cell SHEET_URL LINK --label "text shown in the cell"
                             (--cell F3 | --row-match "text in that row" --col-header "column header")
    python gdrive_publish.py --selftest

What `publish` guarantees
    * The file lands in a folder of YOUR Drive (created on first use).
    * Sharing is "anyone with the link -- viewer". Edit access is never granted: any public
      permission with another role is removed, then permissions are re-read and the run stops
      unless exactly one public permission (anyone/reader) remains.
    * The upload is checked: the Drive file's md5 must equal the local file's md5.
    * Publishing the same file again replaces the CONTENT of the same Drive file, so the link
      you already handed out (or put in a sheet) keeps working and shows the new version.

`link-cell` writes =HYPERLINK(link, label) into one Google Sheets cell. Prefer --row-match +
--col-header over a fixed --cell: rows move, headers rarely do. The cell must be empty, or already
hold this label or this link; anything else stops the run (use --force to overwrite). The cell is
re-read after writing.

Setup (Google Cloud project, OAuth client, publishing the app) is in docs/SETUP.md.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

__version__ = "0.1.0"

SCOPES = ["https://www.googleapis.com/auth/drive.file",
          "https://www.googleapis.com/auth/spreadsheets"]


def _default_home():
    if os.environ.get("GDRIVE_PUBLISH_HOME"):
        return os.environ["GDRIVE_PUBLISH_HOME"]
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], "gdrive-publish")
    return os.path.join(os.path.expanduser("~"), ".config", "gdrive-publish")


HOME = _default_home()
CLIENT = os.path.join(HOME, "client_secret.json")
TOKEN = os.path.join(HOME, "token.json")
FOLDER_MIME = "application/vnd.google-apps.folder"
MIME = {".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png", ".jpg": "image/jpeg", ".csv": "text/csv", ".txt": "text/plain",
        ".html": "text/html", ".zip": "application/zip", ".mp4": "video/mp4"}


##################################################################
#####  1.  Sign-in                                           #####
##################################################################
def credentials(interactive=False):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception as e:
            if not interactive:
                raise SystemExit("Token refresh failed (%r). Run `python gdrive_publish.py setup` again.\n"
                                 "If this happens every 7 days, your OAuth app is still in 'Testing' "
                                 "-- see docs/SETUP.md, step 5." % e)
    if not interactive:
        raise SystemExit("Not signed in. Follow docs/SETUP.md, then run `python gdrive_publish.py setup`.")
    if not os.path.exists(CLIENT):
        raise SystemExit("Missing %s -- download the Desktop OAuth client JSON (docs/SETUP.md, step 6)." % CLIENT)
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  success_message="Signed in. You can close this window.")
    _save_token(creds)
    return creds


def _save_token(creds):
    os.makedirs(HOME, exist_ok=True)
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def _services(creds):
    from googleapiclient.discovery import build
    return (build("drive", "v3", credentials=creds, cache_discovery=False),
            build("sheets", "v4", credentials=creds, cache_discovery=False))


##################################################################
#####  2.  Registry (which Drive file belongs to which local file)
##################################################################
def _registry_path(path, registry):
    return registry or os.path.join(os.path.dirname(os.path.abspath(path)), ".gdrive_publish.json")


def _key(path, reg):
    """Registry key = path relative to the registry's folder, so two files with the same name in
    different folders do not overwrite each other's Drive file."""
    rel = os.path.relpath(os.path.abspath(path), os.path.dirname(os.path.abspath(reg)))
    return rel.replace(os.sep, "/")


def _load(reg):
    if os.path.exists(reg):
        with open(reg, encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}, "folders": {}}


def _dump(reg, data):
    with open(reg, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


##################################################################
#####  3.  Finding the sheet cell (offline-testable)         #####
##################################################################
def col_letter(i):
    """0 -> A, 25 -> Z, 26 -> AA"""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def locate(values, row_match, col_header):
    """Rows of a sheet -> (A1 address, current value) of the cell in the row containing row_match and
    the column whose header is col_header. Stops if either is missing or the row is ambiguous."""
    head_i = next((i for i, r in enumerate(values) if any(str(c).strip() == col_header for c in r)), None)
    if head_i is None:
        raise SystemExit("No column header %r found." % col_header)
    col = [str(c).strip() for c in values[head_i]].index(col_header)
    rows = [i for i, r in enumerate(values) if i != head_i and any(row_match in str(c) for c in r)]
    if len(rows) != 1:
        raise SystemExit("%d rows contain %r -- need exactly one%s"
                         % (len(rows), row_match, (" (rows %s)" % ", ".join(str(i + 1) for i in rows)) if rows else ""))
    r = rows[0]
    cur = values[r][col] if col < len(values[r]) else ""
    return "%s%d" % (col_letter(col), r + 1), cur


def _ours(cur, url, label):
    """May we write this cell? Only if it is empty, or already shows this label, or already links here."""
    c = (cur or "").strip()
    return (not c) or c == label or bool(url and url in c)


##################################################################
#####  4.  Publish                                           #####
##################################################################
def _folder(drive, data, name):
    fid = data["folders"].get(name)
    if fid:
        try:
            if not drive.files().get(fileId=fid, fields="id,trashed").execute().get("trashed"):
                return fid
        except Exception:
            pass
    fid = drive.files().create(body={"name": name, "mimeType": FOLDER_MIME}, fields="id").execute()["id"]
    data["folders"][name] = fid
    print("  created Drive folder: %s" % name)
    return fid


def publish(path, folder, registry=None):
    """Upload (or replace the content of) `path` in Drive folder `folder`, make it view-only for anyone
    with the link, and return the link. Does not touch any sheet."""
    from googleapiclient.http import MediaFileUpload
    if not os.path.exists(path):
        raise SystemExit("No such file: %s" % path)
    fname = os.path.basename(path)
    reg = _registry_path(path, registry)
    data = _load(reg)
    key = _key(path, reg)
    drive, _ = _services(credentials())
    mime = MIME.get(os.path.splitext(fname)[1].lower(), "application/octet-stream")
    local = _md5(path)
    rec = data["files"].get(key)
    fid, meta = None, {}
    if rec:
        try:
            meta = drive.files().get(fileId=rec["id"], fields="id,trashed,md5Checksum").execute()
            fid = None if meta.get("trashed") else rec["id"]
        except Exception:
            fid = None
        if fid is None:
            print("  ! the recorded Drive file is gone (deleted or in trash) -- uploading anew; the link will change")
    media = MediaFileUpload(path, mimetype=mime, resumable=True)
    if fid and meta.get("md5Checksum") == local:
        print("  Drive already has this exact content (md5) -- nothing uploaded")
        info = drive.files().get(fileId=fid, fields="id,webViewLink,md5Checksum").execute()
    elif fid:
        info = drive.files().update(fileId=fid, media_body=media, fields="id,webViewLink,md5Checksum").execute()
        print("  replaced content, same link: %s" % fname)
    else:
        parent = _folder(drive, data, folder)
        info = drive.files().create(body={"name": fname, "parents": [parent]}, media_body=media,
                                    fields="id,webViewLink,md5Checksum").execute()
        print("  uploaded: %s" % fname)
    if info.get("md5Checksum") != local:
        raise SystemExit("Uploaded md5 %s does not match local %s -- upload incomplete"
                         % (info.get("md5Checksum"), local))
    view_only(drive, info["id"])
    url = info["webViewLink"]
    data["files"][key] = {"id": info["id"], "url": url, "md5": local, "folder": folder,
                          "uploaded": time.strftime("%Y-%m-%d %H:%M")}
    _dump(reg, data)
    print("  link: %s" % url)
    return url


def view_only(drive, fid):
    """Make the public access exactly 'anyone with the link -- viewer'. Remove public permissions with
    any other role, add the viewer one if missing, then re-read and stop unless it is the only one."""
    def lst():
        return drive.permissions().list(fileId=fid, fields="permissions(id,type,role)").execute().get("permissions", [])
    for p in lst():
        if p.get("type") in ("anyone", "domain") and p.get("role") != "reader":
            drive.permissions().delete(fileId=fid, permissionId=p["id"]).execute()
            print("  ! removed public %s permission with role %s (view-only allowed)" % (p.get("type"), p.get("role")))
    if not any(p.get("type") == "anyone" and p.get("role") == "reader" for p in lst()):
        drive.permissions().create(fileId=fid, body={"type": "anyone", "role": "reader",
                                                     "allowFileDiscovery": False}).execute()
    pub = [p for p in lst() if p.get("type") in ("anyone", "domain")]
    if [(p["type"], p["role"]) for p in pub] != [("anyone", "reader")]:
        raise SystemExit("Public access is not exactly 'anyone with the link -- viewer': %r" % pub)
    print("  sharing: anyone with the link can view (no edit; re-read and confirmed)")


##################################################################
#####  5.  Put a link in a sheet cell                        #####
##################################################################
def _sheet_id(s):
    m = re.search(r"/d/([A-Za-z0-9_-]+)", s)
    return m.group(1) if m else s


def link_cell(sheet, url, label, cell=None, row_match=None, col_header=None, force=False, tab=None):
    """Write =HYPERLINK(url, label) into one cell; refuse to overwrite other content unless force."""
    _, sheets = _services(credentials())
    sid = _sheet_id(sheet)
    if not tab:
        tab = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties.title").execute()[
            "sheets"][0]["properties"]["title"]
    q = "'%s'" % tab.replace("'", "''")
    get = lambda rng: sheets.spreadsheets().values().get(spreadsheetId=sid, range=rng,
                                                         valueRenderOption="FORMULA").execute().get("values", [])
    if cell:
        got = get("%s!%s" % (q, cell))
        cur = got[0][0] if got and got[0] else ""
        a1 = cell
    else:
        if not (row_match and col_header):
            raise SystemExit("Give --cell, or both --row-match and --col-header.")
        a1, cur = locate(get(q), row_match, col_header)
    if not force and not _ours(cur, url, label):
        raise SystemExit("Cell %s already holds %r -- not overwriting (use --force)." % (a1, cur))
    formula = '=HYPERLINK("%s","%s")' % (url, label.replace('"', '""'))
    sheets.spreadsheets().values().update(spreadsheetId=sid, range="%s!%s" % (q, a1),
                                          valueInputOption="USER_ENTERED",
                                          body={"values": [[formula]]}).execute()
    back = get("%s!%s" % (q, a1))
    if not back or url not in back[0][0]:
        raise SystemExit("Re-read of %s does not contain the link: %r" % (a1, back))
    print("  %s!%s <- %s (re-read and confirmed)" % (tab, a1, label))
    return a1


##################################################################
#####  6.  Command line                                      #####
##################################################################
def _selftest():
    assert [col_letter(i) for i in (0, 5, 25, 26, 27, 701)] == ["A", "F", "Z", "AA", "AB", "ZZ"]
    v = [["Week", "Date", "Topic", "Presenter", "Notes", "Slides"],
         ["1", "Sep 11", "2. Statistical Learning", "A"],
         ["2", "Oct 2", "3. Linear Regression", "B", "LM", "old.pdf"],
         ["3", "Oct 16", "4. Classification", "C"]]
    assert locate(v, "3. Linear Regression", "Slides") == ("F3", "old.pdf")
    assert locate(v, "4. Classification", "Slides") == ("F4", "")
    for bad in (("no such row", "Slides"), ("Oct", "Slides"), ("3. Linear Regression", "no such column")):
        try:
            locate(v, *bad)
            raise AssertionError("should have stopped: %r" % (bad,))
        except SystemExit:
            pass
    u = "https://drive.google.com/file/d/X/view"
    assert _ours("", u, "a.pdf") and _ours("a.pdf", u, "a.pdf")
    assert _ours('=HYPERLINK("%s","a.pdf")' % u, u, "a.pdf")
    assert not _ours("someone's note", u, "a.pdf")
    assert not _ours('=HYPERLINK("https://drive.google.com/file/d/OTHER/view","x")', u, "a.pdf")
    reg = os.path.join(os.sep, "proj", ".gdrive_publish.json")
    assert _key(os.path.join(os.sep, "proj", "ch3", "deck.pdf"), reg) == "ch3/deck.pdf"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Publish a file to your Google Drive with a stable view-only link.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="sign in once (opens a browser)")
    p = sub.add_parser("publish", help="upload or replace, then share view-only")
    p.add_argument("file")
    p.add_argument("--folder", required=True, help="Drive folder name (created if missing)")
    p.add_argument("--registry", help="where to remember file ids (default: .gdrive_publish.json beside the file)")
    s = sub.add_parser("status", help="show the recorded link and whether the local file changed")
    s.add_argument("file")
    s.add_argument("--registry")
    c = sub.add_parser("link-cell", help="write the link into a Google Sheets cell")
    c.add_argument("sheet", help="sheet URL or id")
    c.add_argument("url", help="the link from publish")
    c.add_argument("--label", required=True)
    c.add_argument("--tab", help="sheet tab name (default: first tab)")
    c.add_argument("--cell", help="A1 address, e.g. F3")
    c.add_argument("--row-match", help="text that appears in the target row")
    c.add_argument("--col-header", help="header text of the target column")
    c.add_argument("--force", action="store_true", help="overwrite whatever is in the cell")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.cmd == "setup":
        credentials(interactive=True)
        print("Signed in. Token: %s" % TOKEN)
    elif a.cmd == "publish":
        publish(a.file, a.folder, registry=a.registry)
    elif a.cmd == "status":
        reg = _registry_path(a.file, a.registry)
        rec = _load(reg)["files"].get(_key(a.file, reg))
        if not rec:
            print("Not published yet.")
        else:
            same = rec["md5"] == _md5(a.file)
            print("%s\n  uploaded %s; local file %s" % (rec["url"], rec["uploaded"],
                                                       "unchanged" if same else "CHANGED -- publish again"))
    elif a.cmd == "link-cell":
        link_cell(a.sheet, a.url, a.label, cell=a.cell, row_match=a.row_match, col_header=a.col_header,
                  force=a.force, tab=a.tab)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
