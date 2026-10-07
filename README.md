# AETHAS38 - Orchestrateur Multi-IA 🤖

Ce projet est un laboratoire d'intelligence artificielle personnel. Il agit comme un orchestrateur avancé (Rédacteur ➔ Travailleurs ➔ Concaténeur) permettant de solliciter jusqu'à 5 modèles en parallèle via une interface unifiée, moderne et hautement sécurisée.

L'interface visuelle est inspirée de l'ergonomie de Gemini, avec le logo stylisé A38 (cerveau en réseau neuronal néon) comme charte graphique centrale.

## 🏗️ Stack Technique & Architecture

* **Backend :** FastAPI (Python) modulaire (une fonction = un module) asynchrone (httpx, asyncio).
* **Frontend :** Vue.js + Tailwind CSS (Responsive / Mobile-first).
* **Base de Données :** PostgreSQL (gestion des utilisateurs, historiques, suivi financier).
* **Traitement Documentaire :** LibreOffice Headless (génération/conversion Excel, Word, PDF).
* **Déploiement :** Docker, géré via Dockge et Gitea, sécurisé sur grappe RAID.

## 📌 Règles de Versioning (SemVer)

Le développement suit un versioning strict (format `vX.Y.Z`) synchronisé avec les tags Gitea et GitHub, affiché dynamiquement sur l'interface :

* **Majeur (X) :** Changement profond d'architecture ou refonte globale.
* **Mineur (Y) :** Validation et ajout d'une nouvelle fonctionnalité de la roadmap.
* **Patch (Z) :** Corrections de bugs, correctifs de sécurité ou ajustements visuels mineurs.

## 📦 Récupération des Paquets Docker (Tags)

Les images Docker sont construites automatiquement par les pipelines CI/CD lors de la création d'un tag.

* **Sur Gitea :** Depuis la page principale de votre dépôt, naviguez dans l'onglet **Packages** (ou Paquets). Vous y trouverez le registre de conteneurs avec toutes les versions taguées (`v0.10.1`, `latest`, etc.).
* **Sur GitHub :** Depuis la page principale du dépôt, regardez dans la colonne de droite la section **Packages**. Cliquez dessus pour accéder au GitHub Container Registry (`ghcr.io/votre-utilisateur/aethas38-multi-ia`) et visualiser la liste des tags disponibles à tirer via Docker/Dockge.

## 🚀 ROADMAP & CAHIER DES CHARGES

### Sécurité & Infrastructure

* [x] Installation stricte via Dockge et Gitea (création automatique des dossiers inclus).


* [x] Sécurisation de la totalité du projet (fichiers, BDD PostgreSQL) sur le stockage RAID.


* [x] Mots de passe cryptés (bcrypt), protection anti-brute force.


* [x] Authentification 2FA obligatoire (Keepassium, Authenticator, etc.).


* [x] Déconnexion automatique (timer invisible / session JWT) après 60 minutes d'inactivité.


* [x] Configuration de GitHub Actions / Gitea Actions pour la création automatique des paquets Docker (Tags SemVer + latest).


* [x] Horodatage UTC en base de données pour immunité au changement d'heure français (Prévention crash 2FA).


* [x] Rotation automatique des logs système : génération d'un fichier log par jour avec purge stricte des fichiers de plus de 7 jours.
* [ ] Procédure de réinitialisation/modification du mot de passe (Admin et Utilisateurs).



### Administration & Gestion des Utilisateurs

* [x] Assistant de première installation (création du compte admin complet).


* [x] Refonte du setup initial (Super Admin) : Obligation de configurer le serveur mail (aide opérateurs FR/Gmail) et paramétrage complet des clés fournisseurs IA (OpenRouter, Groq, Gemini, DeepSeek, Mistral, Cloudflare, HF).
* [x] Intégration de la roue crantée (Paramètres) en bas de la barre latérale.
* [ ] Page de configuration Utilisateur : changement d'email (avec validation via lien envoyé) et de mot de passe.


* [ ] Page de configuration Admin : ajout/modification de fournisseurs, clés API, et serveur mail en permanence.


* [ ] Hiérarchie des rôles : Un Admin peut proposer l'élévation d'un User en Admin (formulaire soumis à la validation exclusive du Super Admin).


* [ ] Export de l'activité Admin : Fichier Excel avec KPI, graphiques "camembert", et suivi financier par utilisateur.


* [ ] Suivi financier en temps réel et vérification du budget API.


* [ ] Envoi de rapport d'activité automatisé chaque jeudi à 04h00.



### Expérience Utilisateur (UI/UX)

* [x] Thème moderne (Gemini-like) et 100% compatible smartphones.


* [x] Refonte de la gestion des projets : séparation Épinglés (en haut) / Non Épinglés (Récents).


* [x] Arrêt de la création automatique de nouveau projet à l'ouverture.


* [x] Intégration permanente du logo AETHAS38 en local (Setup / Login / Dashboard).


* [x] Indicateur visuel (Loader/Animation) signalant que l'IA AETHAS38 "réfléchit" ou travaille.
* [x] Fonctionnalité de renommage manuel des discussions/projets.
* [ ] Affichage natif et fluide des images directement dans le flux de la discussion.
* [ ] Système de partage des réponses sur les réseaux et messageries externes (Facebook, WhatsApp, etc.).

### Moteur IA, Modèles & Fonctionnalités

* [x] Cœur asynchrone pour la parallélisation des appels API (module `orchestrator.py`).
* [ ] Pipeline multi-agents complet avec sélection dynamique :
* Possibilité de sélectionner de 1 à 5 travailleurs IA en parallèle.
* Si un seul travailleur est sélectionné, bypass automatique du prompteur et du concaténeur.
* Si > 1 travailleur, activation de la chaîne complète (1 Prompteur ➔ N Travailleurs ➔ 1 Concaténeur).


* [ ] Extraction, mise à jour (via tâche planifiée CRON toutes les 12h ou manuelle) et gestion des modèles depuis les API fournisseurs vers la BDD.
* [ ] Page spécifique d'interface pour les modèles permettant l'export, l'import manuel d'un fichier d'extraction, et la sélection.
* [ ] Extraction unitaire des retours IA.
* [ ] Extraction/Téléchargement de la totalité d'une conversation dans des formats utiles aux différents fournisseurs (JSONL, TXT, etc.).
* [ ] Détection et téléchargement ciblé de pièces jointes ou blocs spécifiques (Code brut, fichiers Excel `.xlsx`) générés par l'IA en respectant le nommage exact demandé.
* [ ] Classement, filtrage (Gratuit/Payant) et catégorisation des modèles (Texte, Code, Image, Audio, Vidéo).


* [ ] Traduction automatisée des descriptions des modèles via Ollama (local) ou Gemini.


* [ ] Interface d'aide à la décision pour le choix des modèles selon la tâche souhaitée.


* [ ] Mécanisme de fallback / termes génériques pour les appels API (protection contre le dépassement des quotas Gemini).