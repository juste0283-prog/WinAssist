# WinAssist

Assistant **vocal agentique** pour Windows, pensé en priorité pour des
utilisateurs en situation de handicap (personnes aveugles ou sans mains),
mais utilisable par tout le monde.

L'objectif : **contrôler intégralement un PC Windows à la voix**, sans
limitation à une liste fixe de commandes. L'assistant observe l'écran
comme un humain (arbre UI Automation, puis vision en secours), décide à
chaque pas d'**une seule action** à exécuter, et boucle jusqu'à la
réalisation de la tâche.

Ce dépôt contient les points 1 et 2 du plan de développement :
- **point 1** — la boucle `perception → décision → action`, testable en local ;
- **point 2** — la boucle vocale de bout en bout (« OK WinAssist, ouvre le
  bloc-notes » → action + retour vocal).

---

## 1. Vision d'architecture (rappel des 6 briques)

| # | Brique | Rôle | Statut |
|---|--------|------|--------|
| 1 | **Entrée vocale (STT)** | Whisper + repli Vosk, mot d'activation | ✅ implémenté |
| 2 | **Perception de l'écran** | Arbre UIA de la fenêtre active (+ repli vision) | ✅ UIA + vision |
| 3 | **Boucle agentique** | Décision → action → observation, avec garde-fous | ✅ implémenté |
| 4 | **Exécution des actions** | Primitives universelles + raccourcis système | ✅ clics/clavier + raccourcis |
| 5 | **Retour vocal (TTS)** | Confirmation orale, descriptions, erreurs | ✅ pyttsx3 + edge-tts |
| 6 | **Sécurité** | Confirmation avant actions sensibles, journal, interruption | ✅ confirmations + journal |

---

## 2. Structure du projet

```
winassist/
├── core/                      # le cœur transversé
│   ├── models.py              #   modèles Pydantic : écran + actions
│   ├── context.py             #   DecisionContext (le "paquet" remis à l'IA)
│   ├── history.py             #   journal des actions + détection de blocage
│   ├── security.py            #   garde-fous : actions sensibles + confirmation
│   ├── journal.py             #   journal de session JSONL, réécoutable
│   └── loop.py                #   LA boucle agentique (perception→décision→action)
├── perception/                # "voir" l'écran
│   └── uia.py                 #   extraction de l'arbre UI Automation (Win10/11)
│   └── vision.py              #   repli vision : capture + modèle multimodal
├── decision/                  # "réfléchir"
│   ├── base.py                #   interfaces DecisionProvider / DecisionContext
│   ├── mock.py                #   cerveau local à règles (démo, tests)
│   └── llm_client.py          #   cerveau LLM compatible OpenAI (function calling)
├── actions/                   # "agir"
│   ├── executor.py            #   exécution souris/clavier (pyautogui)
│   └── quick_actions.py       #   raccourcis système : apps, volume, corbeille, fond d'écran
├── io/                        # entrées/sorties audio/vocales
│   ├── tts.py                 #   synthèse vocale (pyttsx3 + edge-tts)
│   ├── stt.py                 #   STT : Whisper API / local / Vosk
│   ├── wake.py                #   mot d'activation (pur texte, testable)
│   ├── audio.py               #   micro + détection de voix (VAD)
│   ├── listener.py            #   écoute continue + interruption vocale
│   ├── voice_loop.py          #   session vocale complète
│   └── interrupt.py           #   arrêt d'urgence clavier (ECHAP)
├── config.py                  # config via variables d'environnement (.env)
├── demo.py                    # démo console : `python -m winassist.demo`
└── voice.py                   # démarrage vocal : `python -m winassist.voice`

scripts/download_models.py     # télécharge les modèles STT locaux (whisper/vosk)
tests/                         # tests unitaires (aucun écran/réseau requis)
requirements.txt
.env.example                   # modèle de configuration (copier vers .env)
```

### Comment ça fonctionne (la boucle, `core/loop.py`)

```
1. Capter l'écran ............ perception.UIA_Perception.capture()
2. Décider UNE action ........ decision.<mock|llm>.decide()
3. Résoudre element_id
   -> coordonnées écran ...... core/loop._resolve()
4. Exécuter ................. actions.executor.execute()
5. Journaliser + vérifier
   blocages ................. core/history (anti-boucle, anti-répétition)
6. Recapter, recommencer ..... jusqu'à `done` / limite / blocage
```

**Gardes-fous intégrés** :
- **Limite d'itérations** (`WINASSIST_MAX_ITERATIONS`, défaut 12) ;
- **Détection de stagnation** : si l'écran ne change plus pendant
  `WINASSIST_STAGNATION_LIMIT` actions (défaut 3) → arrêt ;
- **Anti-répétition** : une action strictement identique à la précédente
  est refusée ;
- **Failsafe pyautogui** : souris dans le coin haut-gauche de l'écran =
  arrêt d'urgence immédiat.

---

## 3. Installation

```powershell
python -m pip install -r requirements.txt
# python 3.13+ recommandé (testé avec 3.13.1)
```

---

## 4. Essayer le prototype (mode local, sans clé API)

Le mode par défaut utilise le **mock** (cerveau à règles locales, zéro
réseau). Lance la démo interactive :

```powershell
python -m winassist.demo
```

Puis essaye, dans l'ordre :

