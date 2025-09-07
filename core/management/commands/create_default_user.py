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