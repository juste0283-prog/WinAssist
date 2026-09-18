# WinAssist

Assistant **vocal agentique** pour Windows, pensé en priorité pour des
utilisateurs en situation de handicap (personnes aveugles ou sans mains),
mais utilisable par tout le monde.

L'objectif : **contrôler intégralement un PC Windows à la voix**, sans
limitation à une liste fixe de commandes. L'assistant observe l'écran
comme un humain (arbre UI Automation, puis vision en secours), décide à
chaque pas d'**une seule action** à exécuter, et boucle jusqu'à la
réalisation de la tâche.

Ce dépôt contient le **prototype du point 1** du plan de développement :
la boucle `perception → décision → action`, testable en local.

---

## 1. Vision d'architecture (rappel des 6 briques)

| # | Brique | Rôle | Statut |
|---|--------|------|--------|
| 1 | **Entrée vocale (STT)** | Whisper + repli Vosk, mot d'activation | *point 2* |
| 2 | **Perception de l'écran** | Arbre UIA de la fenêtre active (+ repli vision) | ✅ UIA / *vision point 3* |
| 3 | **Boucle agentique** | Décision → action → observation, avec garde-fous | ✅ implémenté |
| 4 | **Exécution des actions** | Primitives universelles + raccourcis système | ✅ clics/clavier / *raccourcis point 4* |
| 5 | **Retour vocal (TTS)** | Confirmation orale, descriptions, erreurs | ✅ TTS local (pyttsx3) |
| 6 | **Sécurité** | Confirmation avant actions sensibles, journal, interruption | *point 5* |

---

## 2. Structure du projet

```
winassist/
├── core/                      # le cœur transversé
│   ├── models.py              #   modèles Pydantic : écran + actions
│   ├── history.py             #   journal des actions + détection de blocage
│   └── loop.py                #   LA boucle agentique (perception→décision→action)
├── perception/                # "voir" l'écran
│   └── uia.py                 #   extraction de l'arbre UI Automation (Win10/11)
│   └── vision.py              #   repli vision (placeholder, point 3)
├── decision/                  # "réfléchir"
│   ├── base.py                #   interfaces DecisionProvider / DecisionContext
│   ├── mock.py                #   cerveau local à règles (démo, tests)
│   └── llm_client.py          #   cerveau LLM compatible OpenAI (function calling)
├── actions/                   # "agir"
│   ├── executor.py            #   exécution souris/clavier (pyautogui)
│   └── quick_actions.py       #   raccourcis système : ouverture d'apps
├── io/                        # entrées/sorties audio
│   ├── tts.py                 #   synthèse vocale (pyttsx3) — opérationnelle
│   └── stt.py                 #   reconnaissance vocale (point 2)
├── config.py                  # config via variables d'environnement (.env)
└── demo.py                    # démo console : `python -m winassist.demo`

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
> écran                        # montre ce que l'assistant "voit" (UIA)
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

## 5. Tester le code

```powershell
python -m unittest discover -s tests -v
```

Les tests sont **déterministes** : ils injectent de faux composants
(écran simulé, cerveau scripté, main enregistreuse) — aucun clic réel,
aucun accès réseau.

---

## 6. Et maintenant ? (points suivants, dans l'ordre)

1. ✅ **Boucle perception→décision→action** (ce prototype) ;
2. ⏳ **STT/TTS de bout en bout** — suivre la voix : Whisper/Vosk + le TTS
   déjà branché (, fichiers `io/stt.py` à compléter) ;
3. ⏳ **Repli vision** — quand l'arbre UIA est vide :
   capture d'écran + modèle multimodal (`perception/vision.py`) ;
4. ⏳ **Raccourcis système** — volume, corbeille, fond d'écran...
   (`actions/quick_actions.py`) ;
5. ⏳ **Fiabilité & confort** — confirmations avant action destructrice,
   journal écoutable, interruption vocale ;
6. ⏳ **Scénarios multi-étapes réels** (ex. « ouvre WhatsApp et lance la
   discussion avec maman »).

## 7. Sécurité — bonnes pratiques

- Ne **jamais** committer de clé API : tout passe par `.env` (ignoré par git).
- Le failsafe par défaut est **activé** : ne le désactive que si tu sais
  ce que tu fais (`WINASSIST_FAILSAFE=0`).
- Les actions destructives nécessiteront une confirmation vocale
  (point 5) — prévu dans la conception, mais pas encore implémenté.