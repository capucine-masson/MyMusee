# Musée IA — « Dis-moi ce que tu vois dans ce tableau »

Envoyez la photo d'un tableau : un modèle vision de Cohere en explique le mouvement, la technique et le contexte, puis
l'application propose des œuvres proches d'un petit corpus du domaine public (embeddings, puis rerank) et justifie
chaque rapprochement par des **citations** limitées aux métadonnées du corpus.

![Page d'accueil de Musée IA](apercu/1.png)

## Lancer le projet (Windows, Python 3.10+)

```powershell
pip install -r requirements.txt
copy .env.example .env          # puis renseigner COHERE_API_KEY
python -m app.cohere_svc       # vérifie que la clé fonctionne (~5 tokens)
python -m scripts.build_corpus  # construit le corpus (~230 peintures) + embeddings, reprenable
python -m app                  # http://127.0.0.1:8000
```

Optionnel :

```powershell
python -m scripts.neighbors mon_tableau.jpg   # test isolé : 5 plus proches voisins + scores
python -m scripts.eval                        # precision@5 : embeddings seuls vs embeddings + rerank
```

`build_corpus` est idempotent : après un quota 429 ou un Ctrl-C, relancez-le, il ne traite que ce qui manque.
`--scale 0.2` construit un mini corpus de test.

## Architecture

```mermaid
flowchart LR
    U[Navigateur<br/>HTML/Jinja2 + JS] -->|POST /api/analyze| V[Command A Vision<br/>JSON structuré]
    V --> H[(SQLite<br/>history)]
    U -->|POST /api/similar| E[Embed v4<br/>image → vecteur]
    E --> S[numpy<br/>cosinus top 20]
    C[(SQLite artworks<br/>embeddings)] --> S
    S --> R[Rerank v4<br/>requête = description vision]
    R --> G[Command A + documents<br/>explication + citations]
    G --> H
    B[build_corpus.py] --> C
    AIC[Art Institute of Chicago] --> B
    WD[Wikidata + Commons] --> B
```

Deux requêtes : l'analyse s'affiche dès qu'elle est prête, puis arrivent les œuvres proches. Si le rerank ou le
grounding échoue, l'application dégrade proprement (ordre des embeddings, pas d'explication citée) et affiche un
message clair.

| Étape | Modèle Cohere (surchargeable via `COHERE_MODEL_*` dans `.env`) |
|---|---|
| Analyse du tableau | `command-a-vision-07-2025` (chat v2, sortie JSON schema) |
| Embeddings image | `embed-v4.0` |
| Re-classement | `rerank-v4.0-pro` |
| Explication groundée | `command-a-03-2025` (chat v2 avec `documents` → citations) |

SDK `cohere` 7.x (`ClientV2`). Le modèle d'embedding est stocké avec chaque vecteur : changer `COHERE_MODEL_EMBED` puis
relancer `python -m scripts.build_corpus` ré-embarque tout, sans jamais mélanger deux espaces vectoriels.

## Corpus

~230 peintures du domaine public, 11 mouvements, source et licence affichées sur chaque carte.

* **Art Institute of Chicago** : impressionnisme, post-impressionnisme, réalisme, baroque, néoclassicisme,
  Renaissance, maniérisme.
* **Wikidata + Wikimedia Commons** : romantisme, expressionnisme, cubisme, art nouveau (artiste mort avant 1955 et
  licence Commons vérifiée). Cette source comble les mouvements absents d'AIC une fois filtré sur le domaine public.

## Choix techniques

* **FastAPI + Jinja2 + JS sans framework** : application légère, pas de build front.
* **SQLite (`sqlite3`, requêtes paramétrées, sans ORM)** : `artworks`, `history`, `settings`. L'historique ne garde que
  les métadonnées et le résultat, jamais l'image.
* **Recherche vectorielle en numpy** : 230 vecteurs ≈ 1,5 Mo, une base vectorielle n'apporterait que de la complexité
  (pgvector/Qdrant se justifient vers 10⁵ vecteurs).
* **Analyse structurée** (JSON schema), avec repli « JSON libre + extraction ». Le champ `is_painting` gère les
  photos non pertinentes ; artiste et mouvement portent un niveau de confiance, « inconnu » est une réponse valide.
* **Grounding en appel séparé** : `response_format` n'est pas compatible avec `documents`. L'explication ne peut citer
  que les métadonnées fournies.
* **Rerank sur texte** : documents = métadonnées des œuvres, requête = description visuelle du modèle vision. C'est
  une passerelle texte ↔ métadonnées, pas un correcteur de similarité visuelle.
* **Image traitée en mémoire** (Pillow : validation, redimensionnement), jamais écrite sur disque.
* **Proxy d'images `/art/{id}`** : l'URL est lue en base (pas d'URL client, donc pas de SSRF) et l'image est mise en
  cache ; la CSP reste `img-src 'self'`.

## Sécurité

Clé dans `.env` (ignoré par git) et jamais exposée au front · CSP stricte, `nosniff`, `no-referrer` · aucun
`innerHTML` côté JS, métadonnées externes traitées comme non fiables · upload limité à 5 Mo, type vérifié sur le
contenu réel · timeouts et backoff sur 429/5xx · erreurs lisibles, jamais de stacktrace.

## Évaluation

Leave-one-out sur le corpus (232 œuvres) : precision@5 sur le **même mouvement** (`python -m scripts.eval`, résultats dans
`data/eval_results.json`, une seule exécution le 2026-10-05).

| Méthode | precision@5 | hors même artiste |
|---|---|---|
| Hasard | 0,099 | 0,099 |
| Embeddings seuls | 0,491 | 0,405 |
| Embeddings + rerank, documents sans mouvement (échantillon de 61) | 0,433 | 0,393 |
| Embeddings + rerank, avec mouvement — utilisé par l'app (échantillon de 61) | 0,515 | 0,459 |

Les embeddings captent bien le style (≈ 5× le hasard). Le gain du rerank vient surtout du mouvement écrit dans les
documents, pas d'une meilleure « vision ».

## Limites

* Étiquettes de mouvement issues des sources (bruitées), pas d'un historien de l'art.
* Corpus petit et déséquilibré (5 œuvres en maniérisme, 30 en impressionnisme).
* Embedding sensible au cadrage des photos (reflets, cadre, angle).
* L'identification d'artiste est une estimation.

## Arborescence

```
app/                    le serveur et ses services
  main.py               FastAPI : routes, erreurs, CSP, proxy d'images
  cohere_svc.py         vision · embeddings · rerank · grounding
  search.py             cosinus numpy + PCA 2D
  db.py · config.py · i18n.py · imaging.py
  templates/ static/    interface (Jinja2, CSS, JS)
scripts/                outils en ligne de commande
  build_corpus.py       AIC + Wikidata/Commons → artworks → embeddings
  neighbors.py          test isolé : image → 5 voisins
  eval.py               precision@5 : embeddings vs rerank
data/                   musee.db et caches (non versionnés), résultats d'évaluation
```

## Aperçu

**Analyse du tableau** : mouvement, période, technique et artiste probable, chacun avec un niveau de confiance.

![Analyse du tableau par le modèle vision](apercu/2.png)

**Œuvres proches** : scores d'embedding (cosinus) et de rerank pour chaque œuvre du corpus.

![Œuvres proches du corpus](apercu/3.png)

**Salle des mouvements** : projection 2D (PCA) du corpus, colorée par mouvement.

![Carte du corpus par mouvement](apercu/4.png)

Survol d'un point : titre, artiste, année et mouvement de l'œuvre.

![Détail d'une œuvre au survol de la carte](apercu/5.png)
