/* Commun aux deux pages : i18n FR/EN, bascule de langue, helpers DOM sûrs (aucun innerHTML). */
(() => {
  "use strict";

  const I18N = {
    fr: {
      "nav.home": "Accueil", "nav.salle": "La salle",
      "footer.text": "Corpus du domaine public (Art Institute of Chicago, Wikimedia Commons) · Propulsé par Cohere",
      "hero.kicker": "Visite nocturne",
      "hero.title": "Dis-moi ce que tu vois dans ce tableau",
      "hero.sub": "Envoie la photo d'un tableau : analyse, œuvres proches et explications sourcées.",
      "drop.title": "Glisse un tableau ici", "drop.or": "ou clique pour choisir un fichier",
      "drop.hint": "JPEG, PNG ou WebP · 5 Mo max", "drop.change": "Changer d'image",
      "level.label": "Niveau d'explication", "level.beginner": "Débutant", "level.enthusiast": "Passionné", "level.expert": "Expert",
      "btn.analyze": "Analyser le tableau", "btn.busy": "Analyse en cours…",
      "stage.vision": "Observation du tableau…",
      "stage.similar": "Recherche des œuvres proches, classement et rédaction de l'explication…",
      "analysis.title": "Ce que je vois",
      "field.movement": "Mouvement", "field.period": "Période", "field.technique": "Technique", "field.artist": "Artiste probable",
      "conf.low": "confiance faible", "conf.medium": "confiance moyenne", "conf.high": "confiance élevée",
      "artist.unknown": "inconnu",
      "similar.title": "Œuvres proches",
      "similar.sub": "Trouvées dans le corpus du domaine public par similarité d'embeddings, puis re-classées.",
      "card.cosine": "cosinus", "card.rerank": "rerank", "card.source": "Source", "card.license": "Licence",
      "card.rank.up": "▲ {n} place(s) gagnée(s) au rerank", "card.rank.down": "▼ {n} place(s) perdue(s) au rerank",
      "card.rank.same": "Position inchangée", "card.rank.new": "Entrée au top 5 grâce au rerank (était n°{n})",
      "card.noimg": "Image indisponible",
      "ba.title": "Avant / après rerank", "ba.before": "Embeddings seuls", "ba.after": "Après rerank",
      "ba.same": "Le rerank n'a pas changé le top 5.", "ba.changed": "Le rerank a modifié le top 5 ({n} changement(s) de position).",
      "ba.skipped": "Rerank indisponible : ordre des embeddings conservé.",
      "ground.title": "Pourquoi ces œuvres se ressemblent",
      "ground.note": "Explication limitée aux métadonnées du corpus. Les passages soulignés sont des citations renvoyées par l'API.",
      "ground.cites": "Citations : {n}",
      "timing.title": "Pipeline",
      "step.vision": "Vision", "step.embed": "Embedding", "step.search": "Recherche", "step.rerank": "Rerank", "step.grounding": "Grounding",
      "history.title": "Dernières analyses", "history.clear": "Effacer l'historique", "history.empty": "Aucune analyse pour l'instant.",
      "history.noimage": "Image non conservée (traitée en mémoire uniquement)",
      "banner.nokey": "Aucune clé Cohere détectée : ajoutez COHERE_API_KEY dans le fichier .env puis relancez python main.py.",
      "banner.nocorpus": "Le corpus n'est pas encore construit : lancez python build_corpus.py (l'analyse fonctionne, mais sans œuvres proches).",
      "err.type": "Format non pris en charge. Envoie une image JPEG, PNG ou WebP.",
      "err.size": "Image trop lourde : 5 Mo maximum.",
      "err.network": "Impossible de joindre le serveur. Vérifie que python main.py tourne toujours.",
      "err.timeout": "Le délai est dépassé. Réessaie dans un instant.",
      "err.generic": "Une erreur inattendue s'est produite. Réessaie.",
      "err.noimage": "Choisis d'abord une image.",
      "salle.kicker": "Salle des mouvements", "salle.title": "Le corpus, par mouvement",
      "salle.sub": "Projection 2D (PCA) des embeddings : les œuvres proches se regroupent.",
      "salle.empty": "Le corpus est vide. Lancez d'abord : python build_corpus.py",
      "salle.maptitle": "Carte des œuvres du corpus (PCA des embeddings)",
      "salle.mapdesc": "Chaque point est une peinture, colorée par mouvement.",
      "salle.legend": "Mouvements", "salle.reset": "Tout afficher", "salle.bymov": "Œuvres par mouvement",
      "salle.meta": "{n} œuvres · variance expliquée : axe 1 {a} %, axe 2 {b} %",
      "salle.works": "œuvres",
    },
    en: {
      "nav.home": "Home", "nav.salle": "The gallery",
      "footer.text": "Public-domain corpus (Art Institute of Chicago, Wikimedia Commons) · Powered by Cohere",
      "hero.kicker": "Night visit",
      "hero.title": "Tell me what you see in this painting",
      "hero.sub": "Upload a photo of a painting: analysis, similar works and sourced explanations.",
      "drop.title": "Drop a painting here", "drop.or": "or click to choose a file",
      "drop.hint": "JPEG, PNG or WebP · 5 MB max", "drop.change": "Change image",
      "level.label": "Explanation level", "level.beginner": "Beginner", "level.enthusiast": "Enthusiast", "level.expert": "Expert",
      "btn.analyze": "Analyse the painting", "btn.busy": "Analysing…",
      "stage.vision": "Looking at the painting…",
      "stage.similar": "Finding similar works, ranking them and writing the explanation…",
      "analysis.title": "What I see",
      "field.movement": "Movement", "field.period": "Period", "field.technique": "Technique", "field.artist": "Likely artist",
      "conf.low": "low confidence", "conf.medium": "medium confidence", "conf.high": "high confidence",
      "artist.unknown": "unknown",
      "similar.title": "Similar works",
      "similar.sub": "Found in the public-domain corpus by embedding similarity, then re-ranked.",
      "card.cosine": "cosine", "card.rerank": "rerank", "card.source": "Source", "card.license": "License",
      "card.rank.up": "▲ up {n} place(s) after rerank", "card.rank.down": "▼ down {n} place(s) after rerank",
      "card.rank.same": "Position unchanged", "card.rank.new": "Entered the top 5 thanks to rerank (was #{n})",
      "card.noimg": "Image unavailable",
      "ba.title": "Before / after rerank", "ba.before": "Embeddings only", "ba.after": "After rerank",
      "ba.same": "Rerank did not change the top 5.", "ba.changed": "Rerank changed the top 5 ({n} position change(s)).",
      "ba.skipped": "Rerank unavailable: embedding order kept.",
      "ground.title": "Why these works look alike",
      "ground.note": "Explanation limited to the corpus metadata. Underlined passages are citations returned by the API.",
      "ground.cites": "Citations: {n}",
      "timing.title": "Pipeline",
      "step.vision": "Vision", "step.embed": "Embedding", "step.search": "Search", "step.rerank": "Rerank", "step.grounding": "Grounding",
      "history.title": "Recent analyses", "history.clear": "Clear history", "history.empty": "No analysis yet.",
      "history.noimage": "Image not kept (processed in memory only)",
      "banner.nokey": "No Cohere key found: add COHERE_API_KEY to the .env file, then restart python main.py.",
      "banner.nocorpus": "The corpus is not built yet: run python build_corpus.py (analysis works, but without similar works).",
      "err.type": "Unsupported format. Please upload a JPEG, PNG or WebP image.",
      "err.size": "Image too large: 5 MB maximum.",
      "err.network": "Cannot reach the server. Check that python main.py is still running.",
      "err.timeout": "Timed out. Please try again in a moment.",
      "err.generic": "An unexpected error occurred. Please try again.",
      "err.noimage": "Choose an image first.",
      "salle.kicker": "Movements gallery", "salle.title": "The corpus, by movement",
      "salle.sub": "2D projection (PCA) of the embeddings: similar works cluster together.",
      "salle.empty": "The corpus is empty. First run: python build_corpus.py",
      "salle.maptitle": "Map of the corpus artworks (PCA of embeddings)",
      "salle.mapdesc": "Each dot is a painting, coloured by movement.",
      "salle.legend": "Movements", "salle.reset": "Show all", "salle.bymov": "Works by movement",
      "salle.meta": "{n} works · explained variance: axis 1 {a}%, axis 2 {b}%",
      "salle.works": "works",
    },
  };

  const MOVEMENTS_FR = {
    "Impressionism": "Impressionnisme", "Post-Impressionism": "Post-impressionnisme", "Realism": "Réalisme",
    "Baroque": "Baroque", "Neoclassicism": "Néoclassicisme", "Renaissance": "Renaissance", "Mannerism": "Maniérisme",
    "Romanticism": "Romantisme", "Expressionism": "Expressionnisme", "Cubism": "Cubisme", "Art Nouveau": "Art nouveau",
  };

  const boot = JSON.parse(document.getElementById("boot").textContent);
  const state = { lang: boot.prefs.lang === "en" ? "en" : "fr", listeners: [] };

  function t(key, vars) {
    let s = (I18N[state.lang] && I18N[state.lang][key]) || I18N.fr[key] || key;
    if (vars) for (const k of Object.keys(vars)) s = s.replace("{" + k + "}", vars[k]);
    return s;
  }

  function movementLabel(name) {
    return state.lang === "fr" ? MOVEMENTS_FR[name] || name : name;
  }

  function applyI18n() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll(".flag").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang));
    });
  }

  async function setLang(lang) {
    if (lang === state.lang) return;
    state.lang = lang;
    applyI18n();
    state.listeners.forEach((fn) => fn(lang));
    try {
      await fetch("/api/settings", {
        method: "PUT",
        keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang }),
      });
    } catch (_) { /* préférence non critique */ }
  }

  /** Crée un élément ; les chaînes sont TOUJOURS insérées via textContent. */
  function el(tag, opts, ...children) {
    const node = document.createElement(tag);
    if (opts) {
      if (opts.class) node.className = opts.class;
      if (opts.text != null) node.textContent = String(opts.text);
      if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
    }
    for (const c of children) if (c) node.append(c);
    return node;
  }

  /** Les métadonnées externes sont non fiables : seules les URLs http(s) sont acceptées. */
  function safeUrl(u) {
    try {
      const url = new URL(u, location.origin);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch (_) { return null; }
  }

  function fmtMs(ms) {
    return ms >= 1000 ? (ms / 1000).toFixed(1) + " s" : Math.round(ms) + " ms";
  }

  document.querySelectorAll(".flag").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  applyI18n();

  window.Musee = {
    boot, state, t, el, safeUrl, fmtMs, movementLabel, applyI18n, setLang,
    onLang: (fn) => state.listeners.push(fn),
  };
})();
