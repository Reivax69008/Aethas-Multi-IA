import os
import shutil
from datetime import datetime

def securiser_fichier_excel(chemin_original, code_affaire):
    """
    Crée une copie de sauvegarde d'un fichier Excel avant traitement.
    Nomenclature : Semaine_Annee_CodeAffaire
    """
    if not os.path.exists(chemin_original):
        print(f"❌ Erreur : Le fichier '{chemin_original}' est introuvable.")
        return None

    # 1. Obtenir la date actuelle
    aujourdhui = datetime.now()
    annee = aujourdhui.strftime("%Y")
    semaine = aujourdhui.strftime("%V") # %V donne le numéro de semaine ISO

    # 2. Créer le dossier de sauvegarde s'il n'existe pas
    dossier_backup = "backups_excel"
    os.makedirs(dossier_backup, exist_ok=True)

    # 3. Extraire l'extension (.xlsx ou .xlsm)
    _, extension = os.path.splitext(chemin_original)

    # 4. Construire le nouveau nom
    nouveau_nom = f"S{semaine}_{annee}_{code_affaire}{extension}"
    chemin_destination = os.path.join(dossier_backup, nouveau_nom)

    # 5. Copier le fichier
    shutil.copy2(chemin_original, chemin_destination)
    print(f"✅ Fichier sécurisé : {chemin_destination}")
    
    return chemin_destination

# --- TEST DU MODULE ---
if __name__ == "__main__":
    # Test à blanc : on crée un faux fichier Excel pour vérifier que le script fonctionne
    fichier_test = "mon_suivi_financier.xlsx"
    with open(fichier_test, "w") as f:
        f.write("Données de test")
        
    securiser_fichier_excel(fichier_test, "CHANTIER_SERFIM_01")