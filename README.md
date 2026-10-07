# AETHAS38 - Orchestrateur Multi-IA 🤖

Ce projet est un laboratoire d'intelligence artificielle personnel. Il agit comme un orchestrateur avancé (Rédacteur ➔ Travailleurs ➔ Concaténeur) permettant de solliciter jusqu'à 5 modèles en parallèle via une interface unifiée, moderne et hautement sécurisée.

L'interface visuelle est inspirée de l'ergonomie de Gemini, avec le logo stylisé A38 (cerveau en réseau neuronal néon) comme charte graphique centrale.

## 🏗️ Stack Technique & Architecture

* **Backend :** FastAPI (Python) modulaire asynchrone (httpx, asyncio)[cite: 2].
* **Frontend :** Vue.js + Tailwind CSS (Responsive / Mobile-first)[cite: 2].
* **Base de Données :** PostgreSQL (gestion des utilisateurs, rôles hiérarchiques Super-Admin/Admin/User, historiques, suivi financier)[cite: 2].
* **Traitement Documentaire :** LibreOffice Headless (génération/conversion Excel, Word, PDF)[cite: 2].
* **Déploiement :** Docker, géré via Dockge et Gitea, sécurisé sur grappe RAID[cite: 2].

## 📌 Règles de Versioning (SemVer)

Le développement suit un versioning strict (format `vX.Y.Z`) synchronisé avec les tags Gitea et GitHub, affiché dynamiquement sur l'interface[cite: 2]:

* **Majeur (X) :** Changement profond d'architecture ou refonte globale[cite: 2].
* **Mineur (Y) :** Validation et ajout d'une nouvelle fonctionnalité de la roadmap[cite: 2].
* **Patch (Z) :** Corrections de bugs, correctifs de sécurité ou ajustements visuels mineurs[cite: 2].

## 📦 Récupération des Paquets Docker (Tags)

Les images Docker sont construites automatiquement par les pipelines CI/CD lors de la création d'un tag[cite: 2].

* **Sur Gitea :** Depuis la page principale de votre dépôt, naviguez dans l'onglet **Packages** (ou Paquets). Vous y trouverez le registre de conteneurs avec toutes les versions taguées (`v0.16.1`, `latest`, etc.)[cite: 2].
* **Sur GitHub :** Depuis la page principale du dépôt, regardez dans la colonne de droite la section **Packages**. Cliquez dessus pour accéder au GitHub Container Registry (`ghcr.io/votre-utilisateur/aethas38-multi-ia`) et visualiser la liste des tags disponibles à tirer via Docker/Dockge[cite: 2].

## 🚀 ROADMAP & CAHIER DES CHARGES

### Sécurité & Infrastructure

* [x] Installation stricte via Dockge et Gitea (création automatique des dossiers inclus)[cite: 2].
* [x] Sécurisation de la totalité du projet (fichiers, BDD PostgreSQL) sur le stockage RAID[cite: 2].
* [x] Mots de passe cryptés (bcrypt), protection anti-brute force[cite: 2].
* [x] Authentification 2FA obligatoire (Keepassium, Authenticator, etc.)[cite: 2].
* [x] Déconnexion automatique (timer invisible / session JWT) après 60 minutes d'inactivité[cite: 2].
* [x] Configuration de GitHub Actions / Gitea Actions pour la création automatique des paquets Docker (Tags SemVer + latest)[cite: 2].
* [x] Horodatage UTC en base de données pour immunité au changement d'heure français (Prévention crash 2FA)[cite: 2].
* [x] Rotation automatique des logs système : génération d'un fichier log par jour avec purge stricte des fichiers de plus de 7 jours[cite: 2].
* [x] Procédure de modification sécurisée du mot de passe (Utilisateurs et Admins)[cite: 2].

### Administration & Gestion des Utilisateurs

