# Créer la structure de dossiers :
# core/
# ├── management/
# │   ├── __init__.py
# │   └── commands/
# │       ├── __init__.py
# │       └── create_default_user.py

# ================================
# core/management/__init__.py (fichier vide)
# ================================


# ================================
# core/management/commands/__init__.py (fichier vide)
# ================================


# ================================
# core/management/commands/create_default_user.py
# ================================
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Créer un superutilisateur par défaut'

    def handle(self, *args, **options):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@test.com',
                password='admin123'
            )
            self.stdout.write(
                self.style.SUCCESS('Superutilisateur créé avec succès')
            )
        else:
            self.stdout.write('Superutilisateur existe déjà')

# ================================
# Modifier build.sh (ajouter à la fin)
# ================================
#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py create_default_user