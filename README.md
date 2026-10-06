# AETHAS38 - Orchestrateur Multi-IA 🤖

Ce projet est un laboratoire d'intelligence artificielle personnel. Il agit comme un orchestrateur avancé (Rédacteur ➔ Travailleurs ➔ Concaténeur) permettant de solliciter jusqu'à 5 modèles en parallèle via une interface unifiée, moderne et hautement sécurisée.

L'interface visuelle est inspirée de l'ergonomie de Gemini, avec le logo stylisé A38 (cerveau en réseau neuronal néon) comme charte graphique centrale.

## 🏗️ Stack Technique & Architecture
- **Backend :** FastAPI (Python) modulaire (une fonction = un module).
- **Frontend :** Vue.js + Tailwind CSS (Responsive / Mobile-first).
- **Base de Données :** PostgreSQL (gestion des utilisateurs, historiques, suivi financier).
- **Traitement Documentaire :** LibreOffice Headless (génération/conversion Excel, Word, PDF).
- **Déploiement :** Docker, géré via Dockge et Gitea, sécurisé sur grappe RAID.

## 📌 Règles de Versioning (SemVer)
Le développement suit un versioning strict (format `vX.Y.Z`) synchronisé avec les tags Gitea et GitHub, affiché dynamiquement sur l'interface :
- **Majeur (X) :** Changement profond d'architecture ou refonte globale.
- **Mineur (Y) :** Validation et ajout d'une nouvelle fonctionnalité de la roadmap.
- **Patch (Z) :** Corrections de bugs, correctifs de sécurité ou ajustements visuels mineurs.

## 🚀 ROADMAP & CAHIER DES CHARGES

### Sécurité & Infrastructure
- [x] Installation stricte via Dockge et Gitea (création automatique des dossiers inclus).
- [x] Sécurisation de la totalité du projet (fichiers, BDD PostgreSQL) sur le stockage RAID.
- [x] Mots de passe cryptés (bcrypt), protection anti-brute force et anti-DDOS (à compléter pour le DDOS).
- [x] Authentification 2FA obligatoire (Keepassium, Authenticator, etc.) sans accès SSH pour les utilisateurs.
- [x] Déconnexion automatique (timer invisible / session JWT) après 60 minutes d'inactivité.
- [ ] Procédure de réinitialisation/modification du mot de passe (Admin et Utilisateurs).
- [x] Configuration de GitHub Actions / Gitea Actions pour la création automatique des paquets Docker.

### Administration & Gestion des Utilisateurs
- [ ] Page d'administration complète : changement des clés, ajout de fournisseurs, configuration et test du serveur mail.
- [x] Assistant de première installation (création du compte admin complet), puis auto-destruction / blocage du script.
- [ ] Système d'invitation par mail : création de compte avec génération de QR Code 2FA à la première connexion.
- [ ] Vérification du budget API toutes les 15 minutes et actualisation après chaque requête.
- [ ] Suivi financier détaillé par fournisseur d'IA.

### Expérience Utilisateur (UI/UX)
- [~] Thème moderne (Gemini-like) et 100% compatible smartphones (Setup et Login terminés).
- [ ] Refonte de la gestion des projets : séparation Épinglés (en haut) / Non Épinglés, avec le dernier utilisé en tête de liste.
- [ ] Plus de création automatique de nouveau projet à l'ouverture.
- [ ] Pré-filtre et classement automatique des modèles par catégorie (Texte/Code, Photo/Image, Vidéo, Son) avec l'aide de l'API Gemini lors de l'import.
- [x] Intégration permanente du logo AETHAS38 dans l'interface (Setup / Login).

### Moteur IA & Fonctionnalités d'Export
- [ ] Récupération dynamique de la liste des modèles directement auprès des fournisseurs par défaut (OpenRouter, Groq, Gemini, DeepSeek, Mistral, Cloudflare, HuggingFace, etc.).
- [ ] Pipeline multi-agents : 1 Rédacteur de prompt, jusqu'à 5 Travailleurs en parallèle, 1 Concaténeur final.
- [ ] Prise en charge de modèles IA pour le traitement de texte, la génération d'images, la synthèse vocale, la musique (calage sur vidéo) et la vidéo.
- [ ] Téléchargement des prompts, des réponses, et de l'historique complet en PDF, TXT, MD ou JSON.
- [ ] Bouton dédié pour télécharger les fichiers générés (Images, Vidéos, Excel mis en forme via LibreOffice).