* [x] Assistant de première installation : l'initiateur du projet se voit attribuer automatiquement le rôle exclusif de **Super-Admin** (un seul par projet)[cite: 2].
* [x] Refonte du setup initial (Super Admin) : configuration du serveur mail (opérateurs FR/Gmail) et paramétrage complet des clés fournisseurs IA[cite: 2].
* [x] Intégration de la roue crantée (Paramètres) en bas de la barre latérale[cite: 2].
* [x] Page de configuration par niveau (Super-Admin, Admin, Utilisateur)[cite: 2].
* [x] Upload et personnalisation dynamique d'avatar utilisateur[cite: 2].
* [ ] Hiérarchie des rôles : Un Admin peut proposer l'élévation d'un User en Admin (formulaire soumis à la validation exclusive du Super Admin)[cite: 2].
* [ ] Export de l'activité Admin : Fichier Excel avec KPI, graphiques "camembert", et suivi financier par utilisateur[cite: 2].
* [x] Suivi financier en temps réel et vérification du budget API (mis à jour après chaque requête et affiché de manière non invasive sous le nom)[cite: 2].
* [ ] Envoi de rapport d'activité automatisé chaque jeudi à 04h00[cite: 2].

### Expérience Utilisateur (UI/UX)

* [x] Thème moderne (Gemini-like) et 100% compatible smartphones[cite: 2].
* [x] Refonte de la gestion des projets : séparation Épinglés (en haut) / Non Épinglés (Récents)[cite: 2].
* [x] Arrêt de la création automatique de nouveau projet à l'ouverture[cite: 2].
* [x] Intégration permanente du logo AETHAS38 en local (Setup / Login / Dashboard)[cite: 2].
* [x] Indicateur visuel (Loader/Animation) signalant que l'IA AETHAS38 "réfléchit" ou travaille[cite: 2].
* [x] Fonctionnalité de renommage manuel des discussions/projets[cite: 2].
* [ ] Affichage natif et fluide des images directement dans le flux de la discussion[cite: 2].
* [ ] Système de partage des réponses sur les réseaux et messageries externes (Facebook, WhatsApp, etc.)[cite: 2].

### Moteur IA, Modèles & Fonctionnalités

* [x] Cœur asynchrone pour la parallélisation des appels API (module `orchestrator.py`)[cite: 2].
* [x] Pipeline multi-agents complet avec sélection dynamique par requête :
  * Sélection de 1 à 5 travailleurs IA en parallèle[cite: 2].
  * Si un seul travailleur est sélectionné, bypass automatique du prompteur et du concaténeur[cite: 2].
  * Si > 1 travailleur, activation de la chaîne complète (1 Prompteur ➔ N Travailleurs ➔ 1 Concaténeur)[cite: 2].
* [x] Extraction universelle multi-fournisseurs (OpenRouter, Groq, DeepSeek, Mistral, Gemini, Cloudflare) avec timeout porté à 90 secondes[cite: 2].
* [x] Tâche planifiée (CRON) pour la mise à jour des modèles toutes les 12h (00h00 et 12h00)[cite: 2].
* [x] Page spécifique dédiée aux modèles permettant l'export, l'import manuel d'un fichier d'extraction JSON, ainsi que le filtrage par prix, domaine et mots-clés[cite: 2].
* [x] Extraction unitaire des retours IA et téléchargement global d'une conversation (formats TXT et JSON)[cite: 2].
* [x] Détection et téléchargement ciblé de pièces jointes ou blocs spécifiques (Code brut, scripts, fichiers de données) générés par l'IA en respectant le nommage exact demandé[cite: 2].
* [x] Classement, filtrage (Gratuit/Payant) et catégorisation des modèles (Texte, Code, Vision, Audio)[cite: 2].
* [ ] Traduction automatisée des descriptions des modèles via Ollama (local) ou Gemini[cite: 2].
* [ ] Interface d'aide à la décision pour le choix des modèles selon la tâche souhaitée[cite: 2].
* [ ] Mécanisme de fallback / termes génériques pour les appels API (protection contre le dépassement des quotas)[cite: 2].