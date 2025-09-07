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
