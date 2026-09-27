# 🎬 Regarder une vidéo contre un service

Site Flask sans compte utilisateur ni connexion utilisateur.

## Installation
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Ouvrir http://127.0.0.1:5000

## Administration
- URL : `/admin/login`
- Mot de passe par défaut en local : `3004`
- En production, définir `ADMIN_PASSWORD` et `SECRET_KEY`.

## Publicités
Le projet contient des emplacements centralisés :
- `ADSTERRA_TOP`
- `ADSTERRA_MIDDLE`
- `ADSTERRA_BOTTOM`
- `ADSTERRA_SERVICE`
- `ADSTERRA_REWARDED_START` / `ADSTERRA_REWARDED_END`

Aucune clé Adsterra n'est incluse.

## Important
Le bouton vidéo récompensée ne transforme pas un clic en récompense. La route `/api/reward/validate` attend une preuve vérifiable du fournisseur. Il faut brancher le mécanisme officiel de validation correspondant au format publicitaire réellement utilisé avant d'accorder une récompense.

Le système actuel utilise une limite temporaire côté serveur via session pour le démarrage du flux. Pour une protection forte à grande échelle, utiliser Redis ou une base partagée avec limitation par IP et/ou empreinte de requête non personnelle.


## Services ajoutés
- Générateur de QR code
- Convertisseur de monnaie
- Générateur de slug
- Calculateur de pourcentage
- Et ajout dynamique de services depuis l'administration.

### Convertisseur de monnaie
Les taux initiaux sont des valeurs configurables de démonstration. Ils sont modifiables dans `/admin`.
Le projet ne présente pas ces taux comme des cotations financières en temps réel.
