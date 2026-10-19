# OM Radar

Site média indépendant sur l'Olympique de Marseille. Il se régénère tout seul toutes les 3 heures :

- résultats, classement et buteurs de Ligue 1 (football-data.org, plan gratuit)
- radar de jeu et probabilités du prochain match (calculés par `build.py`)
- titres de presse (titre, source, lien uniquement) via des flux RSS Google Actualités

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
- Pas de photos : elles sont soumises à des droits. Les visuels sont des graphismes aux couleurs du logo. Tu peux ajouter tes propres images ou des images libres de droits plus tard.

## Fichiers utiles
- `config.json` : flux de presse à suivre.
- `build.py` : récupération des données, calculs, génération du site.
- `templates/index.html` et `assets/style.css` : design.
- `.github/workflows/update.yml` : planning de mise à jour.
