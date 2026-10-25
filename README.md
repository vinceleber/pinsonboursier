# Rapport Social Investing — envoi quotidien

Chaque jour de semaine à 17 h (heure de Toronto / Québec, après la fermeture des bourses), GitHub Actions :
1. récupère Fear & Greed (actions et crypto), prix crypto, cours, VIX et mentions Reddit;
2. calcule RSI, MACD (12, 26, 9), MA50 et MA200 pour chaque titre suivi;
3. génère le rapport PDF complet;
4. l'envoie par Gmail en pièce jointe.

## Mise en route (environ 10 minutes)

1. **Créer un dépôt GitHub privé** (par exemple `social-investing-bot`).
2. **Y déposer tout le contenu de ce dossier**, en gardant les dossiers `.github/` et `bot/`.
   Le dossier `.github` est caché : utilisez Git ou GitHub Desktop plutôt que le glisser-déposer du navigateur.
3. **Créer un mot de passe d'application Gmail** (validation en deux étapes requise) :
   https://myaccount.google.com/apppasswords — 16 caractères, affichés une seule fois.
4. **Ajouter 3 secrets** : dépôt → Settings → Secrets and variables → Actions → New repository secret.

   | Secret | Valeur |
   |---|---|
   | `GMAIL_FROM` | votre adresse Gmail |
   | `GMAIL_APP_PASSWORD` | le mot de passe d'application (16 caractères) |
   | `TO_EMAILS` | un ou plusieurs courriels séparés par des virgules |

5. **Premier essai manuel** : onglet Actions → « Rapport Social Investing quotidien » → Run workflow.
   Comptez 2 à 4 minutes, puis vérifiez la boîte de réception (et les indésirables).
6. C'est tout : le déclenchement automatique se fait ensuite du lundi au vendredi.

## Fichier à entretenir : `bot/content.json`

