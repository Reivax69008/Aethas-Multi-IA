# Roadmap Stratégique : Automatisme d'Attachement (Projet ATT-STIC)

## Pile Technologique (Stack) & Environnement
*   **Serveur Hôte (aethas38) :** 
    *   **OS :** Debian GNU/Linux 13 (trixie) - Kernel 6.12.107+deb13-amd64
    *   **CPU :** 1 Socket, 1 Thread par cœur
    *   **RAM :** 24 Go (23 GiB Total / 11 GiB Disponible)
    *   **Stockage :** 915 Go Total (801 Go libres / 8% utilisés)
    *   **Environnement :** Docker v29.7.2, Docker Compose v5.5.0, Python 3.13.5
*   **Orchestration / Déploiement :** Docker géré strictement via Dockge
*   **Gestion de version (VCS) :** Gitea (Auto-hébergé)
*   **Environnement de Développement (IDE) :** Visual Studio Code (Extensions: Remote-SSH, Docker, Python, Git Graph, Spreadsheet Viewer)
*   **Interface Web (UI) :** Conteneur léger (HTML/CSS/JS + Backend Python Flask/FastAPI). Intégration de la charte graphique SERFIM TIC et du logo Aethas38.
*   **Traitement de Données :** VBA (pour la macro locale) et moteur Python pour l'intégration web.

---

## Phase 0 : Audit Infrastructure et Initialisation de l'Environnement
*   [x] **Tâche 0.1 :** Exécution du script d'audit sur le serveur Debian pour définir les limites matérielles CPU/RAM.
*   [x] **Tâche 0.2 :** Configuration de l'environnement VSCode (liste des extensions nécessaires et configuration du workspace).
*   [x] **Tâche 0.3 :** Initialisation du dépôt sur Gitea et premier commit de cette roadmap.
*   [x] **Tâche 0.4 :** Création du Dashboard local et extraction des codes couleurs/typographie depuis `https://serfimtic.com` pour les assets graphiques.

## Phase 1 : Audit et Restructuration des Fichiers Excel (Data Foundation)
*   [ ] **Tâche 1.1 - Mécanisme de Sauvegarde Préalable :** Création du protocole garantissant que *chaque fichier* est sauvegardé avant modification, indicé sous le format `Semaine_Année_CodeAffaire`.
*   [ ] **Tâche 1.2 - Analyse du Fichier de Suivi (Commun) :** Normalisation de la structure pour lecture des données sans briser les formules complexes (Code affaire, N° de commande, Montants).
*   [ ] **Tâche 1.3 - Analyse du Fichier d'Attachement :** Mapping exact entre les données du suivi et les cellules de destination (en-tête de date, zones de cumul). Validation de l'intégrité des formules basiques existantes.
*   [ ] **Tâche 1.4 - Refonte du Fichier Macro :** Audit, nettoyage et restructuration des macros existantes en modules indépendants.

## Phase 2 : Développement du Conteneur Web (Interface & Backend)
*   [ ] **Tâche 2.1 - Maquette & UI :** Développement de l'interface utilisateur en appliquant la charte graphique SERFIM TIC et en intégrant le logo Aethas38.
*   [ ] **Tâche 2.2 - Création du Backend :** Script de gestion des uploads/downloads des fichiers de suivi et d'attachement.
*   [ ] **Tâche 2.3 - Dockge & Déploiement Local :** Écriture du `docker-compose.yml` optimisé pour le serveur Debian, testé localement puis déployé via Dockge.

## Phase 3 : Développement du Moteur de Traitement (Core Logic)
*   [ ] **Tâche 3.1 - Identification & Sécurité :** Script pour capturer l'identité de l'utilisateur (log web ou session) et horodatage de l'action.
*   [ ] **Tâche 3.2 - Injection des Métadonnées :** Remplissage automatique des en-têtes (Semaine/Année, Code Affaire, Numéro de Commande).
*   [ ] **Tâche 3.3 - Moteur de Calcul :** Logique d'addition des données de la semaine en cours avec l'historique pour générer la vue cumulative.

## Phase 4 : Sécurisation et Clôture (Safe Exit)
*   [ ] **Tâche 4.1 - Verrouillage des Données :** Implémentation de la fonction retournant dans le fichier de suivi pour verrouiller les cellules traitées.
*   [ ] **Tâche 4.2 - Onglet Justifications :** Préparation de l'architecture pour le second onglet dédié aux justifications hebdomadaires.

## Phase 5 : Finalisation, Traçabilité et Mises à Jour (Gitea)
*   [ ] **Tâche 5.1 - Rapport de Traitement :** Génération automatique d'une synthèse (lignes traitées, auteur, valeurs transférées, statut des verrouillages).
*   [ ] **Tâche 5.2 - Phase de Test (UAT) :** Tests complets de l'outil avec de faux jeux de données.
*   [ ] **Tâche 5.3 - Livraison Continue (CI/CD basique) :** Validation du flux de mise à jour entre le dépôt Gitea et les conteneurs Dockge.