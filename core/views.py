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

# ================================
# templates/core/dashboard.html - CRÉER CE FICHIER
# ================================

@login_required
def operations_list(request):
    operations = Operation.objects.filter(user=request.user).select_related('client')
    
    # Filtres
    statut_filtre = request.GET.get('statut')
    ville_filtre = request.GET.get('ville')
    search = request.GET.get('search')
    tri = request.GET.get('tri', 'date_prevue')
    
    if statut_filtre:
        operations = operations.filter(statut=statut_filtre)
    
    if ville_filtre:
        operations = operations.filter(client__ville__icontains=ville_filtre)
    
    if search:
        operations = operations.filter(
            Q(client__nom__icontains=search) |
            Q(client__prenom__icontains=search) |
            Q(client__ville__icontains=search) |
            Q(client__telephone__icontains=search) |
            Q(type_prestation__icontains=search) |
            Q(adresse_intervention__icontains=search)
        )
    
    # Tri
    if tri == 'date_prevue_desc':
        operations = operations.order_by('-date_prevue')
    elif tri == 'date_prevue':
        operations = operations.order_by('date_prevue')
    else:
        operations = operations.order_by('-date_creation')
    
    # Villes pour le filtre dropdown
    villes = Client.objects.filter(user=request.user).values_list('ville', flat=True).distinct().order_by('ville')
    
    # Titre dynamique
    titre_filtre = "Toutes les opérations"
    if statut_filtre:
        statut_display = dict(Operation.STATUTS).get(statut_filtre, statut_filtre)
        titre_filtre = f"Opérations : {statut_display}"
    
    context = {
        'operations': operations,
        'villes': villes,
        'statut_filtre': statut_filtre,
        'ville_filtre': ville_filtre,
        'search': search,
        'tri': tri,
        'titre_filtre': titre_filtre,
        'statuts': Operation.STATUTS,
    }
    return render(request, 'core/operations.html', context)
