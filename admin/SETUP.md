# Plugin-pages editor — one-time login setup

The editor (`/admin`) is already built. It just needs a GitHub sign-in broker so
you can log in and publish. This is a ~10-minute, one-time setup. After it's done,
editing is: open the editor URL → sign in with GitHub → edit text / drop in
screenshots → **Publish**. Changes appear on the app's plugin pages on next launch,
with no app update.

There are two small pieces: **(1)** a tiny free auth worker, and **(2)** a GitHub
OAuth app that tells GitHub to trust it. Do them in this order.

---

## 1. Deploy the auth worker (Cloudflare — free)

We use Sveltia's ready-made auth worker (nothing to code).

1. Go to <https://github.com/sveltia/sveltia-cms-auth> and click the **Deploy to
   Cloudflare Workers** button (you'll sign in / create a free Cloudflare account).
2. When it's deployed, note the worker URL — it looks like
   `https://sveltia-cms-auth.<your-name>.workers.dev`.
3. Leave the two secrets (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`) for step 2 —
   you'll fill them in after creating the OAuth app.

## 2. Create the GitHub OAuth app

1. GitHub → your profile → **Settings → Developer settings → OAuth Apps → New OAuth App**
   (or do it under the **Pure-BPM org** settings if you want it owned by the org).
2. Fill in:
   - **Application name:** `Pure BPM Plugin Pages`
   - **Homepage URL:** your editor URL (from step 3 below, e.g.
     `https://pure-bpm.github.io/pure-plugins-releases/admin/`)
   - **Redirect URI** (GitHub's redesigned form calls the callback this — same
     thing): your worker URL **+ `/callback`**, e.g.
     `https://sveltia-cms-auth.<your-name>.workers.dev/callback`
   - Leave **Allow wildcard matching** and **Enable Device Flow** unchecked.
   - **Uncheck "Expire user access tokens"** — otherwise the editor login drops
     after 8 hours.
3. Click **Register application**, then **Generate a new client secret**.
4. Copy the **Client ID** and **Client secret** into the Cloudflare worker's
   variables (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`). Also set
   `ALLOWED_DOMAINS` to your editor host, e.g. `pure-bpm.github.io`.

## 3. Point the editor at your worker + turn it on

1. In this repo, edit **`admin/config.yml`** → set `backend.base_url` to your worker
   URL (the one from step 1, no `/callback`). Commit it. *(Tell me the worker URL and
   I'll make this edit for you.)*
2. Enable hosting for `/admin`: repo **Settings → Pages → Build and deployment →
   Source: Deploy from a branch → `main` / root**. Your editor is then at
   `https://pure-bpm.github.io/pure-plugins-releases/admin/`. *(I can enable this for
   you if I have admin on the repo.)*

## 4. Use it

Open the editor URL, click **Login with GitHub**, choose **Plugin pages → All
plugins**, edit any plugin, drag screenshots into the **Screenshots** field, and hit
**Publish**. Done — the app picks it up on next launch.

---

### Notes
- Every publish is a normal git commit to `manifest.json` (+ any images under
  `/screenshots`), so there's full history and one-click revert on GitHub.
- Only people you authorize (org/repo write access) can publish.
- If you'd rather not touch Cloudflare/GitHub settings yourself, grant me access
  and I'll stand up the worker + OAuth app and wire `base_url` — then it's just
  "open editor, sign in, edit."
