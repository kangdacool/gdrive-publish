# gdrive-publish

Put a file in your own Google Drive, get a view-only link that never changes, and (optionally) drop
that link into a Google Sheet.

Built for one recurring chore. You keep revising a slide deck or a draft, and the copy behind the link
you already shared should always be the latest one. Sync clients do this silently and sometimes stop
without telling you. This tool uploads through the Drive API and checks the result.

> **한국어 요약** — 내 구글 드라이브 폴더에 파일을 올리고 «링크가 있는 모든 사용자 — 보기» 링크를 만든다.
> 같은 파일을 다시 올리면 드라이브 파일의 «내용만» 바뀌어 **링크가 그대로**다. 편집 권한은 절대 주지 않는다.
> 원하면 그 링크를 구글 시트의 원하는 칸에 넣는다. 처음 한 번 구글 클라우드 설정이 필요하다 → [docs/SETUP.md](docs/SETUP.md).

## What it guarantees

- **View-only, always.** Public access is set to "anyone with the link: viewer". Any public permission with
  another role is removed. Permissions are then re-read, and the run fails unless exactly that one
  remains.
- **Stable link.** Publishing the same file again replaces the content of the same Drive file. The link
  you already shared keeps working and shows the new version.
- **Checked upload.** The Drive file's md5 must match your local file, or the run fails.
- **Your account only.** It can touch only files it created (`drive.file` scope). Your token stays on your computer.
- **Careful with sheets.** `link-cell` writes only into an empty cell, or a cell that already holds the same
  label or link. Anything else stops the run unless you pass `--force`.

## Setup

One time, about 10 minutes: [docs/SETUP.md](docs/SETUP.md). It covers the Google Cloud project, the OAuth
client, and publishing the app so sign-in does not expire every 7 days.

```
pip install -r requirements.txt
python gdrive_publish.py setup
```

## Use

**bash / zsh**
```bash
python gdrive_publish.py publish talk.pdf --folder "Lab talks"
# -> link: https://drive.google.com/file/d/.../view?usp=drivesdk

python gdrive_publish.py link-cell "https://docs.google.com/spreadsheets/d/SHEET_ID" "LINK" \
       --label "talk.pdf" --row-match "3. Linear Regression" --col-header "Slides"
```

**PowerShell**
```powershell
python gdrive_publish.py publish talk.pdf --folder "Lab talks"
python gdrive_publish.py link-cell "https://docs.google.com/spreadsheets/d/SHEET_ID" "LINK" `
       --label "talk.pdf" --row-match "3. Linear Regression" --col-header "Slides"
```

**cmd.exe**
```bat
python gdrive_publish.py publish talk.pdf --folder "Lab talks"
python gdrive_publish.py link-cell "https://docs.google.com/spreadsheets/d/SHEET_ID" "LINK" ^
       --label "talk.pdf" --row-match "3. Linear Regression" --col-header "Slides"
```

Other commands:

```
python gdrive_publish.py status talk.pdf     # recorded link, and whether the local file changed since
python gdrive_publish.py --selftest          # offline checks
python e2e_check.py                          # full check against your account (creates and deletes test files)
```

The tool remembers which Drive file belongs to which local file in `.gdrive_publish.json`. By default
it is stored next to the file; `--registry` puts it elsewhere. It holds only file ids and links, no
secrets. If you delete it, the next publish creates a new file with a new link.

### Choosing the sheet cell

Prefer `--row-match` (text somewhere in the target row) plus `--col-header` (the column's header) over
`--cell F3`, because rows get inserted and fixed addresses go stale. The tool asks the Sheets API where
the header actually is. Do not count columns in a CSV export: a published CSV can show a column in a
different position from its real cell address.

## Using it with an AI coding agent

The split that works well:

- the agent runs `publish`, which is deterministic and only ever creates a view-only link;
- the agent reads the sheet, decides which row and column the link belongs in, and runs `link-cell`
  with `--row-match` and `--col-header`.

`link-cell` refuses to overwrite someone else's cell, so a wrong guess fails loudly instead of
clobbering data. Tell your agent where this README is. The commands above are all it needs.

## Limits

- Personal use. Each person sets up their own Google Cloud project. There is no shared server or app.
- An unpublished (Testing) OAuth app forces a new sign-in every 7 days. See SETUP step 5.
- An unverified published app shows a warning at sign-in and allows up to 100 users. That is fine for one person.
- Large files upload resumably. Very large files (several GB) have not been tested.

## License

MIT
