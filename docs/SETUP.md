# One-time setup

About 10 minutes, once per Google account. Each computer then needs one sign-in (step 8).

You are creating your own small OAuth "app" in Google Cloud. Only you use it, and it runs only on your
computer. No server and no billing are involved. The tool never sees anyone else's account.

## 1. Create a project

<https://console.cloud.google.com/projectcreate>. Any name works, for example `gdrive-publish`.

The console may offer things like "Create an agent" or "Create a Gemini API key". You need neither.
Close those prompts.

Make sure the project picker at the top shows the new project before continuing.

## 2. Turn on two APIs

Open each page and click **Enable**:

- Google Drive API: <https://console.cloud.google.com/apis/library/drive.googleapis.com>
- Google Sheets API: <https://console.cloud.google.com/apis/library/sheets.googleapis.com>

You only need the Sheets API if you will use `link-cell`.

## 3. Configure the consent screen

Open <https://console.cloud.google.com/auth/overview> and click **Get started**. If that button does
nothing, open <https://console.cloud.google.com/auth/overview/create> directly.

- App information: app name (anything), user support email (your Gmail).
- Audience: **External**. Internal is only for Google Workspace organisations.
- Contact information: your email.
- Finish: tick the Google API Services User Data Policy, then click **Create**.

## 4. Add yourself as a test user

<https://console.cloud.google.com/auth/audience>, then **Add users**. Add your own Gmail address and click **Save**.

This is enough to start using the tool today, but see step 5.

## 5. Publish the app (or re-sign-in every 7 days)

While the app is in **Testing**, Google issues refresh tokens that **expire after 7 days**. Publishing
removes the expiry. It does not require Google's verification review: unverified apps are limited to
100 users, and the sign-in screen shows a "Google hasn't verified this app" warning. For an app only
you use, that is fine.

The **Publish app** button stays greyed out until the Branding page has a home page and a privacy
policy link on an authorized domain. If you have no website, two static pages on GitHub Pages work:

1. Create a public GitHub repository named `YOUR-USERNAME.github.io`.
2. Add an `index.html` saying what the tool is, and a `privacy.html`. A filled-in template is at
   [`privacy.example.html`](privacy.example.html). Replace the placeholders and keep only what is true for you.
3. Wait a minute, then check that `https://YOUR-USERNAME.github.io/privacy.html` opens.
4. On <https://console.cloud.google.com/auth/branding>:
   - set the application home page to `https://YOUR-USERNAME.github.io/`;
   - set the privacy policy link to `https://YOUR-USERNAME.github.io/privacy.html`;
   - add `YOUR-USERNAME.github.io` under **Authorized domains**, using its own box and not the
     developer-email box below it;
   - click **Save**.
5. Back on **Audience**, click **Publish app** and then **Confirm**. The status should read **In production**.

Keep those pages online. The published app expects them to exist.

## 6. Create the OAuth client

<https://console.cloud.google.com/auth/clients/create>: application type **Desktop app**, then **Create**,
then **Download JSON**.

Save the file as `client_secret.json` in the tool's home folder:

| OS | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\gdrive-publish\` |
| macOS / Linux | `~/.config/gdrive-publish/` |

Set `GDRIVE_PUBLISH_HOME` to use a different folder. Keep this folder **outside** Dropbox, OneDrive or
iCloud. It holds your credentials.

## 7. Install the Python packages

```
pip install -r requirements.txt
```

## 8. Sign in

```
python gdrive_publish.py setup
```

A browser window opens:

- pick your account;
- on "Google hasn't verified this app", choose **Continue** (or **Advanced, then Go to ...**);
- tick both permissions and click **Continue**.

The token is saved next to `client_secret.json`.

**If you published the app (step 5) after signing in, run `setup` once more.** A token obtained
while the app was in Testing keeps its 7-day expiry even after you publish.

## What the permissions mean

| Scope | What it allows |
|---|---|
| `drive.file` | Only files and folders this tool created. It cannot list or read anything else in your Drive. |
| `spreadsheets` | Read and write Google Sheets. Used only by `link-cell`, on the sheet you name. |

To revoke access, go to <https://myaccount.google.com/permissions>.
