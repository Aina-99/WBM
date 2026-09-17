# Contexte IA — WBM.extension (PyRevit)

> Ce fichier capitalise l'état du projet pour qu'une session Claude démarrée sur
> n'importe quel poste (clone git ou copie OneDrive) puisse reprendre le travail
> sans redécouvrir tout l'historique. À mettre à jour au fil des sessions.
> Dernière mise à jour : 2026-09-17.

## Projet

Extension pyRevit "WBM" : contrôle qualité de maquette, numérotation d'éléments,
génération de remarques BCF. Remote GitHub : `https://github.com/Aina-99/WBM.git`
(branches `main` et `develop`).

Deux copies de travail locales existent sur cette machine, toutes deux des repos
git réels pointant sur le même remote :
- `D:\03_Projet\Cellule dev\64_PyRevit Extension\WBM.extension`
- `D:\04_Perso\OneDrive\M360\PyRevit.Script\WBM.extension` (celle-ci, sur OneDrive)

**Toujours push avant de changer de poste/dossier** pour ne pas diverger entre les deux.

## Règle impérative du projet

Toujours créer un fichier XAML séparé pour les fenêtres. Ne jamais construire
d'interface directement en Python.

## État par module

### QC.panel / ModelCheck.pushbutton (`lib/wbm_qc/`)

Contrôleur qualité modulaire (moteur + registry + règles indépendantes), fenêtre
de résultats WPF moderne avec bouton "afficher" par erreur.

Règles implémentées (`lib/wbm_qc/rules/`) :
- Titleblock : le nom doit commencer par `WBM`
- Project Number (info projet) == nom de fichier == 18 digits
- Project Issue Date (info projet, format `YYYYMMDD`) == date dans le nom de fichier (format `YYMMDD`) == date du jour
- Fraîcheur des exports Dynamo (façade area, coordonnées, géométrie des pièces) —
  scripts de référence dans `00_Template/05_Dynamo Scripts_WBM/`
- Convention de tags :
  - Room : `Level.Incrément` (attribut `Number`)
  - Porte : `T.Level.Incrément` (attribut `Mark`)
  - Fenêtre : `F.Level.Incrément` (attribut `Mark`)
  - Incrémentation 3 digits, unique, réinitialisée à 1 par niveau
  - Nombre d'éléments == nombre de tags, un seul avertissement consolidé par
    type de tag (pas un par tag individuel)
  - Tous les tags doivent être visibles dans les vues contenant "Grundriss"
  - RoomTag : label parameter "Unbounded Height" doit avoir le préfixe `LRH:`
  - DoorTag : famille imposée `M360_DoorTagV2`
  - WindowTag : famille imposée `M360_Window tag V2`
- Cohérence largeur × hauteur des pièces vs `area` (tolérance ±2 m², idéalement
  via bounding box en Groundfloor pour réduire la marge d'erreur)
- Liens feuilles/vues + nommage (`rule_sheet_naming.py`) :
  - Nom de feuille : `Type de vue - Libre`
  - Types de vue autorisés : `Grundriss`, `Vermietungsgrundriss`, `Ansichten`, `Schnitt`, `JPG`
  - Les identifiants de la partie "Libre" sont **toujours séparés par une
    virgule**, y compris pour `Schnitt` (ex : `Schnitt - A-A,B-B`,
    `Grundriss - EG,OG1`). *Correction du 2026-09-17* : l'ancienne règle
    imposait un underscore pour `Schnitt`, mais les feuilles réelles du
    projet utilisent la virgule comme tous les autres types — la règle a été
    alignée sur l'usage réel (vérifié en direct sur la feuille A2.004 du doc
    actif Revit).
  - Chaque identifiant doit se retrouver dans au moins une vue liée, et
    chaque vue liée (hors vues contenant `Lageplan`) doit contenir au moins
    un identifiant
  - Feuilles contenant `Vorlage` exclues de tout contrôle
- Chevauchement des tags (`rule_tag_overlap.py`, ajouté le 2026-09-17) :
  l'étiquette des tags pièce/porte/fenêtre ne doit chevaucher ni un mur ni
  un contour de pièce, dans les vues en plan "Grundriss". Une anomalie par
  tag (pour pouvoir "Afficher" chacun). Points clés validés en test :
  - Ne pas utiliser la bbox brute du tag : elle inclut la ligne de rappel.
    Les leaders sont retirés dans une transaction **toujours annulée**
  - Sans leader, Revit ramène un RoomTag sur le point de la pièce : la boîte
    est recalée de (TagHeadPosition − Location.Point). Pas le cas des
    IndependentTag (portes/fenêtres)
  - La largeur de la bbox d'un RoomTag correspond déjà au texte réel
    (mesuré à 0,1 mm près) : inutile de recalculer une largeur dynamique
  - Murs : coupe réelle du solide au plan de coupe de la vue
    (`CutWithHalfSpace`), pas l'axe + épaisseur
  - Comme la règle ouvre une transaction, "Relancer" et "Afficher" de la
    fenêtre ModelCheck passent par `ApiContextRunner` (ExternalEvent)