```
> ouvre le bloc-notes          # ouvre Notepad via raccourci système
> tape bonjour                 # saisit le texte dans Notepad
> monte le volume              # raccourci système direct (volume)
> change le fond d'écran en bleu  # raccourci système direct (fond d'écran)
> ouvre mes documents          # ouvre le dossier Documents
> écran                        # montre ce que l'assistant "voit" (UIA)
> décris                       # décrive l'écran en français (voix/vision)
> valide
> quitter
```

Ou avec une commande directe :

```powershell
python -m winassist.demo "ouvre le bloc-notes"
```

Le **retour vocal** est activé par défaut (`WINASSIST_TTS=1`) : chaque
étape est annoncée à voix haute. Coupe-le avec `WINASSIST_TTS=0` si besoin.

### Passer au vrai LLM (optionnel)

Crée un fichier `.env` (copie de `.env.example`), puis :

```env
WINASSIST_LLM_MODE=openai
# Option A — API OpenAI :
WINASSIST_API_KEY=sk-...
# Option B — serveur local (Ollama par ex.) :
# WINASSIST_API_BASE_URL=http://localhost:11434/v1
# WINASSIST_MODEL=llama3.2
```

Sans clé ni serveur local, le programme **bascule automatiquement sur le
mock** pour rester utilisable.

---

## 4bis. Contrôler à la voix (point 2)

### 1. Préparer un moteur STT (au choix)

```powershell
# Option A — Whisper local hors-ligne (recommandé) :
python -m pip install faster-whisper
python scripts/download_models.py --whisper base

# Option B — Whisper via API (clé OpenAI ou serveur compatible) :
#   renseigne WINASSIST_API_KEY dans .env

# Option C — Vosk hors-ligne léger :
# python -m pip install vosk
# python scripts/download_models.py --vosk
#   puis WINASSIST_VOSK_MODEL_PATH=models/vosk-small-fr dans .env
```

Sans aucun moteur installé, `python -m winassist.voice` affiche une
erreur claire et te renvoie vers la démo console.

### 2. Lancer l'assistant vocal

```powershell
python -m winassist.voice
```

Puis, au micro :

```
"OK WinAssist, ouvre le bloc-notes"
"OK WinAssist, tape bonjour"
"arrête"              # stoppe la tâche en cours
"au revoir"           # quitte la session
```

Le **mot d'activation** évite d'exécuter des phrases entendues au hasard.
Pendant l'exécution d'une tâche, une **interruption vocale** (« arrête »)
ou la touche **Échap** arrêtent la boucle immédiatement.

### Sécurité intégrée (point 5)

- Les actions **sensibles** (« vide la corbeille », « éteins le PC »...)
  demandent une **confirmation vocale** (« Confirme avec oui, ou dis
  non »). Sans confirmation, elles sont refusées d'office.
- Chaque session écrit un **journal** dans `logs/` (JSON Lines) : dic
  « lit le journal » pour réécouter la session (`WINASSIST_JOURNAL=0` pour
  couper).

### TTS au choix

- `WINASSIST_TTS_ENGINE=pyttsx3` : voix locale Windows (défaut, sans réseau).
- `WINASSIST_TTS_ENGINE=edge` : voix Edge naturelle via internet
  (`WINASSIST_EDGE_VOICE=fr-FR-EloiseNeural`).

---

## 4ter. Repli vision (point 3)

Quand l'arbre UIA ne voit aucun élément interactif nommé (jeux, canvas,
vieilles applications), la perception bascule automatiquement sur une
**analyse d'image** : capture d'écran (mss) envoyée à un modèle multimodal
(`WINASSIST_VISION_MODEL`, par défaut le modèle de décision). La commande
`décris` décrit l'écran en français pour la voix.

Exigence : un modèle multimodal (ex. `gpt-4o-mini`) avec
`WINASSIST_LLM_MODE=openai` et `WINASSIST_API_KEY`. Sans cela, le repli
vision est simplement contourné et on garde la vue UIA.

---

## 5. Tester le code

```powershell
python -m unittest discover -s tests -v
```

Les tests sont **déterministes** : ils injectent de faux composants
(écran simulé, cerveau scripté, main enregistreuse, micro simulé) —
aucun clic réel, aucun accès réseau, aucun micro nécessaire.

---

## 6. Et maintenant ? (points suivants, dans l'ordre)

1. ✅ **Boucle perception→décision→action** ;
2. ✅ **Voix de bout en bout** — STT (Whisper/Vosk) + mot d'activation +
   TTS + interruption vocale ;
3. ✅ **Repli vision** — quand UIA ne voit rien : capture d'écran + modèle
   multimodal, description de l'écran en français pour la voix
   (`perception/vision.py`, commande `décris`) ;
4. ✅ **Raccourcis système** — volume, verrouillage, Bureau, corbeille,
   fond d'écran, dossiers personnels (`actions/quick_actions.py`, action
   `SystemAction` ; les raccourcis sensibles sont déjà déclarés pour la
   sécurité) ;
5. ✅ **Fiabilité & confort** — confirmation vocale avant action
   destructrice, journal écoutable (« lit le journal »), interruption
   vocale et touche Échap (`core/security.py`, `core/journal.py`) ;
6. ⏳ **Scénarios multi-étapes réels** (ex. « ouvre WhatsApp et lance la
   discussion avec maman »).

## 7. Sécurité — bonnes pratiques

- Ne **jamais** committer de clé API : tout passe par `.env` (ignoré par git).
- Le failsafe par défaut est **activé** : ne le désactive que si tu sais
  ce que tu fais (`WINASSIST_FAILSAFE=0`).
- Les actions destructives nécessiteront une confirmation vocale
  (point 5) — prévu dans la conception, mais pas encore implémenté.