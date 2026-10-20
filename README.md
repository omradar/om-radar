# OM Radar

Site média indépendant sur l'Olympique de Marseille. Il se régénère tout seul toutes les 3 heures :

- résultats, classement et buteurs de Ligue 1 (football-data.org, plan gratuit)
- radar de jeu et probabilités du prochain match (calculés par `build.py`)
- titres de presse avec image et court extrait, via les flux RSS des médias que tu choisis (fichier `config.json`)
- une fiche d'article sur le site pour chaque titre, avec un bouton vers l'article d'origine

Aucun abonnement. Seul le nom de domaine, optionnel, est payant.

## Mise en ligne (une seule fois)

1. Sur GitHub, ouvre le dépôt `om-radar`, clique sur **Add file**, puis **Upload files**, et glisse tout le contenu de ce dossier (y compris le dossier caché `.github`, voir plus bas), puis **Commit changes**.
2. Va dans **Settings**, puis **Pages**. Dans « Build and deployment », choisis **Source : GitHub Actions**.
3. Vérifie que le secret `FOOTBALL_DATA_TOKEN` existe (Settings, Secrets and variables, Actions).
4. Va dans l'onglet **Actions**, clique sur « Mise à jour du site », puis **Run workflow**. Après 1 à 2 minutes, l'adresse du site s'affiche dans Settings, Pages.

Le site se met ensuite à jour seul toutes les 3 heures.

### Si le dossier `.github` n'est pas envoyé par glisser-déposer
Certains navigateurs ignorent les dossiers cachés. Dans ce cas : **Add file**, **Create new file**, tape `.github/workflows/update.yml` comme nom, puis colle le contenu du fichier du même nom.

## En cas d'erreur
Onglet **Actions**, clique sur l'exécution en rouge. Le message dit l'essentiel :
- « clé refusée » : le secret `FOOTBALL_DATA_TOKEN` est faux ou absent.
- « trop d'appels » : relance dans une minute.
- « cette ressource n'est pas incluse dans le plan gratuit » : on retire la ressource concernée.

Quand une mise à jour échoue, la version précédente reste en ligne.

## Tester chez soi sans clé
```
python tests/make_sample.py
python build.py --sample
```
Ouvre ensuite `dist-sample/index.html`. Ce sont des données inventées, à ne jamais publier.

## Ce qui est volontairement simple
- Pas de direct : le plan gratuit retarde les scores.
- Pas de statistiques avancées (xG, tirs, possession) : réservées aux offres payantes.
- Les textes d'analyse sont générés par modèles de phrases à partir des chiffres, sans IA payante.
- Les photos des articles ne sont pas stockées sur le site : elles sont affichées depuis le site de l'éditeur (image de partage de l'article), avec le nom du média. Elles restent la propriété de leur éditeur. Si un média te le demande, mets `"enabled": false` sur sa source, ou `"images": false` pour tout couper. Quand aucune photo n'est trouvée, une vignette aux couleurs du site s'affiche.

## Choisir les sources de presse
Tout se règle dans `config.json`, liste `sources`. Pour chaque média :
- `enabled` : `true` pour l'utiliser, `false` pour l'écarter.
- `site` : adresse de sa page d'accueil. Le site cherche alors lui-même le flux RSS. C'est le plus simple pour ajouter un média.
- `url` : adresse exacte de son flux RSS, si tu la connais (à la place de `site`).
- `only_om` : `true` si le flux parle de tout le football (le site ne garde alors que les articles sur l'OM).
- `category` : `"auto"` classe les articles en Mercato ou Actualités d'après le titre.

Pour ajouter un média : copie un bloc existant, change `name` et `site`, puis lance « Run workflow » dans l'onglet Actions. Si le site n'a pas de flux RSS public, la mise à jour le signale (voir ci-dessous) et il n'apparaît simplement pas.

Après chaque mise à jour, l'onglet **Actions** de GitHub (clique sur la dernière exécution, section « Annotations ») indique pour chaque source le nombre de titres retenus, le nombre de photos trouvées et l'erreur éventuelle. Le fichier `status.json` du site donne la même information.

Les sources « Google Actualités » sont désactivées : leurs liens sont des redirections et l'adresse réelle des articles n'est plus récupérable, donc elles n'ont pas de photo. Les médias qui n'ont pas de flux RSS public (par exemple om.fr) ne peuvent pas être suivis.

Réglages généraux : `images` (`false` pour ne plus afficher aucune photo de presse), `excerpt_chars` (longueur du court extrait, `0` pour aucun), `max_news` (nombre total d'articles), `per_source_cap` (nombre maximum d'articles par média, pour garder une page variée).

## Nom de domaine (om-radar.fr)
1. Achète `om-radar.fr` chez un bureau d'enregistrement (OVHcloud, Gandi, etc.).
2. Dans sa zone DNS, supprime les enregistrements créés par défaut, puis ajoute :
   - 4 enregistrements **A** (nom `@`) : `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - 1 enregistrement **CNAME** (nom `www`) vers `omradar.github.io`
3. Sur GitHub : **Settings**, **Pages**, **Custom domain**, écris `om-radar.fr`, puis **Save**. Attends que GitHub affiche « DNS check successful » (de quelques minutes à 24 h), puis coche **Enforce HTTPS**.
4. Seulement ensuite, dans `config.json`, mets `"domain": "om-radar.fr"` : le site utilise alors ce nom pour ses adresses officielles et son plan du site.

Le fichier `CNAME` généré par le site est ignoré par GitHub quand on publie avec Actions : c'est le réglage de l'étape 3 qui compte.

## Fichiers utiles
- `config.json` : sources de presse et réglages.
- `build.py` : récupération des données, calculs, génération du site.
- `templates/index.html` et `assets/style.css` : design.
- `.github/workflows/update.yml` : planning de mise à jour.
