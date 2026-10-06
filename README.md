# AETHAS38 - Orchestrateur Multi-IA 🤖

Ce projet est un laboratoire d'intelligence artificielle personnel. Il agit comme un orchestrateur avancé (Rédacteur ➔ Travailleurs ➔ Concaténeur) permettant de solliciter plusieurs modèles et fournisseurs via une interface unifiée, moderne et hautement sécurisée.

## 🏗️ Stack Technique
- **Backend :** FastAPI (Python)
- **Frontend :** Vue.js + Tailwind CSS (Design inspiré de Gemini)
- **Base de Données :** PostgreSQL
- **Déploiement :** Docker & Docker Compose (sécurisé sur grappe RAID)

## 📌 Règles de Versioning (SemVer)
Le développement suit un versioning strict (format `vX.Y.Z`) synchronisé avec les tags Gitea et GitHub :
- **Majeur (X) :** Changement profond d'architecture ou refonte globale (ex: passage de FastHTML à Vue.js).
- **Mineur (Y) :** Validation et ajout d'une nouvelle fonctionnalité de la roadmap.
- **Patch (Z) :** Corrections de bugs, correctifs de sécurité ou ajustements visuels mineurs.

---

## 🚀 ROADMAP (Ordre d'exécution strict)

- [ ] **Étape 1 :** Création de la page d'administration (changement des clés, ajout de fournisseurs, configuration serveur mail, etc.).
- [ ] **Étape 2 :** Ajout des fournisseurs pour le traitement d'images, de sons (génération de voix, musique, calage sur vidéo) et de vidéos.
- [ ] **Étape 3 :** Possibilité de télécharger les prompts en PDF, TXT, MD et JSON.
- [ ] **Étape 4 :** Possibilité de télécharger les réponses en PDF, TXT, MD et JSON.
- [ ] **Étape 5 :** Rédaction du Wiki détaillé pour Gitea et GitHub.
- [ ] **Étape 6 :** Ne plus créer systématiquement un nouveau projet à l'ouverture de l'application.
- [ ] **Étape 7 :** Refonte de la gestion des projets (séparation Épinglés / Non Épinglés, avec le dernier utilisé en tête de liste).
- [ ] **Étape 8 :** Possibilité d'extraire la totalité d'une conversation en PDF, TXT, MD et JSON.
- [ ] **Étape 9 :** Mise en place d'un pré-filtre pour sélectionner les modèles selon leur catégorie (photo/image, vidéo, texte/code).
- [ ] **Étape 10 :** Refonte architecturale : création de modules dédiés par tâche pour remplacer le "main" unique.
- [ ] **Étape 11 :** Paramétrage de GitHub Actions pour la création automatique des paquets Docker (similaire à Gitea).
- [ ] **Étape 12 :** Migration de la gestion de l'historique vers une BDD PostgreSQL sécurisée sur le RAID (avec récupération de l'existant).
- [ ] **Étape 13 :** Mise en place et affichage dynamique du versioning pour plus de lisibilité.
- [ ] **Étape 14 :** Sécurisation et mappage de la totalité du projet (fichiers et BDD) sur le stockage RAID.
- [ ] **Étape 15 :** Intégration d'un timer invisible déconnectant l'utilisateur après 60 minutes d'inactivité.
- [ ] **Étape 16 :** Optimisation complète de l'interface pour une compatibilité smartphones (Mobile First).
- [ ] **Étape 17 :** Ajout d'un bouton dédié pour récupérer facilement les images, vidéos ou fichiers Excel mis en forme.
- [ ] **Étape 18 :** Application d'un thème plus moderne et responsive (Transition actée de FastHTML vers Vue.js/FastAPI).
- [ ] **Étape 19 :** Classement automatique des modèles dès l'import (utilisation de l'API Gemini pour trier par efficacité/catégorie).
- [ ] **Étape 20 :** Ajustement final de la mise en forme globale pour s'inspirer de l'ergonomie de Gemini.
- [ ] **Étape 21 :** Vérification des sommes allouées (API OpenRouter) toutes les 15 minutes et actualisation après chaque requête.
- [ ] **Étape 22 :** Intégration de LibreOffice (mode headless) pour le traitement des fichiers (Excel, Word, PDF) — *Cette étape servira de pont backend (API) pour le futur site d'attachements Corporate.*