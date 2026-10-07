# Correction orthographique des textes existants

À exécuter sur le serveur après déploiement. Les cinq applications sont traitées l’une après l’autre, avec les modèles privés déjà installés.

```bash
sudo bash /var/www/facturation_backend/scripts/correct_all_app_texts.sh prepare
```

Affiche le champ en cours, le nombre traité, `done` et une estimation du temps restant. Cette première passe ne modifie aucune donnée. Les propositions avant/après sont dans `/var/lib/ebh-ai-corrections/*.jsonl` (dossier privé, hors des fichiers publics).

Relisez les valeurs `before` / `after`. Pour ne pas appliquer une proposition, retirez sa ligne `status: prepared` du journal. Puis :

```bash
sudo bash /var/www/facturation_backend/scripts/correct_all_app_texts.sh apply
```

Relancer avec le même dossier reprend les travaux sans refaire les propositions déjà préparées. Une modification faite dans l’application entre préparation et application est conservée : le script signale un conflit. Les champs avec historique conservent une trace de la correction. Les montants, dates, références, identifiants, noms des personnes et sociétés, listes de choix et mouvements historiques sont exclus. La langue d’origine est conservée : seule l’orthographe/grammaire du texte est corrigée.

Pour revenir aux valeurs précédentes sans écraser une modification plus récente :

```bash
sudo bash /var/www/facturation_backend/scripts/correct_all_app_texts.sh rollback
```

Pour une nouvelle campagne après modification des textes, choisissez un nouveau dossier en deuxième argument. Pour un essai limité à une application :

```bash
cd /var/www/facturation_backend
sudo install -d -m 700 -o 1000 -g 1000 /var/lib/ebh-ai-corrections
sudo docker compose run --rm --no-deps -v /var/lib/ebh-ai-corrections:/ai-corrections web python manage.py ai_correct_texts --journal /ai-corrections/facturation-essai.jsonl --limit 10
```
