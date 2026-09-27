# Luis & Jessie Photography: static archive

This is a static snapshot of luisandjessie.com, captured from the live WordPress site on 2026-09-27. It uses the site's own HTML, Kadence theme CSS, JavaScript, colors, and images, so it looks and behaves like the original. Galleries, carousels, the lightbox, and the mobile menu all work. It doesn't need WordPress or a database, so it can be hosted for free on GitHub Pages.

```
docs/     the website (GitHub Pages serves this folder)
tools/    scripts used to build it (only needed if you want to re-capture)
```

## What changed from the live site

- **Full-size photos:** the lightbox now opens the 2048px versions WordPress had already generated instead of the 2560px originals. That cut the size from about 980 MB to about 580 MB, safely under GitHub Pages' 1 GB limit. On-screen quality is the same.
- **Links are relative,** so the site works at `https://<user>.github.io/<repo>/` or on luisandjessie.com.
- **WordPress-only features were removed:** feeds, the REST API and oEmbed tags, the LiteSpeed cache ping, and the search box on the 404 page.
- **Kept as-is:**
  - The Contact page embeds your **Studio Ninja** form, so it only works while that Studio Ninja account/form exists.
  - The **counter.dev** and **PostHog** analytics snippets are still in place. Delete them from the pages if you don't want them.
- **Fonts:** the theme names Montserrat and Source Sans Pro, but the live site never loads them, so visitors see the system sans-serif font. The copy matches that exactly.

## Publish on GitHub Pages

1. Create a new **public** repository on GitHub, for example `luisandjessie-site`. On a free GitHub plan, Pages needs a public repo.
2. From this folder, run:
   ```bash
   cd ~/Code/luisandjessie-site
   git init -b main
   git add .
   git commit -m "Static archive of luisandjessie.com"
   git remote add origin https://github.com/<your-username>/luisandjessie-site.git
   git push -u origin main
   ```
   The push is about 580 MB and may take a few minutes. If it fails with an HTTP 400 or "RPC failed" error, run `git config http.postBuffer 524288000` and push again.
3. On GitHub, open the repo's **Settings → Pages**. Under "Build and deployment", set **Source: Deploy from a branch**, **Branch: main**, and **Folder: /docs**, then save.
4. After a minute or two the site is live at `https://<your-username>.github.io/luisandjessie-site/`.

## Keeping the luisandjessie.com domain (optional)

The only ongoing cost is the domain renewal. Hosting is free.

1. In **Settings → Pages → Custom domain**, enter `luisandjessie.com` and save. GitHub adds a `CNAME` file to `docs/`.
2. At your domain registrar's DNS settings, delete the old A/AAAA records that point to your current host, then add:
   - `A` records for `@` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - (optional IPv6) `AAAA` records for `@` → `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`
   - `CNAME` for `www` → `<your-username>.github.io`
3. When the DNS check passes, tick **Enforce HTTPS**.
4. Cancel the WordPress hosting only **after** the new site loads on the domain.

To confirm these values, see GitHub's docs: "Managing a custom domain for your GitHub Pages site" (docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).

## Re-capturing (only while WordPress is still up)

```bash
cd tools
python3 crawl.py /tmp/raw           # downloads the rendered site
rm -rf ../docs && cp -r /tmp/raw ../docs
python3 postprocess.py ../docs      # cleans it up for GitHub Pages
```
This needs Python 3 with `requests`, `beautifulsoup4`, and `lxml`.
