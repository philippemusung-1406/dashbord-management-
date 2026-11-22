# Tableau de Bord Interactif — Fiabilisation des Transformateurs MT (KCC S.A.)

Application **100 % Python (Streamlit)** développée dans le cadre du TP3 de Management (Master 2 Data Science — Université Don Bosco de Lubumbashi).

## Contenu du package
- `app.py` : Application Streamlit complète (KPI dynamiques, maintenance prédictive P09, diagnostic check-list F02, suivi des 10 actions du plan stratégique TP1 et export Excel F10).
- `transfo_dataset .xlsx` : Base de données d'inspections GMAO (8 260 relevés sur 53 transformateurs MT).
- `requirements.txt` : Dépendances Python nécessaires au déploiement.

## Installation et lancement en local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déploiement en ligne (Streamlit Community Cloud)
1. Créez un dépôt GitHub contenant `app.py`, `requirements.txt` et `transfo_dataset .xlsx`.
2. Connectez-vous sur [share.streamlit.io](https://share.streamlit.io).
3. Sélectionnez votre dépôt et le fichier principal `app.py`, puis cliquez sur **Deploy**.
