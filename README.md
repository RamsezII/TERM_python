# Unity TERM client

## Lancer depuis Python

```text
python term_client.py
```

Au premier build, le projet crée automatiquement un environnement Python isolé
dans `.venv` et y installe uniquement ses dépendances. VS Code détecte ce dossier
et l'utilise comme interpréteur par défaut.

Pour activer manuellement cet environnement dans un autre terminal :

```text
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux
source .venv/bin/activate
```

La commande `deactivate` permet ensuite de quitter l'environnement.

## Construire l'exécutable

```text
python build.py
```

Cette commande crée `.venv` si nécessaire, installe les dépendances de build puis
se relance automatiquement avec le Python isolé. Les paquets installés globalement
sur la machine ne sont donc pas inclus accidentellement dans l'exécutable.

Le résultat est `dist/unity-term.exe` sous Windows et `dist/unity-term.x86_64` sous Linux.
PyInstaller construit pour le système sur lequel il est lancé : il faut donc exécuter
le script une fois sous Windows et une fois sous Linux pour produire les deux versions.

Pour un build plus facile à inspecter pendant le débogage :

```text
python build.py --onedir
```

Dans l'éditeur Unity, le lanceur utilise le binaire correspondant à la plateforme
dans `Assets/_TERM_/Editor/Binaries`. Lors du build du jeu, le postprocesseur Unity
copie automatiquement ce binaire dans le dossier d'outils attendu par le jeu.
