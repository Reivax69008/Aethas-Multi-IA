# AETHAS38 - Orchestrateur Multi-IA 🤖

Ce projet est un laboratoire d'intelligence artificielle personnel. Il agit comme un orchestrateur avancé (Rédacteur ➔ Travailleurs ➔ Concaténeur) permettant de solliciter jusqu'à 5 modèles en parallèle via une interface unifiée, moderne et hautement sécurisée.

L'interface visuelle est inspirée de l'ergonomie de Gemini, avec le logo stylisé A38 (cerveau en réseau neuronal néon) comme charte graphique centrale.

## 🏗️ Stack Technique & Architecture
- **Backend :** FastAPI (Python) modulaire et asynchrone (httpx, asyncio).
- **Frontend :** Vue.js + Tailwind CSS (Responsive / Mobile-first).
- **Base de Données :** PostgreSQL (gestion des utilisateurs, historiques, suivi financier, rôles hiérarchiques).
- **Traitement Documentaire :** LibreOffice Headless (génération/conversion Excel, Word, PDF).
- **Déploiement :** Docker, géré via Dockge et Gitea, sécurisé sur grappe RAID.

## 📌 Règles de Versioning (SemVer)
Le développement suit un versioning strict (format `vX.Y.Z`) synchronisé avec les tags Gitea et GitHub, affiché dynamiquement sur l'interface :
- **Majeur (X) :** Changement profond d'architecture ou refonte globale.
- **Mineur (Y) :** Validation et ajout d'une nouvelle fonctionnalité de la roadmap.
- **Patch (Z) :** Corrections de bugs, correctifs de sécurité ou ajustements visuels mineurs.

## 📦 Récupération des Paquets Docker (Tags)
Les images Docker sont construites automatiquement par les pipelines CI/CD lors de la création d'un tag.
- **Sur Gitea :** Depuis la page principale de votre dépôt, naviguez dans l'onglet **Packages** (ou Paquets). Vous y trouverez le registre de conteneurs avec toutes les versions taguées (`v0.16.0`, `latest`, etc.).
- **Sur GitHub :** Depuis la page principale du dépôt, regardez dans la colonne de droite la section **Packages**. Cliquez dessus pour accéder au GitHub Container Registry (`ghcr.io/votre-utilisateur/aethas38-multi-ia`) et visualiser la liste des tags disponibles à tirer via Docker/Dockge.

## 🚀 ROADMAP & CAHIER DES CHARGES

### Sécurité & Infrastructure
- [x] Installation stricte via Dockge et Gitea (création automatique des dossiers inclus).
- [x] Sécurisation de la totalité du projet (fichiers, BDD PostgreSQL) sur le stockage RAID.
- [x] Mots de passe cryptés (bcrypt), protection anti-brute force.
- [x] Authentification 2FA obligatoire (Keepassium, Authenticator, etc.).
- [x] Déconnexion automatique (timer invisible / session JWT) après 60 minutes d'inactivité.
- [x] Configuration de GitHub Actions / Gitea Actions pour la création automatique des paquets Docker (Tags SemVer + latest).
- [x] Horodatage UTC en base de données pour immunité au changement d'heure français (Prévention crash 2FA).
- [x] Rotation automatique des logs système : génération d'un fichier log par jour avec purge stricte des fichiers de plus de 7 jours.
- [x] Procédure de modification sécurisée du mot de passe (Utilisateurs et Admins).

### Administration & Gestion des Utilisateurs
- [x] Assistant de première installation : le premier utilisateur initiateur devient automatiquement le **Super-Admin** unique du projet.
- [x] Refonte du setup initial (Super-Admin) : configuration du serveur mail (opérateurs FR/Gmail) et paramétrage complet des clés fournisseurs IA.
- [x] Intégration de la roue crantée (Paramètres) en bas de la barre latérale.
- [x] Page de configuration par niveau (Super-Admin, Admin, Utilisateur).
- [x] Upload et personnalisation d'avatar utilisateur (redimensionnement et adaptation dynamique).
- [ ] Hiérarchie des rôles : Un Admin peut proposer l'élévation d'un User en Admin (soumis à validation exclusive du Super-Admin).
- [ ] Export de l'activité Admin : Fichier Excel avec KPI, graphiques "camembert", et suivi financier par utilisateur.
- [ ] Envoi de rapport d'activité automatisé chaque jeudi à 04h00.

### Expérience Utilisateur (UI/UX)
- [x] Thème moderne (Gemini-like) et 100% compatible smartphones.
- [x] Refonte de la gestion des projets : séparation Épinglés (en haut) / Non Épinglés (Récents).
- [x] Arrêt de la création automatique de nouveau projet à l'ouverture.
- [x] Intégration permanente du logo AETHAS38 en local (Setup / Login / Dashboard).
- [x] Indicateur visuel (Loader/Animation) signalant que l'IA AETHAS38 "réfléchit" ou travaille.
- [x] Fonctionnalité de renommage manuel des discussions/projets.
- [x] Affichage permanent et non invasif des soldes financiers fournisseurs sous le profil utilisateur, mis à jour après chaque requête.
- [ ] Affichage natif et fluide des images directement dans le flux de la discussion.
- [ ] Système de partage des réponses sur les réseaux et messageries externes (Facebook, WhatsApp, etc.).

### Moteur IA, Modèles & Fonctionnalités
- [x] Cœur asynchrone pour la parallélisation des appels API (module `orchestrator.py`).
- [x] Pipeline multi-agents complet avec sélection dynamique par requête :
  - Sélection de 1 à 5 travailleurs IA en parallèle.
  - Si 1 seul travailleur : bypass automatique du prompteur et du concaténeur.
  - Si > 1 travailleur : chaîne complète active (1 Prompteur ➔ N Travailleurs ➔ 1 Concaténeur).
- [x] Extraction universelle et multi-fournisseurs (OpenRouter, Groq, DeepSeek, Mistral, Gemini, Cloudflare) avec timeout étendu à 90 secondes.
- [x] Tâche planifiée (CRON) pour la mise à jour automatique des modèles toutes les 12h (00h00 et 12h00 heure de Paris).
- [x] Page dédiée aux modèles : export, import manuel de fichiers d'extraction JSON, filtrage par prix (Gratuit/Payant), domaine (Code, Texte, Vision, Audio) et recherche textuelle.
- [x] Extraction unitaire des retours IA et téléchargement global d'une conversation (formats TXT et JSON).
- [x] Détection et téléchargement ciblé de blocs de code ou de données (ex: fichiers `.xlsx`, `.py`, `.csv`) générés par l'IA en respectant le nommage exact.