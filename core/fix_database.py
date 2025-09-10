# core/fix_database.py
from django.db import connection

def fix_client_constraint():
    """Supprime les contraintes unique sur id_client et id_operation pour permettre plusieurs utilisateurs"""
    try:
        with connection.cursor() as cursor:
            # Supprimer la contrainte unique sur les clients
            cursor.execute("ALTER TABLE core_client DROP CONSTRAINT IF EXISTS core_client_id_client_key CASCADE;")
            print("Contrainte unique sur id_client supprimée")
            
            # Supprimer la contrainte unique sur les opérations
            cursor.execute("ALTER TABLE core_operation DROP CONSTRAINT IF EXISTS core_operation_id_operation_key CASCADE;")
            print("Contrainte unique sur id_operation supprimée")
            
            return True
                
    except Exception as e:
        print(f"Erreur lors de la suppression des contraintes : {e}")
        return False