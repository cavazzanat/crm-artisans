# ================================
# core/views.py - Remplacer la vue dashboard existante
# ================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Client, Operation, Intervention, HistoriqueOperation

@login_required
def dashboard(request):
    # KPI du mois en cours
    now = timezone.now()
    debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # CA du mois (opérations payées)
    operations_payees = Operation.objects.filter(
        user=request.user,
        statut='paye',
        date_modification__gte=debut_mois
    )
    ca_mois = sum(op.montant_total for op in operations_payees)
    
    # Nombre de clients
    nb_clients = Client.objects.filter(user=request.user).count()
    
    # Opérations par statut
    nb_en_attente_devis = Operation.objects.filter(user=request.user, statut='en_attente_devis').count()
    nb_a_planifier = Operation.objects.filter(user=request.user, statut='a_planifier').count()
    nb_realise = Operation.objects.filter(user=request.user, statut='realise').count()
    
    # Prochaines opérations (max 10)
    prochaines_operations = Operation.objects.filter(
        user=request.user,
        statut='planifie',
        date_prevue__gte=now
    ).select_related('client').order_by('date_prevue')[:10]
    
    context = {
        'ca_mois': ca_mois,
        'nb_clients': nb_clients,
        'nb_en_attente_devis': nb_en_attente_devis,
        'nb_a_planifier': nb_a_planifier,
        'nb_realise': nb_realise,
        'prochaines_operations': prochaines_operations,
    }
    return render(request, 'core/dashboard.html', context)

# ================================
# templates/core/dashboard.html - CRÉER CE FICHIER
# ================================