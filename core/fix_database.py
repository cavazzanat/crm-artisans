# core/fix_database.py
from django.db import connection

def fix_client_constraint():
    """Supprime la contrainte unique sur id_client pour permettre plusieurs utilisateurs"""
    try:
        with connection.cursor() as cursor:
            # Vérifier si la contrainte existe avant de la supprimer
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'core_client' 
                AND constraint_name = 'core_client_id_client_key'
                AND table_schema = 'public'
            """)
            
            if cursor.fetchone():
                # Supprimer la contrainte unique problématique
                cursor.execute("ALTER TABLE core_client DROP CONSTRAINT core_client_id_client_key CASCADE;")
                print("Contrainte unique sur id_client supprimée avec succès")
                return True
            else:
                print("Contrainte déjà supprimée ou inexistante")
                return True
                
    except Exception as e:
        print(f"Erreur lors de la suppression de la contrainte : {e}")
        return False