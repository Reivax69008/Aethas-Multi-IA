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
- [x] Mots de passe cryptés (bcrypt), protection anti-brute force.
- [x] Authentification 2FA obligatoire (Keepassium, Authenticator, etc.).
- [x] Déconnexion automatique (timer invisible / session JWT) après 60 minutes d'inactivité.
- [x] Configuration de GitHub Actions / Gitea Actions pour la création automatique des paquets Docker (Tags SemVer + latest).
- [x] Horodatage UTC en base de données pour immunité au changement d'heure français (Prévention crash 2FA).
- [ ] Procédure de réinitialisation/modification du mot de passe (Admin et Utilisateurs).

### Administration & Gestion des Utilisateurs
- [x] Assistant de première installation (création du compte admin complet).
- [ ] Refonte du setup initial (Super Admin) : Obligation de configurer le serveur mail (aide opérateurs FR/Gmail) et proposition de saisie des clés API.
- [ ] Intégration de la roue crantée (Paramètres) en bas de la barre latérale.
- [ ] Page de configuration Utilisateur : changement d'email (avec validation via lien envoyé) et de mot de passe.
- [ ] Page de configuration Admin : ajout/modification de fournisseurs, clés API, et serveur mail en permanence.
- [ ] Hiérarchie des rôles : Un Admin peut proposer l'élévation d'un User en Admin (formulaire soumis à la validation exclusive du Super Admin).
- [ ] Export de l'activité Admin : Fichier Excel avec KPI, graphiques "camembert", et suivi financier par utilisateur.
- [ ] Suivi financier en temps réel et vérification du budget API.
- [ ] Envoi de rapport d'activité automatisé chaque jeudi à 04h00.

### Expérience Utilisateur (UI/UX)
- [x] Thème moderne (Gemini-like) et 100% compatible smartphones.
- [x] Refonte de la gestion des projets : séparation Épinglés (en haut) / Non Épinglés (Récents).
- [x] Arrêt de la création automatique de nouveau projet à l'ouverture.
- [x] Intégration permanente du logo AETHAS38 en local (Setup / Login / Dashboard).
- [ ] Indicateur visuel (Loader/Animation) signalant que l'IA AETHAS38 "réfléchit" ou travaille.
- [ ] Fonctionnalité de renommage manuel des discussions/projets.

### Moteur IA, Modèles & Fonctionnalités
- [ ] Pipeline multi-agents : 1 Rédacteur de prompt, jusqu'à 5 Travailleurs, 1 Concaténeur final.
- [ ] Extraction automatisée des modèles disponibles chez les fournisseurs (sauvegarde txt horodatée ex: "07/10/2026 à 10h00").
- [ ] Tâche planifiée (CRON) pour la mise à jour des modèles toutes les 12h (le timer se reset si mise à jour manuelle).
- [ ] Classement, filtrage (Gratuit/Payant) et catégorisation des modèles (Texte, Code, Image, Audio, Vidéo).
- [ ] Upload manuel du fichier d'extraction des modèles avec intégration dans l'interface filtrable.
- [ ] Traduction automatisée des descriptions des modèles via Ollama (local) ou Gemini.
- [ ] Interface d'aide à la décision pour le choix des modèles selon la tâche souhaitée.
- [ ] Mécanisme de fallback / termes génériques pour les appels API (protection contre le dépassement des quotas Gemini).
- [ ] Téléchargement des requêtes, réponses et fichiers générés (Excel, PDF, TXT, Images).