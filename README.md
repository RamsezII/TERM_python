# Unity TERM client

## Lancer depuis Python

```text
python -m pip install -r requirements.txt
python term_client.py
```

## Construire l'exécutable

```text
python -m pip install -r requirements-build.txt
python build.py
```

Le résultat est `dist/unity-term.exe` sous Windows et `dist/unity-term` sous Linux.
PyInstaller construit pour le système sur lequel il est lancé : il faut donc exécuter
le script une fois sous Windows et une fois sous Linux pour produire les deux versions.

Pour un build plus facile à inspecter pendant le débogage :

```text
python build.py --onedir
```

Dans l'éditeur Unity, le lanceur cherche automatiquement le binaire dans le dépôt
frère `TERM_python/dist`. Dans un jeu construit, placez-le dans un dossier `TERM`
à côté de l'exécutable du jeu. Le chemin peut aussi être défini dans
`terminal_executable` (relatif à la racine du projet/jeu) ou dans la variable
d'environnement `TERM_CLIENT_PATH`.