Tout ce qui est calculé ou récupéré chaque matin (cours, RSI, MACD, MA50/MA200, Fear & Greed, VIX, crypto, Reddit) est automatique.
Le contenu **éditorial** ne l'est pas : listes sous-évalués / surévalués, cibles d'analystes, P/E, convictions, faits saillants,
lecture AAII, signaux d'initiés. Il est daté dans `editorial_as_of`; le rapport affiche un **avertissement** quand ce contenu vieillit
(7 jours pour les commentaires, 30 jours pour les cibles et P/E, 9 jours pour l'AAII). Mettez-le à jour quand vous revoyez vos idées.

## Ce que le rapport ne fait pas

- Aucune valeur n'est inventée : si une source ne répond pas, la case affiche **N/D**.
- Les cours d'actions sont les **clôtures du jour** (le rapport part à 17 h, après la fermeture de 16 h; les résultats publiés après la cloche ne sont pas encore dans les cours).
- Reddit bloque parfois les adresses des serveurs GitHub : les mentions peuvent alors être absentes (la section l'indique).
- Les signaux d'initiés sont à NEUTRE tant que vous ne les saisissez pas.
- Document informatif seulement; ne constitue pas un conseil en placement.

## Dépannage

- **Aucun courriel** : ouvrir le dernier run dans l'onglet Actions et lire l'étape « Générer et envoyer le rapport ».
  `Authentication` = mauvais mot de passe d'application ou secret mal copié.
- **PDF sans cours** : Yahoo Finance a refusé la requête; relancer le workflow plus tard. Le robot n'envoie rien s'il n'a aucune cotation.
- **Heure d'envoi** : le workflow tourne à 17 h 17 heure de Toronto (changement d'heure géré automatiquement).
  GitHub peut retarder les tâches planifiées de quelques minutes.
- **Dépôt public** : GitHub désactive les tâches planifiées après 60 jours sans activité; gardez le dépôt privé.

## Essai local

```bash
pip install -r bot/requirements.txt
python bot/main.py --demo --no-email     # PDF avec données synthétiques (aucun réseau)
python bot/main.py --no-email            # PDF avec vraies données, sans courriel
```

## Police

Le rapport utilise Montserrat si les fichiers `Montserrat-Regular/Medium/Bold/Light.ttf` sont dans `bot/fonts/`, sinon Poppins (fournie).

## Mise à jour du contenu éditorial (octobre 2026)

`bot/content.json` est daté du **13 octobre 2026** : cibles et P/E prévisionnels tirés du consensus affiché par StockAnalysis.com
(clôture du 13 octobre), AAII du 7 octobre, faits saillants du 9 au 13 octobre. Les médianes sectorielles, les convictions,
les signaux d'initiés et les rendements à 12 mois du tableau AAII historique sont des saisies ou des ordres de grandeur non recalculés.
Chaque champ `bucket` des listes alimente le donut de répartition sectorielle.

## Canaux de Social Investing (ajout du 14 octobre 2026)

Relevés automatiquement chaque matin, sans clé ni compte : **ApeWisdom** (mentions Reddit agrégées par titre et crypto),
**StockTwits** (symboles en tendance), **Wikipédia** (pages vues des sociétés) et **Google Trends** (au mieux : non officiel,
souvent bloqué depuis les serveurs; la section affiche alors N/D). Le Reddit direct est conservé en complément.
Le signal « Social » de la matrice de confluence utilise ApeWisdom en priorité (5 à 299 mentions sur 24 h = intérêt, 300 et plus = excès).

Le rapport contient deux sections : un radar du jour (palmarès, croisement avec vos 20 titres) et un catalogue des sources
(X, Facebook, YouTube/TikTok, Quiver, etc.) avec leur coût et leurs limites, tiré de `social_sources` dans `bot/content.json`.
`wiki_titles` (titres d'articles Wikipédia) et `trends_keywords` (mots-clés Google Trends) se modifient dans le même fichier.
Aucun de ces collecteurs n'a pu être testé en direct depuis l'environnement de développement : le premier essai manuel (Run workflow)
dira lesquels répondent depuis GitHub.

## EDGAR, YouTube et TikTok (ajout du 14 octobre 2026)

Deux secrets **facultatifs** activent ces sections (sans eux, elles affichent « N/D » et le reste du rapport est inchangé) :

| Secret | Contenu | Où l'obtenir |
|---|---|---|
| `SEC_USER_AGENT` | Un nom et un courriel de contact, par exemple `Vincent Rapport vous@exemple.com` | Rien à créer : la SEC exige que les outils automatisés s'identifient. Ce texte est envoyé à la SEC; choisissez l'adresse que vous acceptez de lui communiquer. |
| `YOUTUBE_API_KEY` | Clé d'API YouTube Data v3 | Google Cloud Console → nouveau projet → activer « YouTube Data API v3 » → Identifiants → Créer une clé API |

- **SEC EDGAR** : achats et ventes en marché ouvert des initiés (formulaire 4) sur 45 jours, pour les titres américains des deux listes. Ils alimentent la colonne « INIT. » des matrices
  (achats de 100 000 $ et plus et supérieurs aux ventes = favorable; ventes de 25 M$ et plus sans achat = défavorable). Limite de la SEC : 10 requêtes par seconde (le robot reste bien en dessous).
- **YouTube** : vidéo la plus vue des 7 derniers jours pour chacun des 20 titres. La page officielle des quotas (mise à jour le 8 octobre 2026) indique 100 recherches par jour : le robot en utilise 20.
- **TikTok** : aucune API utilisable par un particulier. Notez vos observations hebdomadaires dans `manual_watch.items` de `bot/content.json` (date, canal, sujet, observation); elles s'affichent dans le rapport.
- SEDI (sociétés canadiennes) n'a pas d'API publique connue : consultation manuelle sur sedi.ca.

Aucun de ces collecteurs n'a été testé avec les vrais serveurs depuis l'environnement de développement (l'analyseur du formulaire 4 a été validé avec un faux fichier).

## Plate-forme web (ajout du 15 octobre 2026)

Le dossier `docs/` est un site statique (aucun serveur) : marché, explorer (recherche par société, symbole ou industrie, tri, filtres, export CSV),
industries (indice équipondéré), fiche société (cours 5 ans, MA50/MA200, RSI, MACD, matrice de confluence, intérêt social), comparaison et historique du marché.

**Mise en ligne (une fois)** : dépôt → Settings → Pages → Source « Deploy from a branch », branche `main`, dossier `/docs`.
Settings → Actions → General → Workflow permissions → **Read and write** (le robot enregistre `docs/data` chaque matin).
Attention : GitHub Pages sur un dépôt **privé** exige un forfait payant, et le site publié est **public** (cours et listes de titres visibles par quiconque a le lien).
Sans Pages, ouvrez simplement `docs/index.html` après avoir récupéré le dépôt : le site fonctionne aussi depuis le disque.

**Historique** : les cours (5 ans), indicateurs, Fear & Greed et pages Wikipédia (365 jours) sont reconstitués à chaque exécution. Les instantanés de signaux,
mentions Reddit/StockTwits, achats d'initiés et lectures AAII s'accumulent à partir de la première exécution.

**Ajouter des sociétés** : `universe_extra` dans `bot/content.json`, par ex. `{"ticker":"SHOP.TO","name":"Shopify (TSX)","industry":"Logiciels et infonuagique"}`.
Essai local : `python bot/main.py --demo --no-email` crée un site de démonstration (données synthétiques) dans `OUTPUT_DIR/site_demo`.

## Gérer les titres suivis (ajout du 17 octobre 2026)

Page « Gérer les titres » du site : ajouter une société (symbole Yahoo Finance, ex. `META`, `SHOP.TO`), la retirer ou changer son industrie.
Le site étant statique, la page produit le contenu de **`watchlist.json`** (racine du dépôt) : copiez-le, ouvrez le fichier dans GitHub (bouton fourni), collez, enregistrez.
Au prochain passage (ou via Run workflow), les nouveaux symboles reçoivent leur historique complet. Les retraits masquent le titre de la plateforme; le PDF garde ses listes éditoriales (`content.json`).
Si un symbole ne répond pas, la page l'indique (« Sans données au dernier passage »).

## Rapport PDF et matrice de confluence sur le site (ajout du 17 octobre 2026)

- Le bouton **Rapport PDF** (barre du haut) ouvre le dernier rapport. Chaque jour, le robot copie le PDF dans `docs/rapports/` (`dernier.pdf` + une copie datée; les 30 plus récentes sont gardées) et l'enregistre avec les données. Les archives sont listées dans la page Historique.
  Attention : sur un site public (GitHub Pages), le PDF est lui aussi public.
- La page **Confluence** reprend la matrice du rapport (9 signaux + score + verdict) avec une colonne **Valorisation** : sous-évalué / surévalué selon les listes éditoriales du rapport, sinon selon le ratio P/E ÷ médiane du secteur (< 0,85 sous-évalué, > 1,5 surévalué); N/D sans P/E saisi.
