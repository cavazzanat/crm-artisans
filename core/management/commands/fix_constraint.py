from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Fix client ID constraint to allow per-user uniqueness'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            try:
                # Supprimer l'ancienne contrainte unique globale
                cursor.execute("ALTER TABLE core_client DROP CONSTRAINT core_client_id_client_key;")
                self.stdout.write(self.style.SUCCESS("Ancienne contrainte supprimée"))
                
                # Ajouter une contrainte unique par utilisateur
                cursor.execute("ALTER TABLE core_client ADD CONSTRAINT core_client_user_id_unique UNIQUE (user_id, id_client);")
                self.stdout.write(self.style.SUCCESS("Nouvelle contrainte ajoutée (unique par utilisateur)"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erreur: {e}"))