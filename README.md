# Veille — agrégateur IT personnel

Fil d'actualité personnel (Dev, Cybersécurité, SysAdmin, IA). Deux modes :

| Mode | Où | Mise à jour |
|------|----|-------------|
| **Live** (FastAPI + SQLite) | Votre machine / un VPS | Toutes les 4 min, temps réel |
| **GitHub Pages** (statique) | `https://VOUS.github.io/REPO/` | Toutes les heures via GitHub Actions |

GitHub Pages n’exécute pas de Python : une Action agrège les RSS, écrit `articles.json`, et publie le site statique. Les **favoris** et le **lu/non-lu** sont alors stockés dans votre navigateur (`localStorage`).

---

## Héberger sur GitHub Pages (recommandé pour un usage perso)

1. Créez un dépôt **public** (Pages gratuit nécessite un repo public, sauf GitHub Pro).
2. Poussez ce projet :

```bash
git init
git add .
git commit -m "Veille IT"
git branch -M main
git remote add origin https://github.com/VOTRE_USER/VOTRE_REPO.git
git push -u origin main
```

3. Sur GitHub : **Settings → Pages → Source = GitHub Actions**.
4. Onglet **Actions** : autorisez les workflows si GitHub le demande, puis attendez le job **Publier Veille sur GitHub Pages**.
5. Le site sera à :

`https://VOTRE_USER.github.io/VOTRE_REPO/`

Vous pouvez relancer une sync à la main : **Actions → Publier Veille → Run workflow**.

> Le cron GitHub tourne **environ toutes les heures** (pas en temps réel). C’est la limite de Pages.

---

## Lancer en local (fil live)

```bash
pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Ouvrez [http://127.0.0.1:8000](http://127.0.0.1:8000). Base SQLite : `data/veille.db`.

Générer un snapshot statique (sans serveur) :

```bash
python scripts/build_feed.py --out _site
```

---

## Raccourcis

| Touche | Action       |
|--------|--------------|
| `/`    | Recherche    |
| `R`    | Synchroniser |
| `F`    | Favoris      |
| `1–5`  | Catégories   |

## Sources

Hacker News, Developpez.com, BleepingComputer, The Hacker News, Krebs, Korben, LinuxFr, Next.ink, Dev.to, Lobsters, Ars Technica, Hugging Face, GitHub Trending, Cloudflare Blog, Kubernetes, r/netsec.
