from django.core.management import call_command
from django.http import HttpResponse

def force_migrate(request):
    """Vue temporaire pour déclencher les migrations"""
    try:
        call_command('migrate')
        return HttpResponse("Migration effectuée avec succès")
    except Exception as e:
        return HttpResponse(f"Erreur migration : {str(e)}")