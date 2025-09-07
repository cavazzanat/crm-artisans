from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Client, Operation, Intervention, HistoriqueOperation

@login_required
def dashboard(request):
    # Version simplifiée pour éviter l'erreur 500
    context = {
        'user': request.user,
        'ca_mois': 0,
        'nb_clients': 0,
        'nb_en_attente_devis': 0,
        'nb_a_planifier': 0,
        'nb_realise': 0,
        'prochaines_operations': [],
    }
    return render(request, 'core/dashboard.html', context)

