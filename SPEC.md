# TradeBoard Engine — Central Banks Probability Engine
## SPECIFICATION (V1)

---

## 1. OBJECTIF DU MOTEUR

Le **TradeBoard Central Banks Engine** a pour objectif de calculer, à partir
des contrats futures de taux (Barchart), les **probabilités implicites**
de décisions de politique monétaire pour **toutes les grandes banques centrales**.

Le moteur est :
- déterministe
- explicable
- auditable
- indépendant du frontend (Lovable, autre UI)

Aucun calcul n’est effectué côté client.

---

## 2. ARCHITECTURE GÉNÉRALE
CSV Barchart
↓
Moteur Python (calculs)
↓
JSON statique versionné
↓
UI (Lovable / autre frontend)


Principes clés :
- séparation stricte **calcul / affichage**
- exécution **1 fois par jour**
- aucune logique métier dans l’UI

---

## 3. SOURCE DE DONNÉES

### 3.1 Type de données
- Contrats futures de taux :
  - Fed Funds (FED)
  - €STR (ECB)
  - SONIA, SARON, etc. (extensions futures)

### 3.2 Source
- Fournisseur : **Barchart**
- Format : CSV
- Mise à jour : quotidienne

---

## 4. CONFIGURATION PAR BANQUE CENTRALE

Chaque banque centrale est définie par un fichier YAML dédié.

Exemples :
- `configs/fed.yaml`
- `configs/ecb.yaml`

Le YAML contient :
- métadonnées banque
- taux directeur actuel
- caractéristiques des futures
- calendrier des réunions
- règles explicites de mapping meeting → contrat
- paramètres de calcul des probabilités
- seuils de qualité des données

Aucune règle implicite n’est autorisée.

---

## 5. LOGIQUE DE CALCUL — TAUX IMPLICITE

### 5.1 Conversion prix → taux

Par défaut (Fed Funds, €STR) :

Taux implicite (%) = 100 - Prix du future


La formule est définie dans le YAML (`price_formula`).

---

## 6. MAPPING RÉUNION → CONTRAT

### Principe fondamental

Le contrat utilisé pour une réunion est **explicitement défini**
dans le YAML via un `manual_mapping`.

Exemples :
- FED : réunion du mois M → contrat du mois M+1
- ECB : réunion du trimestre Q → contrat du trimestre Q

Aucun calcul automatique du mapping n’est autorisé en V1.

---

## 7. CALCUL DE L’ÉCART AU TAUX ACTUEL

spread_bp = (taux implicite - taux actuel) × 100


Cet écart représente l’anticipation du marché.

---

## 8. CALCUL DES PROBABILITÉS (V1)

### 8.1 Méthode

Méthode : `linear_distance_v1.5`

- basée sur l’écart en basis points
- pas de distribution statistique
- logique volontairement simple et explicable

### 8.2 Seuil de neutralité

threshold_bp = 12.5 bp


- spread < -12.5 bp → biais dovish
- -12.5 ≤ spread ≤ +12.5 → hold
- spread > +12.5 bp → biais hawkish

### 8.3 Scénarios

Les scénarios possibles sont définis dans le YAML :
- FED : double cut, cut, hold, hike, double hike
- ECB : cut, hold, hike

Les probabilités sont normalisées pour sommer à 100 %.

---

## 9. QUALITÉ DES DONNÉES

Chaque contrat est évalué selon :
- open interest
- volume
- bid/ask spread (optionnel)

Si `bid_ask_spread` est absent du CSV :
- le critère est ignoré
- aucune pénalité n’est appliquée

Niveaux :
- high
- medium
- low
- unavailable

---

## 10. FORMAT DE SORTIE

Le moteur génère un **JSON statique** par banque centrale contenant :
- metadata (date, version, source)
- courbe des taux implicites
- probabilités pour la prochaine réunion
- indicateurs de qualité des données

Le JSON est la **seule interface** entre moteur et UI.

---

## 11. CONTRAINTES NON-NÉGOCIABLES

- ❌ Pas de calcul côté frontend
- ❌ Pas de magie implicite
- ❌ Pas de logique dépendante de l’UI
- ✅ Tout comportement doit être traçable dans le YAML ou le code

---

## 12. PÉRIMÈTRE V1

Inclus :
- toutes les grandes banques centrales
- mise à jour quotidienne
- probabilités Cut / Hold / Hike (et variantes)

Exclus :
- intraday
- machine learning
- calibration statistique avancée
- backtesting (V2)

---

## 13. PHILOSOPHIE PRODUIT

Le moteur doit :
- inspirer confiance
- être compréhensible par un humain
- être défendable face à un professionnel

Objectif : **crédibilité institutionnelle**, pas complexité gratuite.
