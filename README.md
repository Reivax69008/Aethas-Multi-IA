# AETHAS38 - Orchestrateur Multi-IA 🤖

Ce projet est un laboratoire d'intelligence artificielle personnel[cite: 5]. Il agit comme un orchestrateur avancé (Rédacteur ➔ Travailleurs ➔ Concaténeur) permettant de solliciter jusqu'à 5 modèles en parallèle via une interface unifiée, moderne et hautement sécurisée[cite: 5].

L'interface visuelle est inspirée de l'ergonomie de Gemini, avec le logo stylisé A38 (cerveau en réseau neuronal néon) comme charte graphique centrale[cite: 6].

## 🏗️ Stack Technique & Architecture
- **Backend :** FastAPI (Python) modulaire (une fonction = un module).
- **Frontend :** Vue.js + Tailwind CSS (Responsive / Mobile-first).
- **Base de Données :** PostgreSQL (gestion des utilisateurs, historiques, suivi financier).
- **Traitement Documentaire :** LibreOffice Headless (génération/conversion Excel, Word, PDF).
- **Déploiement :** Docker, géré via Dockge et Gitea, sécurisé sur grappe RAID[cite: 5].

## 📌 Règles de Versioning (SemVer)
Le développement suit un versioning strict (format `vX.Y.Z`) synchronisé avec les tags Gitea et GitHub, affiché dynamiquement sur l'interface[cite: 5] :
- **Majeur (X) :** Changement profond d'architecture ou refonte globale[cite: 5].
- **Mineur (Y) :** Validation et ajout d'une nouvelle fonctionnalité de la roadmap[cite: 5].
- **Patch (Z) :** Corrections de bugs, correctifs de sécurité ou ajustements visuels mineurs[cite: 5].

## 🚀 ROADMAP & CAHIER DES CHARGES

### Sécurité & Infrastructure
- [ ] Installation stricte via Dockge et Gitea (création automatique des dossiers inclus).
- [ ] Sécurisation de la totalité du projet (fichiers, BDD PostgreSQL) sur le stockage RAID.
- [ ] Mots de passe cryptés, protection anti-brute force et anti-DDOS.
- [ ] Authentification 2FA obligatoire (Keepassium, Authenticator, etc.) sans accès SSH pour les utilisateurs.
- [ ] Déconnexion automatique (timer invisible) après 60 minutes d'inactivité.
- [ ] Procédure de réinitialisation/modification du mot de passe (Admin et Utilisateurs).
- [ ] Configuration de GitHub Actions pour la création automatique des paquets Docker.

### Administration & Gestion des Utilisateurs
- [ ] Page d'administration complète : changement des clés, ajout de fournisseurs, configuration et test du serveur mail.
- [ ] Assistant de première installation (création du compte admin complet), puis auto-destruction du script.
- [ ] Système d'invitation par mail : création de compte avec génération de QR Code 2FA à la première connexion.
- [ ] Vérification du budget API toutes les 15 minutes et actualisation après chaque requête.
- [ ] Suivi financier détaillé par fournisseur d'IA.

### Expérience Utilisateur (UI/UX)
- [ ] Thème moderne (Gemini-like) et 100% compatible smartphones.
- [ ] Refonte de la gestion des projets : séparation Épinglés (en haut) / Non Épinglés, avec le dernier utilisé en tête de liste.
- [ ] Plus de création automatique de nouveau projet à l'ouverture.
- [ ] Pré-filtre et classement automatique des modèles par catégorie (Texte/Code, Photo/Image, Vidéo, Son) avec l'aide de l'API Gemini lors de l'import.
- [ ] Intégration permanente du logo AETHAS38 (hébergé sur Drive) dans l'interface.

### Moteur IA & Fonctionnalités d'Export
- [ ] Récupération dynamique de la liste des modèles directement auprès des 9 fournisseurs par défaut (OpenRouter, Groq, Gemini, DeepSeek, Mistral, Cloudflare, HuggingFace, etc.).
- [ ] Pipeline multi-agents : 1 Rédacteur de prompt, jusqu'à 5 Travailleurs en parallèle, 1 Concaténeur final.
- [ ] Prise en charge de modèles IA pour le traitement de texte, la génération d'images, la synthèse vocale, la musique (calage sur vidéo) et la vidéo.
- [ ] Téléchargement des prompts, des réponses, et de l'historique complet en PDF, TXT, MD ou JSON.
- [ ] Bouton dédié pour télécharger les fichiers générés (Images, Vidéos, Excel mis en forme via LibreOffice).