- Contrôle Dynamo : vérifier que le script a tourné sur **toutes** les pièces
  (pas juste respecter une marge d'erreur)

Dashboard et catégorie "sévérité" dans l'UI : masqués pour l'instant (pas
prioritaires). Export CSV retiré (jugé pas utile).

### Numbering.panel / Door Numbering (Beta).pushbutton (`lib/wbm_numbering/door_numbering.py`)

Fonctionnel. Règle : `T.Niveau(EG00).Incrément` (3 digits).
- Priorité de rattachement : **`ToRoom` > `FromRoom`** (inversé suite à un bug
  diagnostiqué le 2026-09-14 : une porte avec un `FromRoom` correct était mal
  placée — la logique a été changée pour prioriser `ToRoom`)
- Si aucun des deux : positionnement par sens horaire depuis un repère
  **sélectionné par l'utilisateur dans la vue** (à l'origine un paramètre fixe
  lié à la famille `M360_Entry 2`, changé en élément sélectionnable)
- Si plusieurs portes dans une même room à partir du `FromRoom`/`ToRoom` :
  respecter le sens horaire à partir de la dernière porte déjà incrémentée
- UI : fenêtre de preview WPF, tableau avec ID des portes, réordonnancement par
  **drag-and-drop** (l'ancien système monter/descendre a été abandonné)
- Flux : sélection du point de repère d'abord → calcul ensuite (pas l'inverse)

Bugs connus non résolus en fin de dernière session :
- Le drag-and-drop ne scrolle pas dans le tableau
- Le bouton "Appliquer" est perçu comme lent (cause pas diagnostiquée)

### Numbering.panel / Window Numbering (Beta).pushbutton (`lib/wbm_numbering/window_numbering.py`)

**Cassé.** Dernière erreur connue (2026-09-14) :
```
ImportError: Cannot import name find_entry_point
  File "...Window Numbering (Beta).pushbutton\preview_window.py", line 17
```
Le module a été construit par analogie avec Door Numbering (fenêtre de preview,
sélection du point de repère dans la vue, calcul, drag-and-drop) mais un import
cassé empêche l'exécution. **Non corrigé** — c'est le point bloquant prioritaire
identifié pour la suite.

### Room Numbering

Évoqué (même logique de règles que pour les portes/fenêtres), un plan de
reproduction a été esquissé mais le sujet a été **mis en pause avant d'être
commencé**. Rien d'implémenté.

### Génération de remarques BCF

**Prototype validé, pas encore packagé en commande pyRevit.** Fait via
`execute_revit_code` (MCP `Revit_Connector`), pas encore dans ce repo :
- Génère un `.bcf` compatible BIMcollab avec capture d'image + commentaire
- Capture liée à la vue (zoom + cadrage) — un bug d'unités (pieds vs mètres)
  a été rencontré et corrigé pendant les tests
- **Limite confirmée** : impossible de conserver la sélection d'éléments dans
  le `.bcf` nativement — BIMcollab en 2D ne lit pas le bloc `<Selection>` du
  `.bcfv`. Contournements proposés : ID dans le commentaire, ou un lecteur BCF
  maison côté pyRevit (bouton qui relit le `.bcfv` et refait zoom + sélection)

Architecture cible validée avec l'utilisateur pour l'industrialiser :
- `lib/wbm_bcf/` — module réutilisable : capture (zoom sur bbox + export
  image), construction markup/viewpoint (**en pieds**), écriture du zip,
  récupération automatique de l'IFC GUID
- `WBM.tab/QC.panel/GenererBCF.pushbutton/` — `script.py` (orchestration) +
  `InputWindow.xaml` (3 champs : ID ou sélection courante, titre, commentaire)
  + `input_window.py` (code-behind)

**Pas encore implémenté** — la session s'est arrêtée juste avant de s'y mettre.

### Agent IA de contrôle complet de maquette (skill Claude Code)

Idée explorée : un agent qui lit un référentiel de règles (MD + fichiers
d'appui), parcourt une maquette Revit ouverte, détecte les écarts, produit un
`.bcf` consolidé (plusieurs `Markup` dans un même zip).

Verdict de faisabilité (2026-09-17) : **oui, faisable**, avec réserves :
- **Claude Code, pas Cowork/cloud** — le contrôle dépend d'un Revit ouvert en
  local piloté par le MCP `Revit_Connector` ; un sandbox cloud n'y a pas accès
- Le noyau technique (lecture éléments/paramètres, capture, écriture BCF) est
  déjà validé — c'est un travail d'ingénierie (écrire/généraliser les règles),
  pas un blocage de faisabilité
- Points de vigilance : pas de run headless sans Revit ouvert localement (sauf
  Design Automation Autodesk, hors écosystème Claude, payant à part) ; le
  compte Claude Pro ne synchronise pas les skills/règles entre postes
  (distribution à organiser via ce repo git) ; agréger les contrôles côté
  IronPython plutôt qu'itérer élément par élément côté agent (coût token) ;
  contrôles "subjectifs" (jugement visuel) moins fiables que les contrôles
  déterministes, prévoir une relecture humaine ; bien verrouiller
  `execute_revit_code` en lecture seule pour un agent de contrôle (jamais de
  Transaction ouverte par erreur) ; plan Pro probablement insuffisant pour un
  usage agentique régulier/planifié (Max/Team recommandé)
- Piste recommandée : empaqueter en skill Claude Code partagé via ce repo (MD
  de règles + lib Python de contrôles réutilisables + générateur BCF corrigé),
  lancé par chaque ingénieur via une commande type `/controle-revit`

## Priorités pour la suite (à date du 2026-09-17)

1. Corriger le bug bloquant de **Window Numbering** (`find_entry_point`)
2. Packager le générateur **BCF** en commande pyRevit (`lib/wbm_bcf/` +
   `QC.panel/GenererBCF.pushbutton/`)
3. Démarrer **Room Numbering** (mis en pause, jamais commencé)
4. Construire le skill Claude Code de contrôle complet de maquette
