# ================================
# core/views.py - Version refactorisée avec devis multiples
# ================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum,Max, Count, Subquery, Exists, OuterRef
from django.db import models
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout
from django.core.management import call_command
from decimal import Decimal
from django.utils import timezone
import io
import sys
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.contrib.auth.hashers import check_password

# ✅ IMPORTS MODIFIÉS
from .models import (
    Client, 
    Operation, 
    Devis,           # ← NOUVEAU
    LigneDevis,      # ← NOUVEAU
    Intervention, 
    HistoriqueOperation, 
    Echeance, 
    ProfilEntreprise,
    PassageOperation
)

from .fix_database import fix_client_constraint
import re
from .pdf_generator import generer_devis_pdf


@login_required
def dashboard(request):
    """Dashboard simplifié : KPI essentiels + Calendrier"""
    #fix_client_constraint()
    try:
        
        today = timezone.now().date()
        
        # ========================================
        # KPI ESSENTIELS (INCHANGÉS)
        # ========================================
        nb_clients = Client.objects.filter(user=request.user).count()
        
        debut_mois = timezone.now().replace(day=1)
        
        ca_mois = Echeance.objects.filter(
            operation__user=request.user,
            paye=True,
            date_echeance__gte=debut_mois
        ).aggregate(total=Sum('montant'))['total'] or 0
        
        # ✅ Compter les DEVIS en attente (envoyés, non expirés, non répondus)
        nb_en_attente_devis = 0
        for op in Operation.objects.filter(user=request.user, avec_devis=True):
            for devis in op.devis_set.filter(statut='envoye', date_envoi__isnull=False):
                if not devis.est_expire:
                    nb_en_attente_devis += 1
        
        nb_a_planifier = Operation.objects.filter(
            user=request.user, 
            statut='a_planifier'
        ).count()
        
        operations_realises = Operation.objects.filter(
            user=request.user,
            statut='realise'
        ).prefetch_related('echeances')
        
        nb_paiements_retard = 0
        nb_operations_sans_paiement = 0
        
        for op in operations_realises:
            retards = op.echeances.filter(
                paye=False,
                date_echeance__lt=timezone.now().date()
            )
            nb_paiements_retard += retards.count()
            
            total_planifie = op.echeances.aggregate(
                total=Sum('montant')
            )['total'] or 0
            
            reste_a_planifier = op.montant_total - total_planifie
            
            if reste_a_planifier > 0:
                nb_operations_sans_paiement += 1
        
                # ========================================
        # NOUVEAUX KPI ESSENTIELS
        # ========================================
        
        # 1. URGENCES (total)
        # Déjà calculé dans operations_list, on le refait ici pour le dashboard
        
        # Paiements en retard
        ops_paiements_retard = []
        for op in Operation.objects.filter(user=request.user, statut='realise').prefetch_related('echeances'):
            retards = op.echeances.filter(paye=False, date_echeance__lt=today)
            if retards.exists():
                ops_paiements_retard.append(op.id)
        
        nb_paiements_retard_dashboard = len(ops_paiements_retard)
        
        # Devis expirés
        ops_devis_expires = []
        for op in Operation.objects.filter(user=request.user, avec_devis=True).prefetch_related('devis_set'):
            for devis in op.devis_set.filter(statut='envoye'):
                if devis.est_expire:
                    ops_devis_expires.append(op.id)
                    break
        
        nb_devis_expire_dashboard = len(ops_devis_expires)
        
        # Interventions aujourd'hui
        nb_aujourdhui = PassageOperation.objects.filter(
            operation__user=request.user,
            date_prevue__date=today,
            realise=False
        ).values('operation').distinct().count()
        
        # Interventions demain
        demain = today + timedelta(days=1)
        nb_demain = PassageOperation.objects.filter(
            operation__user=request.user,
            date_prevue__date=demain,
            realise=False
        ).values('operation').distinct().count()
        
        # Total urgences (sans doublons)
        ids_urgences = set(ops_paiements_retard + ops_devis_expires)
        # + opérations avec passage aujourd'hui/demain
        ids_aujourdhui = set(PassageOperation.objects.filter(
            operation__user=request.user,
            date_prevue__date=today,
            realise=False
        ).values_list('operation_id', flat=True))
        ids_demain = set(PassageOperation.objects.filter(
            operation__user=request.user,
            date_prevue__date=demain,
            realise=False
        ).values_list('operation_id', flat=True))
        
        ids_urgences = ids_urgences | ids_aujourdhui | ids_demain
        nb_urgences = len(ids_urgences)
        
        # 2. À ENCAISSER (réalisées avec reste à payer)
        nb_a_encaisser = 0
        for op in Operation.objects.filter(user=request.user, statut='realise').prefetch_related('echeances'):
            total_paye = op.echeances.filter(paye=True).aggregate(total=Sum('montant'))['total'] or 0
            if op.montant_total and total_paye < op.montant_total:
                nb_a_encaisser += 1
        
        # ========================================
        # 🔥 CALENDRIER - VERSION PASSAGES
        # ========================================
        start_date = today - timedelta(days=30)
        end_date = today + timedelta(days=14)

        # ========================================
        # 🔥 CALENDRIER - VERSION HYBRIDE
        # ========================================
        
        # 1️⃣ Passages AVEC dates (dans la période)
        passages_avec_dates = PassageOperation.objects.filter(
            operation__user=request.user
        ).filter(
            Q(date_prevue__isnull=False, date_prevue__date__gte=start_date, date_prevue__date__lte=end_date) |
            Q(date_realisation__isnull=False, date_realisation__date__gte=start_date, date_realisation__date__lte=end_date)
        ).select_related('operation', 'operation__client')
        
        # ✅ SEULEMENT les passages avec dates (pas les "à planifier")
        passages_calendrier = list(passages_avec_dates)

        calendar_events = []
        
        for passage in passages_calendrier:
            op = passage.operation
            
            #   ✅ Utiliser date_prevue du PASSAGE en priorité
            # Si pas de date, afficher à aujourd'hui (pour les "à planifier")
            date_affichage = passage.date_prevue or passage.date_realisation or timezone.now()

            
            is_past = date_affichage < timezone.now()
            
            # ✅ CODE COULEUR basé sur le STATUT DU PASSAGE
            if passage.realise:
                # Si passage réalisé mais opération pas payée
                if op.statut == 'paye':
                    color_class = 'event-paye'
                    status_text = "Payé"
                else:
                    color_class = 'event-realise'
                    status_text = "Réalisé"
            elif passage.est_en_retard:
                # Passage prévu dans le passé mais pas réalisé
                color_class = 'event-a-traiter'
                status_text = "À traiter (en retard)"
            elif passage.est_planifie:
                # Passage planifié dans le futur
                color_class = 'event-planifie'
                status_text = "Planifié"
            else:
                # Passage sans date prévue
                color_class = 'event-default'
                status_text = "À planifier"
            
            # Détecter retards paiement de l'OPÉRATION
            paiements_retard_op = op.echeances.filter(
                paye=False,
                date_echeance__lt=timezone.now().date()
            )
            
            has_retard = paiements_retard_op.exists()
            nb_retards_op = paiements_retard_op.count()
            montant_retard_op = paiements_retard_op.aggregate(
                total=Sum('montant')
            )['total'] or 0
            
            # ✅ Déterminer le statut brut pour le JS
            if passage.realise:
                statut_brut = 'realise'
            elif passage.est_en_retard:
                statut_brut = 'a_traiter'
            elif passage.est_planifie:
                statut_brut = 'planifie'
            else:
                statut_brut = 'a_planifier'

            calendar_events.append({
                'id': op.id,
                'passage_id': passage.id,
                'client_nom': f"{op.client.nom} {op.client.prenom}",
                'service': f"{op.type_prestation} - Passage #{passage.numero}",
                'date': date_affichage.strftime('%Y-%m-%d'),
                'time': date_affichage.strftime('%H:%M'),
                'address': op.adresse_intervention,
                'phone': op.client.telephone,
                'url': f'/operations/{op.id}/',
                'statut': statut_brut,  # ✅ Valeur brute pour JS
                'statut_display': status_text,  # ✅ Texte pour affichage
                'color_class': color_class,
                'is_past': is_past,
                'commentaires': passage.commentaire or op.commentaires or '',
                'has_retard_paiement': has_retard,
                'nb_retards': nb_retards_op,
                'montant_retard': float(montant_retard_op)
            })
        
        context = {
            # KPI essentiels (NOUVEAU)
            'nb_urgences': nb_urgences,
            'nb_aujourdhui': nb_aujourdhui,
            'nb_en_attente_devis': nb_en_attente_devis,  # Déjà existant
            'nb_a_encaisser': nb_a_encaisser,
            'ca_mois': ca_mois,  # Déjà existant
            
            # Calendrier (existant)
            'calendar_events_json': json.dumps(calendar_events),
            'calendar_events': calendar_events,
            
            # Anciens KPI (garder pour compatibilité si besoin)
            'nb_clients': nb_clients,
            'nb_a_planifier': nb_a_planifier,
            'nb_paiements_retard': nb_paiements_retard,
            'nb_operations_sans_paiement': nb_operations_sans_paiement,
        }
        
        return render(request, 'core/dashboard.html', context)
        
    except Exception as e:
        return HttpResponse(f"<h1>CRM Artisans</h1><p>Erreur : {str(e)}</p>")

# ════════════════════════════════════════════════════════════════════════════════
# FONCTION 1 : COMPTEURS DEVIS
# ════════════════════════════════════════════════════════════════════════════════

def get_devis_counters(request, all_operations):
    """
    Calcule les compteurs pour l'onglet Devis et ses sous-filtres.
    
    Retourne un dictionnaire avec :
    - nb_devis_total : Toutes les opérations avec au moins un devis
    - nb_devis_brouillon : Dernier devis en statut 'brouillon'
    - nb_devis_pret : Dernier devis en statut 'pret' (à envoyer)
    - nb_devis_envoye : Dernier devis en statut 'envoye' et NON expiré
    - nb_devis_expire : Dernier devis en statut 'envoye' et expiré
    - nb_devis_accepte : Dernier devis en statut 'accepte'
    - nb_devis_refuse : Dernier devis en statut 'refuse'
    
    IMPORTANT : On compte par OPÉRATION (pas par devis), basé sur le DERNIER devis de chaque opération.
    """
    
    # Filtrer les opérations avec devis
    operations_avec_devis = all_operations.filter(avec_devis=True).prefetch_related('devis_set')
    
    # Initialiser les compteurs
    nb_devis_total = 0
    nb_devis_brouillon = 0
    nb_devis_pret = 0
    nb_devis_envoye = 0
    nb_devis_expire = 0
    nb_devis_accepte = 0
    nb_devis_refuse = 0
    
    # Parcourir chaque opération avec devis
    for op in operations_avec_devis:
        # Récupérer le DERNIER devis (version la plus élevée)
        dernier_devis = op.devis_set.order_by('-version').first()
        
        if not dernier_devis:
            continue
        
        # Compter le total
        nb_devis_total += 1
        
        # Classer selon le statut du dernier devis
        if dernier_devis.statut == 'brouillon':
            nb_devis_brouillon += 1
            
        elif dernier_devis.statut == 'pret':
            nb_devis_pret += 1
            
        elif dernier_devis.statut == 'envoye':
            # Vérifier si expiré ou en attente
            if dernier_devis.est_expire:
                nb_devis_expire += 1
            else:
                nb_devis_envoye += 1
                
        elif dernier_devis.statut == 'accepte':
            nb_devis_accepte += 1
            
        elif dernier_devis.statut == 'refuse':
            nb_devis_refuse += 1
    
    return {
        'nb_devis_total': nb_devis_total,
        'nb_devis_brouillon': nb_devis_brouillon,
        'nb_devis_pret': nb_devis_pret,
        'nb_devis_envoye': nb_devis_envoye,
        'nb_devis_expire': nb_devis_expire,
        'nb_devis_accepte': nb_devis_accepte,
        'nb_devis_refuse': nb_devis_refuse,
    }

def filter_operations_by_devis(request, filtre_actif, sous_filtre, all_operations):
    """
    Filtre les opérations selon le sous-filtre devis sélectionné.
    
    Paramètres :
    - request : La requête HTTP
    - filtre_actif : Le filtre principal ('devis' pour cet onglet)
    - sous_filtre : Le sous-filtre ('brouillon', 'pret', 'envoye', 'expire', 'accepte', 'refuse')
    - all_operations : QuerySet de toutes les opérations
    
    Retourne :
    - QuerySet filtré des opérations, ou None si filtre_actif != 'devis'
    """
    
    # Ne traiter que si on est sur l'onglet Devis
    if filtre_actif != 'devis':
        return None
    
    # Filtrer les opérations avec devis
    operations_avec_devis = all_operations.filter(avec_devis=True).prefetch_related('devis_set')
    
    # Liste des IDs à retourner
    filtered_ids = []
    
    # Parcourir chaque opération
    for op in operations_avec_devis:
        # Récupérer le DERNIER devis
        dernier_devis = op.devis_set.order_by('-version').first()
        
        if not dernier_devis:
            continue
        
        # Appliquer le filtre selon le sous-filtre
        should_include = False
        
        if not sous_filtre:
            # Pas de sous-filtre = TOUS les devis
            should_include = True
            
        elif sous_filtre == 'brouillon':
            should_include = (dernier_devis.statut == 'brouillon')
            
        elif sous_filtre == 'pret':
            should_include = (dernier_devis.statut == 'pret')
            
        elif sous_filtre == 'envoye':
            # En attente = envoyé mais PAS expiré
            should_include = (dernier_devis.statut == 'envoye' and not dernier_devis.est_expire)
            
        elif sous_filtre == 'expire':
            # Expiré = envoyé ET date dépassée
            should_include = (dernier_devis.statut == 'envoye' and dernier_devis.est_expire)
            
        elif sous_filtre == 'accepte':
            should_include = (dernier_devis.statut == 'accepte')
            
        elif sous_filtre == 'refuse':
            should_include = (dernier_devis.statut == 'refuse')
        
        if should_include:
            filtered_ids.append(op.id)
    
    # Retourner le QuerySet filtré
    return all_operations.filter(id__in=filtered_ids)


@login_required
def operations_list(request):
    """
    Page Opérations avec filtres intelligents :
    - Urgences (paiements retard, devis expirés, interventions aujourd'hui/demain)
    - À faire (à planifier, devis brouillon, paiements non planifiés)
    - En cours (triées par dernière activité)
    - À venir (interventions futures)
    - À encaisser (réalisées non payées)
    - Archivées (payées)
    """
    
    today = timezone.now().date()
    now = timezone.now()
    demain = today + timedelta(days=1)
    fin_semaine = today + timedelta(days=(6 - today.weekday()))  # Dimanche
    fin_semaine_prochaine = fin_semaine + timedelta(days=7)
    fin_mois = today.replace(day=28) + timedelta(days=4)
    fin_mois = fin_mois - timedelta(days=fin_mois.day)  # Dernier jour du mois
    
    # ========================================
    # GESTION DE LA PÉRIODE (CONSERVÉ)
    # ========================================
    periode = request.GET.get('periode', 'this_month')
    mois_param = request.GET.get('mois', '')
    nav = request.GET.get('nav', '')
    
    if mois_param and nav:
        try:
            date_ref = datetime.strptime(mois_param, '%Y-%m').date()
            if nav == 'prev':
                date_ref = date_ref - relativedelta(months=1)
            elif nav == 'next':
                date_ref = date_ref + relativedelta(months=1)
            
            periode_start = date_ref.replace(day=1)
            periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
            periode = 'custom'
        except:
            periode_start = today.replace(day=1)
            periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
    elif mois_param:
        try:
            date_ref = datetime.strptime(mois_param, '%Y-%m').date()
            periode_start = date_ref.replace(day=1)
            periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
            periode = 'custom'
        except:
            periode_start = today.replace(day=1)
            periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
    elif periode == 'this_month':
        periode_start = today.replace(day=1)
        periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
    elif periode == 'last_month':
        periode_start = (today.replace(day=1) - relativedelta(months=1))
        periode_end = today.replace(day=1) - timedelta(days=1)
    elif periode == 'last_3':
        periode_start = (today.replace(day=1) - relativedelta(months=2))
        periode_end = (periode_start + relativedelta(months=3)) - timedelta(days=1)
    elif periode == 'ytd':
        periode_start = today.replace(month=1, day=1)
        periode_end = today
    else:
        periode_start = today.replace(day=1)
        periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
    
    # ========================================
    # RÉCUPÉRER TOUTES LES OPÉRATIONS
    # ========================================
    all_operations = Operation.objects.filter(
        user=request.user
    ).select_related('client').prefetch_related(
        'interventions', 'echeances', 'historique', 'devis_set', 'passages'
    )
    
    # --- COMPTEURS DEVIS ---
    devis_counters = get_devis_counters(request, all_operations)
    
    # ========================================
    # CALCULS FINANCIERS (CONSERVÉ)
    # ========================================
    operations_periode = Operation.objects.filter(
        user=request.user,
        statut__in=['realise', 'paye'],
        date_realisation__gte=periode_start,
        date_realisation__lte=periode_end
    ).prefetch_related('echeances')

    ca_encaisse = 0
    ca_en_attente_total = 0
    ca_retard = 0
    ca_non_planifies = 0

    for op in operations_periode:
        montant_total = op.montant_total
        montant_paye = op.echeances.filter(paye=True).aggregate(total=Sum('montant'))['total'] or 0
        ca_encaisse += montant_paye
        
        total_planifie = op.echeances.aggregate(total=Sum('montant'))['total'] or 0
        reste = montant_total - montant_paye
        
        if reste > 0:
            ca_en_attente_total += reste
        
        retards = op.echeances.filter(paye=False, date_echeance__lt=today)
        if retards.exists():
            montant_retard = retards.aggregate(total=Sum('montant'))['total'] or 0
            ca_retard += montant_retard
        
        reste_a_planifier = montant_total - total_planifie
        if reste_a_planifier > 0:
            ca_non_planifies += reste_a_planifier

    # CA Prévisionnel 30 jours
    date_dans_30j = today + timedelta(days=30)
    operations_previsionnel = Operation.objects.filter(
        user=request.user,
        statut='planifie',
        date_prevue__gte=today,
        date_prevue__lte=date_dans_30j
    )
    ca_previsionnel_30j = sum(op.montant_total for op in operations_previsionnel if op.montant_total)
    
    # Variation vs période précédente
    duree = (periode_end - periode_start).days
    periode_prec_start = periode_start - timedelta(days=duree + 1)
    periode_prec_end = periode_start - timedelta(days=1)
    
    ca_encaisse_prec = Echeance.objects.filter(
        operation__user=request.user,
        operation__date_realisation__gte=periode_prec_start,
        operation__date_realisation__lte=periode_prec_end,
        paye=True
    ).aggregate(total=Sum('montant'))['total'] or 0
    
    if ca_encaisse_prec > 0:
        ca_encaisse_var = int(((ca_encaisse - ca_encaisse_prec) / ca_encaisse_prec) * 100)
    else:
        ca_encaisse_var = 0 if ca_encaisse == 0 else 100
    
    # ========================================
    # CALCUL DES COMPTEURS PAR CATÉGORIE
    # ========================================
    
    # --- URGENCES ---
    # 1. Paiements en retard
    ops_paiements_retard = []
    for op in all_operations.filter(statut='realise'):
        retards = op.echeances.filter(paye=False, date_echeance__lt=today)
        if retards.exists():
            ops_paiements_retard.append(op.id)
    
    nb_paiements_retard = len(ops_paiements_retard)
    
    # 2. Devis expirés
    ops_devis_expires = []
    for op in all_operations.filter(avec_devis=True):
        for devis in op.devis_set.filter(statut='envoye'):
            if devis.est_expire:
                ops_devis_expires.append(op.id)
                break
    
    nb_devis_expire = len(ops_devis_expires)
    
    # 3. Interventions aujourd'hui
    ops_aujourdhui = list(all_operations.filter(
        Q(date_prevue__date=today) | 
        Q(passages__date_prevue__date=today, passages__realise=False)
    ).values_list('id', flat=True).distinct())
    
    nb_aujourdhui = len(ops_aujourdhui)
    
    # 4. Interventions demain
    ops_demain = list(all_operations.filter(
        Q(date_prevue__date=demain) | 
        Q(passages__date_prevue__date=demain, passages__realise=False)
    ).values_list('id', flat=True).distinct())
    
    nb_demain = len(ops_demain)
    
    # Total urgences (sans doublons)
    ids_urgences = set(ops_paiements_retard + ops_devis_expires + ops_aujourdhui + ops_demain)
    nb_urgences = len(ids_urgences)
    
    # --- À FAIRE ---
    nb_a_planifier = all_operations.filter(statut='a_planifier').count()
    
    nb_devis_brouillon = Devis.objects.filter(
        operation__user=request.user,
        statut='brouillon'
    ).values('operation').distinct().count()
    
    # Paiements non planifiés
    ops_paiements_non_planifies = []
    for op in all_operations.filter(statut='realise'):
        total_planifie = op.echeances.aggregate(total=Sum('montant'))['total'] or 0
        if op.montant_total and total_planifie < op.montant_total:
            ops_paiements_non_planifies.append(op.id)
    
    nb_operations_sans_paiement = len(ops_paiements_non_planifies)
    
    # Total à faire
    ids_a_faire = set()
    ids_a_faire.update(all_operations.filter(statut='a_planifier').values_list('id', flat=True))
    ids_a_faire.update(Devis.objects.filter(
        operation__user=request.user,
        statut='brouillon'
    ).values_list('operation_id', flat=True))
    ids_a_faire.update(ops_paiements_non_planifies)
    ids_a_faire -= ids_urgences
    nb_a_faire = len(ids_a_faire)
    
    # --- EN COURS ---
    statuts_en_cours = ['en_attente_devis', 'a_planifier', 'planifie', 'en_cours', 'realise']
    ids_en_cours = set(all_operations.filter(statut__in=statuts_en_cours).values_list('id', flat=True))
    ids_en_cours -= ids_urgences
    nb_en_cours = len(ids_en_cours)
    
    # --- À VENIR ---
    ops_a_venir = all_operations.filter(
        Q(statut='planifie', date_prevue__gte=now) |
        Q(passages__date_prevue__gte=now, passages__realise=False)
    ).distinct()
    nb_a_venir = ops_a_venir.count()
    
    # --- À ENCAISSER ---
    ops_a_encaisser_ids = []
    for op in all_operations.filter(statut='realise'):
        total_paye = op.echeances.filter(paye=True).aggregate(total=Sum('montant'))['total'] or 0
        if op.montant_total and total_paye < op.montant_total:
            ops_a_encaisser_ids.append(op.id)
    
    nb_a_encaisser = len(ops_a_encaisser_ids)
    
    # --- ARCHIVÉES ---
    nb_archivees = all_operations.filter(statut='paye').count()
    
    # --- AUTRES COMPTEURS (CONSERVÉS) ---
    nb_total = all_operations.count()
    nb_planifie = all_operations.filter(statut='planifie').count()
    nb_realise = all_operations.filter(statut='realise').count()
    nb_paye = all_operations.filter(statut='paye').count()
    
    # Compteurs devis
    nb_devis_genere_non_envoye = Devis.objects.filter(
        operation__user=request.user,
        statut='pret'
    ).count()
    
    nb_sans_devis = Operation.objects.filter(
        user=request.user,
        avec_devis=True
    ).annotate(nb_devis=Count('devis_set')).filter(nb_devis=0).count()
    
    nb_devis_en_attente = 0
    for op in Operation.objects.filter(user=request.user, avec_devis=True):
        for devis in op.devis_set.filter(statut='envoye', date_envoi__isnull=False):
            if not devis.est_expire:
                nb_devis_en_attente += 1
    
    # À traiter (passages en retard)
    passages_en_retard = PassageOperation.objects.filter(
        operation__user=request.user,
        date_prevue__lt=now,
        realise=False
    ).values_list('operation_id', flat=True).distinct()
    nb_a_traiter = len(set(passages_en_retard))
    
    # ========================================
    # FILTRAGE SELON L'ONGLET SÉLECTIONNÉ
    # ========================================
    filtre = request.GET.get('filtre', 'toutes')
    sous_filtre = request.GET.get('sous', '')
    recherche = request.GET.get('recherche', '')
    tri = request.GET.get('tri', 'recent')  # recent, ancien, activite
    
    # Commencer avec toutes les opérations
    operations = all_operations
    
    # ========================================
    # NOUVEAUX FILTRES INTELLIGENTS
    # ========================================
    if filtre == 'urgences':
        if sous_filtre == 'retards':
            operations = operations.filter(id__in=ops_paiements_retard)
        elif sous_filtre == 'expires':
            operations = operations.filter(id__in=ops_devis_expires)
        elif sous_filtre == 'aujourdhui':
            operations = operations.filter(id__in=ops_aujourdhui)
        elif sous_filtre == 'demain':
            operations = operations.filter(id__in=ops_demain)
        else:
            operations = operations.filter(id__in=ids_urgences)
        
        for op in operations:
            op.est_urgent = True
            
    elif filtre == 'devis':
        operations = filter_operations_by_devis(request, filtre, sous_filtre, all_operations)
    
    elif filtre == 'a_faire':
        if sous_filtre == 'a_planifier':
            operations = operations.filter(statut='a_planifier')
        elif sous_filtre == 'devis_brouillon':
            ids_brouillon = Devis.objects.filter(
                operation__user=request.user,
                statut='brouillon'
            ).values_list('operation_id', flat=True)
            operations = operations.filter(id__in=ids_brouillon)
        elif sous_filtre == 'paiements_non_planifies':
            operations = operations.filter(id__in=ops_paiements_non_planifies)
        else:
            operations = operations.filter(id__in=ids_a_faire)
            
    elif filtre == 'en_cours':
        operations = operations.filter(id__in=ids_en_cours)
        
    elif filtre == 'toutes':
        # Toutes les opérations, pas de filtre
        pass
        
    elif filtre == 'a_venir':
        operations = ops_a_venir
        
        if sous_filtre == 'semaine':
            operations = operations.filter(
                Q(date_prevue__date__lte=fin_semaine) |
                Q(passages__date_prevue__date__lte=fin_semaine)
            ).distinct()
        elif sous_filtre == 'semaine_prochaine':
            operations = operations.filter(
                Q(date_prevue__date__gt=fin_semaine, date_prevue__date__lte=fin_semaine_prochaine) |
                Q(passages__date_prevue__date__gt=fin_semaine, passages__date_prevue__date__lte=fin_semaine_prochaine)
            ).distinct()
        elif sous_filtre == 'mois':
            operations = operations.filter(
                Q(date_prevue__date__lte=fin_mois) |
                Q(passages__date_prevue__date__lte=fin_mois)
            ).distinct()
        elif sous_filtre == 'plus_tard':
            operations = operations.filter(
                Q(date_prevue__date__gt=fin_mois) |
                Q(passages__date_prevue__date__gt=fin_mois)
            ).distinct()
        
        operations = operations.order_by('date_prevue')
        
    elif filtre == 'a_encaisser':
        operations = operations.filter(id__in=ops_a_encaisser_ids)
        
    elif filtre == 'archivees':
        operations = operations.filter(statut='paye')
        operations = operations.order_by('-date_paiement', '-date_modification')
    
    # ========================================
    # ANCIENS FILTRES (CONSERVÉS POUR COMPATIBILITÉ)
    # ========================================
    elif filtre == 'brouillon':
        operations = operations.filter(avec_devis=True).filter(
            Exists(Devis.objects.filter(operation=OuterRef('pk'), statut='brouillon'))
        )
        
    elif filtre == 'sans_devis':
        operations = operations.annotate(nb_devis=Count('devis_set')).filter(
            avec_devis=True, nb_devis=0
        )

    elif filtre == 'genere_non_envoye':
        operations = operations.filter(avec_devis=True).filter(
            Exists(Devis.objects.filter(operation=OuterRef('pk'), statut='pret'))
        )
        
    elif filtre == 'devis_en_attente':
        operations_en_attente_ids = []
        for op in operations.filter(avec_devis=True):
            devis_en_attente = op.devis_set.filter(statut='envoye', date_envoi__isnull=False)
            for devis in devis_en_attente:
                if devis.date_limite and devis.date_limite >= today:
                    operations_en_attente_ids.append(op.id)
                    break
                elif not devis.date_limite:
                    operations_en_attente_ids.append(op.id)
                    break
        operations = operations.filter(id__in=operations_en_attente_ids)

    elif filtre == 'expire':
        operations = operations.filter(id__in=ops_devis_expires)

    elif filtre == 'a_traiter':
        operations_planifiees_retard = Operation.objects.filter(
            user=request.user, statut='planifie', date_prevue__lt=now
        ).values_list('id', flat=True)
        ids_a_traiter = set(passages_en_retard) | set(operations_planifiees_retard)
        operations = operations.filter(id__in=ids_a_traiter)

    elif filtre == 'retards':
        operations = operations.filter(id__in=ops_paiements_retard)
        for op in operations:
            premier_retard = op.echeances.filter(paye=False, date_echeance__lt=today).order_by('date_echeance').first()
            if premier_retard:
                op.premier_retard = premier_retard
                op.jours_retard = (today - premier_retard.date_echeance).days

    elif filtre == 'non_planifies':
        operations = operations.filter(id__in=ops_paiements_non_planifies)
        for op in operations:
            total_planifie = op.echeances.aggregate(total=Sum('montant'))['total'] or 0
            op.reste_a_planifier = op.montant_total - total_planifie

    elif filtre in ['a_planifier', 'planifie', 'realise', 'paye']:
        operations = operations.filter(statut=filtre)
    
    # ========================================
    # RECHERCHE
    # ========================================
    if recherche:
        operations = operations.filter(
            Q(client__nom__icontains=recherche) |
            Q(client__prenom__icontains=recherche) |
            Q(client__telephone__icontains=recherche) |
            Q(client__ville__icontains=recherche) |
            Q(type_prestation__icontains=recherche) |
            Q(id_operation__icontains=recherche) |
            Q(adresse_intervention__icontains=recherche) |
            Q(commentaires__icontains=recherche)
        )
    
    # ========================================
    # TRI DYNAMIQUE
    # ========================================
    if tri == 'ancien':
        operations = operations.order_by('date_creation')
    elif tri == 'activite':
        operations = operations.order_by('-date_modification')
    else:  # recent (par défaut)
        operations = operations.order_by('-date_creation')
    
    # ========================================
    # ENRICHIR LES OPÉRATIONS
    # ========================================
    operations_list = list(operations)
    
    for op in operations_list:
        # Dernier devis (pour le template)
        if op.avec_devis:
            op.dernier_devis_obj = op.devis_set.order_by('-version').first()
        else:
            op.dernier_devis_obj = None
        
        # Dernière action depuis l'historique
        derniere_entree = op.historique.order_by('-date').first()
        op.derniere_action = derniere_entree.action[:50] if derniere_entree else None
        
        # Reste à payer
        total_paye = op.echeances.filter(paye=True).aggregate(total=Sum('montant'))['total'] or 0
        op.reste_a_payer = (op.montant_total or 0) - total_paye
        
        # Prochaine étape
        op.prochaine_etape = None
        if op.avec_devis:
            dernier_devis = op.dernier_devis
            if dernier_devis:
                if dernier_devis.statut == 'brouillon':
                    op.prochaine_etape = "Compléter le devis"
                elif dernier_devis.statut == 'pret':
                    op.prochaine_etape = "Envoyer le devis"
                elif dernier_devis.statut == 'envoye' and not dernier_devis.est_expire:
                    op.prochaine_etape = "Attendre réponse"
                elif dernier_devis.statut == 'accepte' and op.statut == 'a_planifier':
                    op.prochaine_etape = "Planifier"
        else:
            if op.statut == 'a_planifier':
                op.prochaine_etape = "Planifier"
            elif op.statut == 'planifie':
                op.prochaine_etape = "Réaliser"
            elif op.statut == 'realise':
                op.prochaine_etape = "Encaisser"
        
        # Flag urgent si pas déjà défini
        if not hasattr(op, 'est_urgent'):
            op.est_urgent = op.id in ids_urgences
    
    # ========================================
    # CONTEXTE
    # ========================================
    context = {
        'operations': operations_list,
        'total_operations': len(operations_list),
        'filtre_actif': filtre,
        'sous_filtre': sous_filtre,
        'recherche': recherche,
        'tri_actif': tri,
        
        # Période (conservé)
        'periode': periode,
        'periode_start': periode_start,
        'periode_end': periode_end,
        
        # Financier (conservé)
        'ca_encaisse': ca_encaisse,
        'ca_encaisse_var': ca_encaisse_var,
        'ca_en_attente_total': ca_en_attente_total,
        'ca_retard': ca_retard,
        'ca_non_planifies': ca_non_planifies,
        'ca_previsionnel_30j': ca_previsionnel_30j,
        
        # Compteurs onglets principaux (NOUVEAU)
        'nb_total': nb_total,
        'nb_urgences': nb_urgences,
        'nb_a_faire': nb_a_faire,
        'nb_en_cours': nb_en_cours,
        'nb_a_venir': nb_a_venir,
        'nb_a_encaisser': nb_a_encaisser,
        'nb_archivees': nb_archivees,
        
        # Compteurs sous-filtres Urgences
        'nb_paiements_retard': nb_paiements_retard,
        'nb_devis_expire': nb_devis_expire,
        'nb_aujourdhui': nb_aujourdhui,
        'nb_demain': nb_demain,
        
        # Compteurs sous-filtres À faire
        'nb_a_planifier': nb_a_planifier,
        'nb_devis_brouillon': nb_devis_brouillon,
        'nb_operations_sans_paiement': nb_operations_sans_paiement,
        
        # Compteurs anciens (conservés pour compatibilité)
        'nb_planifie': nb_planifie,
        'nb_a_traiter': nb_a_traiter,
        'nb_realise': nb_realise,
        'nb_paye': nb_paye,
        'nb_devis_genere_non_envoye': nb_devis_genere_non_envoye,
        'nb_devis_en_attente': nb_devis_en_attente,
        'nb_sans_devis': nb_sans_devis,
        
        'nb_devis_total': devis_counters['nb_devis_total'],
        'nb_devis_brouillon': devis_counters['nb_devis_brouillon'],
        'nb_devis_pret': devis_counters['nb_devis_pret'],
        'nb_devis_envoye': devis_counters['nb_devis_envoye'],
        'nb_devis_expire': devis_counters['nb_devis_expire'],
        'nb_devis_accepte': devis_counters['nb_devis_accepte'],
        'nb_devis_refuse': devis_counters['nb_devis_refuse'],
    }
    
    return render(request, 'operations/list.html', context)


# ========================================
# AUTRES VUES (inchangées)
# ========================================
# ... Gardez toutes vos autres vues existantes
# (operation_detail, operation_create, etc.)
@login_required
def operation_detail(request, operation_id):
    """Fiche détaillée d'une opération avec gestion complète"""
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
    # ========================================
        # ACTION : CRÉER UN NOUVEAU DEVIS
        # ========================================
        if action == 'creer_nouveau_devis':
            try:
                # Créer un nouveau devis (version auto-incrémentée)
                nouveau_devis = Devis.objects.create(
                    operation=operation,
                    statut='brouillon',
                    validite_jours=30
                )
                
                # Historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"📄 Nouveau devis créé : {nouveau_devis.numero_devis} (version {nouveau_devis.version})",
                    utilisateur=request.user
                )
                
                messages.success(request, f"✅ Nouveau devis {nouveau_devis.numero_devis} créé ! Vous pouvez maintenant ajouter des lignes.")
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # ========================================
        # ACTION : AJOUTER UNE LIGNE À UN DEVIS
        # ========================================
        elif action == 'add_ligne_devis':
            devis_id = request.POST.get('devis_id')
            description = request.POST.get('description', '').strip()
            quantite_str = request.POST.get('quantite', '1').strip()
            unite = request.POST.get('unite', 'forfait')
            prix_unitaire_str = request.POST.get('prix_unitaire_ht', '').strip()
            taux_tva_str = request.POST.get('taux_tva', '10').strip()
            
            if devis_id and description and prix_unitaire_str:
                try:
                    devis = Devis.objects.get(id=devis_id, operation=operation)
                    
                    # Vérifier que le devis n'est pas verrouillé
                    if devis.est_verrouille:
                        messages.error(request, "❌ Ce devis est verrouillé, impossible d'ajouter des lignes.")
                        return redirect('operation_detail', operation_id=operation.id)
                    
                    quantite = Decimal(quantite_str)
                    prix_unitaire_ht = Decimal(prix_unitaire_str)
                    taux_tva = Decimal(taux_tva_str)
                    
                    # Dernier ordre
                    dernier_ordre = devis.lignes.aggregate(
                        max_ordre=Max('ordre')
                    )['max_ordre'] or 0
                    
                    # Créer la ligne
                    ligne = LigneDevis.objects.create(
                        devis=devis,
                        description=description,
                        quantite=quantite,
                        unite=unite,
                        prix_unitaire_ht=prix_unitaire_ht,
                        taux_tva=taux_tva,
                        ordre=dernier_ordre + 1
                    )
                    
                    # Historique
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"➕ Ligne ajoutée au devis {devis.numero_devis} : {description} - {ligne.montant}€ HT",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, f"✅ Ligne ajoutée au devis {devis.numero_devis}")
                    
                except Devis.DoesNotExist:
                    messages.error(request, "❌ Devis introuvable")
                except ValueError as e:
                    messages.error(request, f"❌ Données invalides : {str(e)}")
            else:
                messages.error(request, "❌ Tous les champs sont obligatoires")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # ========================================
        # ACTION : SUPPRIMER UNE LIGNE DE DEVIS
        # ========================================
        elif action == 'delete_ligne_devis':
            ligne_id = request.POST.get('ligne_id')
            
            try:
                ligne = LigneDevis.objects.get(id=ligne_id, devis__operation=operation)
                devis = ligne.devis
                
                # Vérifier que le devis n'est pas verrouillé
                if devis.est_verrouille:
                    messages.error(request, "❌ Ce devis est verrouillé, impossible de supprimer des lignes.")
                    return redirect('operation_detail', operation_id=operation.id)
                
                description = ligne.description
                ligne.delete()
                
                # Historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"🗑️ Ligne supprimée du devis {devis.numero_devis} : {description}",
                    utilisateur=request.user
                )
                
                messages.success(request, "✅ Ligne supprimée")
                
            except LigneDevis.DoesNotExist:
                messages.error(request, "❌ Ligne introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
    
        #notes et validité
        elif action == 'update_notes_validite_devis':
            devis_id = request.POST.get('devis_id')
            notes = request.POST.get('notes', '').strip()
            validite_jours_str = request.POST.get('validite_jours', '30')
            
            try:
                devis = Devis.objects.get(id=devis_id, operation=operation)
                
                # Vérifier que le devis est en brouillon
                if devis.statut != 'brouillon':
                    messages.error(request, "❌ Impossible de modifier un devis déjà généré.")
                    return redirect('operation_detail', operation_id=operation.id)
                
                devis.notes = notes
                devis.validite_jours = int(validite_jours_str)
                devis.save()
                
                messages.success(request, "✅ Notes et validité enregistrées")
                
            except Devis.DoesNotExist:
                messages.error(request, "❌ Devis introuvable")
            except ValueError:
                messages.error(request, "❌ Validité invalide")
            
            return redirect('operation_detail', operation_id=operation.id)
                
        # ════════════════════════════════════════════════════════════
        # ACTION : Générer PDF / Marquer comme prêt
        # ════════════════════════════════════════════════════════════
        elif action == 'generer_pdf_devis':
            devis_id = request.POST.get('devis_id')
            
            try:
                devis = Devis.objects.get(id=devis_id, operation=operation)
                
                # ✅ 1. Vérifier s'il y a une ligne en cours de saisie à ajouter
                ligne_description = request.POST.get('ligne_description', '').strip()
                ligne_prix_ht = request.POST.get('ligne_prix_ht', '').strip()
                
                if ligne_description and ligne_prix_ht:
                    # Il y a une ligne à ajouter avant de générer
                    try:
                        ligne_quantite = Decimal(request.POST.get('ligne_quantite', '1'))
                        ligne_unite = request.POST.get('ligne_unite', 'forfait')
                        ligne_prix_unitaire_ht = Decimal(ligne_prix_ht)
                        ligne_tva = Decimal(request.POST.get('ligne_tva', '10'))
                        
                        # Dernier ordre
                        dernier_ordre = devis.lignes.aggregate(max_ordre=Max('ordre'))['max_ordre'] or 0
                        
                        # Créer la ligne
                        LigneDevis.objects.create(
                            devis=devis,
                            description=ligne_description,
                            quantite=ligne_quantite,
                            unite=ligne_unite,
                            prix_unitaire_ht=ligne_prix_unitaire_ht,
                            taux_tva=ligne_tva,
                            ordre=dernier_ordre + 1
                        )
                        
                        print(f"✅ Ligne ajoutée automatiquement : {ligne_description}")
                        
                    except (ValueError, TypeError) as e:
                        messages.error(request, f"❌ Erreur dans les données de la ligne : {str(e)}")
                        return redirect('operation_detail', operation_id=operation.id)
                
                # ✅ 2. Vérifier qu'il y a au moins une ligne (maintenant ou avant)
                if not devis.lignes.exists():
                    messages.error(request, "❌ Le devis doit contenir au moins une ligne.")
                    return redirect('operation_detail', operation_id=operation.id)
                
                # ✅ 3. Enregistrer notes et validité
                notes = request.POST.get('notes', '').strip()
                validite_jours_str = request.POST.get('validite_jours', '30')
                
                if notes:
                    devis.notes = notes
                
                try:
                    devis.validite_jours = int(validite_jours_str)
                except ValueError:
                    pass
                
                # ✅ 4. Passer au statut "prêt"
                devis.statut = 'pret'
                devis.save()
                
                messages.success(request, f"✅ Devis {devis.numero_devis} prêt à envoyer !")
                
            except Devis.DoesNotExist:
                messages.error(request, "❌ Devis introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # ========================================
        # ACTION : ENREGISTRER DATE D'ENVOI
        # ========================================
        elif action == 'enregistrer_date_envoi_devis':
            devis_id = request.POST.get('devis_id')
            date_envoi_str = request.POST.get('date_envoi', '')
            
            try:
                devis = Devis.objects.get(id=devis_id, operation=operation)
                
                if date_envoi_str:
                    devis.date_envoi = datetime.strptime(date_envoi_str, '%Y-%m-%d').date()
                    # ✅ CHANGEMENT : Passer en statut "envoyé" maintenant
                    devis.statut = 'envoye'
                    devis.save()
                    
                    # Historique
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"📅 Date d'envoi enregistrée pour {devis.numero_devis} : {devis.date_envoi.strftime('%d/%m/%Y')} - Statut : Envoyé",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, f"✅ Date d'envoi enregistrée : {devis.date_envoi.strftime('%d/%m/%Y')} - Devis marqué comme envoyé")
                else:
                    messages.error(request, "⚠️ Veuillez renseigner une date")
                
            except Devis.DoesNotExist:
                messages.error(request, "❌ Devis introuvable")
            except ValueError:
                messages.error(request, "❌ Format de date invalide")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # ========================================
        # ACTION : ACCEPTER UN DEVIS
        # ========================================
        elif action == 'accepter_devis':
            devis_id = request.POST.get('devis_id')
            
            try:
                devis = Devis.objects.get(id=devis_id, operation=operation)
                
                # Date de réponse = aujourd'hui
                devis.date_reponse = timezone.now().date()
                devis.statut = 'accepte'
                devis.save()
                
                # Changer le statut de l'opération si besoin
                if operation.statut == 'en_attente_devis':
                    # ✅ Vérifier si un passage est déjà planifié
                    passage_planifie = operation.passages.filter(
                        date_prevue__isnull=False,
                        realise=False
                    ).exists()
                    
                    if passage_planifie:
                        # Si déjà planifié, passer en statut "planifie"
                        operation.statut = 'planifie'
                    else:
                        # Sinon, à planifier
                        operation.statut = 'a_planifier'
                    
                    operation.save()
                
                # Calculer délai de réponse
                if devis.date_envoi and devis.date_reponse:
                    delai = (devis.date_reponse - devis.date_envoi).days
                    delai_texte = f" - Délai : {delai} jour{'s' if delai > 1 else ''}"
                else:
                    delai_texte = ""
                
                # Historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"✅ Devis {devis.numero_devis} accepté par le client{delai_texte} - Montant : {devis.total_ttc}€ TTC",
                    utilisateur=request.user
                )
                
                messages.success(request, f"✅ Devis {devis.numero_devis} accepté le {devis.date_reponse.strftime('%d/%m/%Y')} !")
                
            except Devis.DoesNotExist:
                messages.error(request, "❌ Devis introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # ========================================
        # ACTION : REFUSER UN DEVIS
        # ========================================
        elif action == 'refuser_devis':
            devis_id = request.POST.get('devis_id')
            
            try:
                devis = Devis.objects.get(id=devis_id, operation=operation)
                
                # Date de réponse = aujourd'hui
                devis.date_reponse = timezone.now().date()
                devis.statut = 'refuse'
                devis.save()
                
                # Historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"❌ Devis {devis.numero_devis} refusé par le client - Montant : {devis.total_ttc}€ TTC",
                    utilisateur=request.user
                )
                
                messages.warning(request, f"❌ Devis {devis.numero_devis} marqué comme refusé.")
                
            except Devis.DoesNotExist:
                messages.error(request, "❌ Devis introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # ========================================
        # ACTION : SUPPRIMER UN DEVIS (brouillon uniquement)
        # ========================================
        elif action == 'supprimer_devis':
            devis_id = request.POST.get('devis_id')
            
            try:
                devis = Devis.objects.get(id=devis_id, operation=operation)
                
                # Vérifier que c'est un brouillon
                if not devis.peut_etre_supprime:
                    messages.error(request, "❌ Seuls les devis en brouillon peuvent être supprimés.")
                    return redirect('operation_detail', operation_id=operation.id)
                
                numero = devis.numero_devis
                devis.delete()
                
                # Historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"🗑️ Devis {numero} supprimé (brouillon)",
                    utilisateur=request.user
                )
                
                messages.success(request, f"✅ Devis {numero} supprimé")
                
            except Devis.DoesNotExist:
                messages.error(request, "❌ Devis introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
            # ========================================
            # FIN NOUVELLES ACTIONS DEVIS
            # ========================================
        
        # GESTION DES ÉCHÉANCES
        elif action == 'add_echeance':
            numero = request.POST.get('numero', '')
            montant_str = request.POST.get('montant', '')
            date_echeance_str = request.POST.get('date_echeance', '')

            if montant_str and date_echeance_str:
                try:


                    
                    montant = Decimal(montant_str)  # ✅ CORRECTION
                    date_echeance = datetime.fromisoformat(date_echeance_str).date()
                    
                    # Auto-générer le numéro
                    dernier_numero = operation.echeances.aggregate(
                        max_numero=Max('numero')
                    )['max_numero'] or 0
                    
                    dernier_ordre = operation.echeances.aggregate(
                        max_ordre=Max('ordre')
                    )['max_ordre'] or 0
                    
                    Echeance.objects.create(
                        operation=operation,
                        numero=dernier_numero + 1,  # ← Auto-incrémenté
                        montant=montant,
                        date_echeance=date_echeance,
                        ordre=dernier_ordre + 1
                    )

                    # ✅ AJOUTEZ CES LIGNES : Enregistrer automatiquement le mode échelonné
                    if not operation.mode_paiement:
                        operation.mode_paiement = 'echelonne'
                        operation.save()
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"Échéance ajoutée : {montant}€ pour le {date_echeance}",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, "Échéance ajoutée")
                except (ValueError, TypeError):
                    messages.error(request, "Données invalides")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        elif action == 'delete_echeance':
            echeance_id = request.POST.get('echeance_id')
            try:
                echeance = Echeance.objects.get(id=echeance_id, operation=operation)
                echeance.delete()
                messages.success(request, "Échéance supprimée")
            except Echeance.DoesNotExist:
                messages.error(request, "Échéance introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        elif action == 'marquer_paye_echeance':
            echeance_id = request.POST.get('echeance_id')
            try:
                echeance = Echeance.objects.get(id=echeance_id, operation=operation)
                echeance.paye = True
                echeance.save()
                
                # Vérifier si toutes les échéances sont payées
                toutes_payees = not operation.echeances.filter(paye=False).exists()
                
                if toutes_payees:
                    operation.statut = 'paye'
                    operation.save()
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"Échéance {echeance.numero} marquée comme payée - Toutes les échéances sont payées",
                        utilisateur=request.user
                    )
                    messages.success(request, "Échéance marquée comme payée. Toutes les échéances sont réglées !")
                else:
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"Échéance {echeance.numero} marquée comme payée",
                        utilisateur=request.user
                    )
                    messages.success(request, "Échéance marquée comme payée")
                    
            except Echeance.DoesNotExist:
                messages.error(request, "Échéance introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        elif action == 'update_mode_paiement':
            mode_paiement = request.POST.get('mode_paiement')
            date_paiement_comptant = request.POST.get('date_paiement_comptant', '')
            
            if mode_paiement in ['comptant', 'echelonne']:
                operation.mode_paiement = mode_paiement
                
                # Si paiement comptant avec date, marquer comme payé
                if mode_paiement == 'comptant' and date_paiement_comptant:
                    
                    try:
                        # Convertir la date en datetime (avec l'heure à minuit)
                        date_obj = datetime.strptime(date_paiement_comptant, '%Y-%m-%d')
                        operation.date_paiement = date_obj  # ← Datetime complet, pas .date()
                        operation.statut = 'paye'
                        print(f"✓ Paiement enregistré: {operation.date_paiement}")
                    except ValueError as e:
                        print(f"✗ Erreur conversion date: {e}")
                        messages.error(request, "Format de date invalide")
                
                operation.save()
                
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"Mode de paiement: {operation.get_mode_paiement_display()}" + 
                        (f" - Payé le {operation.date_paiement.strftime('%d/%m/%Y')}" if operation.statut == 'paye' else ""),
                    utilisateur=request.user
                )
                
                if operation.statut == 'paye':
                    messages.success(request, "✓ Paiement enregistré - Opération marquée comme payée")
                else:
                    messages.success(request, "Mode de paiement mis à jour")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # GESTION DU CHANGEMENT DE STATUT
        elif action == 'change_status':
            nouveau_statut = request.POST.get('statut')
            date_prevue_str = request.POST.get('date_prevue', '')
            date_realisation_str = request.POST.get('date_realisation', '')
            date_paiement_str = request.POST.get('date_paiement', '')
            
            if nouveau_statut in dict(Operation.STATUTS):
                ancien_statut = operation.get_statut_display()
                operation.statut = nouveau_statut
                
                
                
                if nouveau_statut == 'planifie' and date_prevue_str:
                    try:
                        operation.date_prevue = datetime.fromisoformat(date_prevue_str.replace('T', ' '))
                    except ValueError:
                        pass
                elif nouveau_statut == 'realise' and date_realisation_str:
                    try:
                        operation.date_realisation = datetime.fromisoformat(date_realisation_str.replace('T', ' '))
                    except ValueError:
                        pass
                elif nouveau_statut == 'paye':
                    if date_realisation_str:
                        try:
                            operation.date_realisation = datetime.fromisoformat(date_realisation_str.replace('T', ' '))
                        except ValueError:
                            pass
                    if date_paiement_str:
                        try:
                            operation.date_paiement = datetime.fromisoformat(date_paiement_str.replace('T', ' '))
                        except ValueError:
                            pass
                        
                operation.save()
                
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"Statut changé : {ancien_statut} → {operation.get_statut_display()}",
                    utilisateur=request.user
                )
                
                messages.success(request, f"Statut mis à jour : {operation.get_statut_display()}")
                return redirect('operation_detail', operation_id=operation.id)
    # ========================================
        # ACTION : AJOUTER UNE INTERVENTION (pour opérations SANS devis)
        # ========================================
        elif action == 'add_intervention':
            # Vérifier que l'opération est bien SANS devis
            if operation.avec_devis:
                messages.error(request, "❌ Cette opération utilise des devis. Utilisez 'Ajouter une ligne de devis'.")
                return redirect('operation_detail', operation_id=operation.id)
            
            description = request.POST.get('description', '').strip()
            quantite_str = request.POST.get('quantite', '1').strip()
            unite = request.POST.get('unite', 'forfait')
            prix_unitaire_str = request.POST.get('prix_unitaire_ht', '').strip()
            taux_tva_str = request.POST.get('taux_tva', '10').strip()
            
            if description and prix_unitaire_str:
                try:
                    quantite = Decimal(quantite_str)
                    prix_unitaire_ht = Decimal(prix_unitaire_str)
                    taux_tva = Decimal(taux_tva_str)
                    
                    dernier_ordre = operation.interventions.aggregate(
                        max_ordre=Max('ordre')
                    )['max_ordre'] or 0
                    
                    # Le montant sera calculé automatiquement dans save()
                    intervention = Intervention.objects.create(
                        operation=operation,
                        description=description,
                        quantite=quantite,
                        unite=unite,
                        prix_unitaire_ht=prix_unitaire_ht,
                        taux_tva=taux_tva,
                        ordre=dernier_ordre + 1
                    )
                    
                    # Historique avec détails
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"➕ Intervention ajoutée : {description} - {intervention.montant}€ HT + TVA = {intervention.montant_ttc}€ TTC",
                        utilisateur=request.user
                    )
                    
                    messages.success(
                        request, 
                        f"✅ Intervention ajoutée : {intervention.montant}€ HT + TVA = {intervention.montant_ttc}€ TTC"
                    )
                    
                except ValueError as e:
                    messages.error(request, f"❌ Données invalides : {str(e)}")
            else:
                messages.error(request, "❌ Description et prix unitaire HT obligatoires")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # GESTION DES COMMENTAIRES
        elif action == 'update_commentaires':
            commentaires = request.POST.get('commentaires', '').strip()
            
            operation.commentaires = commentaires
            operation.save()
            
            HistoriqueOperation.objects.create(
                operation=operation,
                action="Commentaires mis à jour",
                utilisateur=request.user
            )
            
            messages.success(request, "Commentaires enregistrés avec succès")
            return redirect('operation_detail', operation_id=operation.id)
            
    # ========================================
        # ACTION : SUPPRIMER UNE INTERVENTION (pour opérations SANS devis)
        # ========================================
        elif action == 'delete_intervention':
            # Vérifier que l'opération est bien SANS devis
            if operation.avec_devis:
                messages.error(request, "❌ Cette opération utilise des devis. Utilisez 'Supprimer ligne de devis'.")
                return redirect('operation_detail', operation_id=operation.id)
            
            intervention_id = request.POST.get('intervention_id')
            
            try:
                intervention = Intervention.objects.get(
                    id=intervention_id, 
                    operation=operation
                )
                description = intervention.description
                intervention.delete()
                
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"🗑️ Intervention supprimée : {description}",
                    utilisateur=request.user
                )
                
                messages.success(request, "✅ Intervention supprimée")
                
            except Intervention.DoesNotExist:
                messages.error(request, "❌ Intervention introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # GESTION DE LA PLANIFICATION
        elif action == 'update_planning':
            
            date_prevue_str = request.POST.get('date_prevue', '')
            
            print(f"\n{'='*60}")
            print(f"PLANIFICATION")
            print(f"Date reçue: '{date_prevue_str}'")
            
            if date_prevue_str:
                try:
                    nouvelle_date = datetime.fromisoformat(date_prevue_str.replace('T', ' '))
                    ancienne_date = operation.date_prevue
                    
                    operation.date_prevue = nouvelle_date
                    operation.statut = 'planifie'
                    operation.save()
                    
                    if ancienne_date and ancienne_date != nouvelle_date:
                        # Replanification
                        HistoriqueOperation.objects.create(
                            operation=operation,
                            action=f"📅 Replanifié du {ancienne_date.strftime('%d/%m/%Y à %H:%M')} au {nouvelle_date.strftime('%d/%m/%Y à %H:%M')}",
                            utilisateur=request.user
                        )
                        messages.success(request, f"🔄 Intervention replanifiée au {nouvelle_date.strftime('%d/%m/%Y à %H:%M')}")
                    else:
                        # Première planification
                        HistoriqueOperation.objects.create(
                            operation=operation,
                            action=f"Intervention planifiée le {nouvelle_date.strftime('%d/%m/%Y à %H:%M')}",
                            utilisateur=request.user
                        )
                        messages.success(request, f"✅ Intervention planifiée le {nouvelle_date.strftime('%d/%m/%Y à %H:%M')}")
                        
                except ValueError as e:
                    print(f"❌ ERREUR: {e}")
                    messages.error(request, "Date invalide")
            
            return redirect('operation_detail', operation_id=operation.id) 

        # VALIDATION DE LA RÉALISATION
        elif action == 'valider_realisation':
            
            date_realisation_str = request.POST.get('date_realisation', '')
            
            if date_realisation_str:
                try:
                    date_realisation = datetime.fromisoformat(date_realisation_str.replace('T', ' '))
                    
                    # Validation : pas dans le futur
                    if date_realisation > timezone.now():
                        messages.error(request, "❌ La date de réalisation ne peut pas être dans le futur")
                        return redirect('operation_detail', operation_id=operation.id)
                    
                    operation.date_realisation = date_realisation
                    operation.statut = 'realise'
                    operation.save()
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"✅ Intervention réalisée le {date_realisation.strftime('%d/%m/%Y à %H:%M')}",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, f"✅ Réalisation validée le {date_realisation.strftime('%d/%m/%Y à %H:%M')}")
                except ValueError:
                    messages.error(request, "Date invalide")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        # CORRECTION DES DATES DE RÉALISATION
        elif action == 'corriger_dates_realisation':
           
            date_realisation_str = request.POST.get('date_realisation', '')
            
            if date_realisation_str:
                try:
                    date_realisation = datetime.fromisoformat(date_realisation_str.replace('T', ' '))
                    
                    # Validation : pas dans le futur
                    if date_realisation > timezone.now():
                        messages.error(request, "❌ La date de réalisation ne peut pas être dans le futur")
                        return redirect('operation_detail', operation_id=operation.id)
                    
                    ancienne_date = operation.date_realisation
                    operation.date_realisation = date_realisation
                    operation.save()
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"⚠️ Date de réalisation corrigée : {ancienne_date.strftime('%d/%m/%Y à %H:%M')} → {date_realisation.strftime('%d/%m/%Y à %H:%M')}",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, f"✅ Date de réalisation corrigée")
                except ValueError:
                    messages.error(request, "Date invalide")
            
            return redirect('operation_detail', operation_id=operation.id)

        # ========================================
        # GESTION DES PAIEMENTS (SIMPLIFIÉ)
        # ========================================

        elif action == 'add_paiement':
            montant_str = request.POST.get('montant', '')
            date_paiement_str = request.POST.get('date_paiement', '')
            paye_str = request.POST.get('paye', 'false')
            generer_facture_auto = request.POST.get('generer_facture_auto') == 'true'
            
            if montant_str and date_paiement_str:
                try:
                    montant = Decimal(montant_str)
                    date_paiement = datetime.strptime(date_paiement_str, '%Y-%m-%d').date()
                    paye = (paye_str == 'true')
                    
                    # ✅ VÉRIFICATION : Calculer le total avec ce nouveau paiement
                    total_actuel_tout = operation.echeances.aggregate(
                        total=Sum('montant')
                    )['total'] or 0
                    
                    nouveau_total = total_actuel_tout + montant
                    
                    if nouveau_total > operation.montant_total:
                        depassement = nouveau_total - operation.montant_total
                        messages.error(
                            request, 
                            f"❌ Dépassement de {depassement:.2f}€ ! "
                            f"Total avec ce paiement : {nouveau_total:.2f}€ / Montant opération : {operation.montant_total:.2f}€"
                        )
                        return redirect('operation_detail', operation_id=operation.id)
                    
                    # Auto-générer le numéro
                    dernier_numero = operation.echeances.aggregate(
                        max_numero=Max('numero')
                    )['max_numero'] or 0
                    
                    dernier_ordre = operation.echeances.aggregate(
                        max_ordre=Max('ordre')
                    )['max_ordre'] or 0
                    
                    # Créer l'échéance
                    echeance = Echeance.objects.create(
                        operation=operation,
                        numero=dernier_numero + 1,
                        montant=montant,
                        date_echeance=date_paiement,
                        paye=paye,
                        ordre=dernier_ordre + 1
                    )
                    
                    # Historique
                    statut_txt = "payé" if paye else "prévu"
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"💰 Paiement {statut_txt} : {montant}€ le {date_paiement.strftime('%d/%m/%Y')}",
                        utilisateur=request.user
                    )
                    
                    # ════════════════════════════════════════════════════════════
                    # ✅ NOUVEAU : GÉNÉRATION AUTOMATIQUE DE FACTURE SI PAYÉ
                    # ════════════════════════════════════════════════════════════
                    facture_generee = False
                    
                    if paye and generer_facture_auto:
                        # Générer automatiquement la facture
                        annee_courante = timezone.now().year
                        prefix = f'FACTURE-{annee_courante}-U{request.user.id}-'
                        
                        dernieres_factures = Echeance.objects.filter(
                            operation__user=request.user,
                            facture_generee=True,
                            numero_facture__startswith=prefix
                        ).values_list('numero_facture', flat=True)
                        
                        max_numero_facture = 0
                        for facture in dernieres_factures:
                            match = re.search(r'-(\d+)$', facture)
                            if match:
                                numero = int(match.group(1))
                                if numero > max_numero_facture:
                                    max_numero_facture = numero
                        
                        nouveau_numero_facture = f'{prefix}{max_numero_facture + 1:05d}'
                        
                        # Déterminer le type de facture
                        total_echeances = operation.echeances.count()
                        echeances_payees_count = operation.echeances.filter(paye=True).count()
                        echeances_payees_non_facturees = operation.echeances.filter(
                            paye=True,
                            facture_generee=False
                        ).count()
                        total_planifie = operation.echeances.aggregate(
                            total=Sum('montant')
                        )['total'] or Decimal('0')
                        reste_non_enregistre = operation.montant_total - total_planifie
                        
                        if echeances_payees_count == 1 and total_echeances == 1:
                            facture_type = 'globale'
                        elif echeances_payees_non_facturees == 1 and reste_non_enregistre <= 0:
                            facture_type = 'solde'
                        else:
                            facture_type = 'acompte'
                        
                        # Enregistrer la facture
                        echeance.facture_generee = True
                        echeance.numero_facture = nouveau_numero_facture
                        echeance.facture_date_emission = timezone.now().date()
                        echeance.facture_type = facture_type
                        echeance.save()
                        
                        facture_generee = True
                        
                        type_label = {
                            'globale': 'globale',
                            'acompte': "d'acompte",
                            'solde': 'de solde'
                        }.get(facture_type, '')
                        
                        HistoriqueOperation.objects.create(
                            operation=operation,
                            action=f"📄 Facture {type_label} {nouveau_numero_facture} générée automatiquement",
                            utilisateur=request.user
                        )
                    
                    # ════════════════════════════════════════════════════════════
                    # FIN GÉNÉRATION AUTOMATIQUE
                    # ════════════════════════════════════════════════════════════
                    
                    # Vérifier si tout est payé
                    total_paye = operation.echeances.filter(paye=True).aggregate(
                        total=Sum('montant')
                    )['total'] or 0
                    
                    if total_paye >= operation.montant_total:
                        operation.statut = 'paye'
                        operation.save()
                        
                        if facture_generee:
                            messages.success(
                                request, 
                                f"✅ Paiement de {montant}€ enregistré + Facture {echeance.numero_facture} générée - Opération soldée ! 🎉"
                            )
                        else:
                            messages.success(request, f"✅ Paiement enregistré - Opération soldée ! 🎉")
                    else:
                        if facture_generee:
                            messages.success(
                                request, 
                                f"✅ Paiement de {montant}€ enregistré + Facture {echeance.numero_facture} générée"
                            )
                        else:
                            messages.success(request, f"✅ Paiement de {montant}€ enregistré")
                    
                except (ValueError, TypeError) as e:
                    messages.error(request, f"Données invalides : {str(e)}")
            
            return redirect('operation_detail', operation_id=operation.id)

        # MARQUER UN PAIEMENT COMME PAYÉ
        elif action == 'marquer_paye':
            echeance_id = request.POST.get('echeance_id')
            try:
                echeance = Echeance.objects.get(id=echeance_id, operation=operation)
                echeance.paye = True
                echeance.save()
                
                # ════════════════════════════════════════════════════════════
                # ✅ NOUVEAU : GÉNÉRATION AUTOMATIQUE DE FACTURE
                # ════════════════════════════════════════════════════════════
                if not echeance.facture_generee:
                    annee_courante = timezone.now().year
                    prefix = f'FACTURE-{annee_courante}-U{request.user.id}-'
                    
                    dernieres_factures = Echeance.objects.filter(
                        operation__user=request.user,
                        facture_generee=True,
                        numero_facture__startswith=prefix
                    ).values_list('numero_facture', flat=True)
                    
                    max_numero_facture = 0
                    for facture in dernieres_factures:
                        match = re.search(r'-(\d+)$', facture)
                        if match:
                            numero = int(match.group(1))
                            if numero > max_numero_facture:
                                max_numero_facture = numero
                    
                    nouveau_numero_facture = f'{prefix}{max_numero_facture + 1:05d}'
                    
                    # Déterminer le type de facture
                    total_echeances = operation.echeances.count()
                    echeances_payees_count = operation.echeances.filter(paye=True).count()
                    echeances_payees_non_facturees = operation.echeances.filter(
                        paye=True,
                        facture_generee=False
                    ).count()
                    total_planifie = operation.echeances.aggregate(
                        total=Sum('montant')
                    )['total'] or Decimal('0')
                    reste_non_enregistre = operation.montant_total - total_planifie
                    
                    if echeances_payees_count == 1 and total_echeances == 1:
                        facture_type = 'globale'
                    elif echeances_payees_non_facturees == 1 and reste_non_enregistre <= 0:
                        facture_type = 'solde'
                    else:
                        facture_type = 'acompte'
                    
                    echeance.facture_generee = True
                    echeance.numero_facture = nouveau_numero_facture
                    echeance.facture_date_emission = timezone.now().date()
                    echeance.facture_type = facture_type
                    echeance.save()
                    
                    type_label = {
                        'globale': 'globale',
                        'acompte': "d'acompte",
                        'solde': 'de solde'
                    }.get(facture_type, '')
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"📄 Facture {type_label} {nouveau_numero_facture} générée automatiquement",
                        utilisateur=request.user
                    )
                # ════════════════════════════════════════════════════════════
                
                # Vérifier si tout est payé
                total_paye = operation.echeances.filter(paye=True).aggregate(
                    total=Sum('montant')
                )['total'] or 0
                
                if total_paye >= operation.montant_total:
                    operation.statut = 'paye'
                    operation.save()
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"✅ Paiement de {echeance.montant}€ confirmé + Facture {echeance.numero_facture} - Opération soldée ! 🎉",
                        utilisateur=request.user
                    )
                    messages.success(
                        request, 
                        f"🎉 Paiement confirmé + Facture {echeance.numero_facture} générée - Opération soldée !"
                    )
                else:
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"✅ Paiement de {echeance.montant}€ confirmé + Facture {echeance.numero_facture}",
                        utilisateur=request.user
                    )
                    messages.success(
                        request, 
                        f"✅ Paiement de {echeance.montant}€ confirmé + Facture {echeance.numero_facture} générée"
                    )
                    
            except Echeance.DoesNotExist:
                messages.error(request, "Paiement introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)

        # SUPPRIMER UN PAIEMENT
        elif action == 'delete_paiement':
            echeance_id = request.POST.get('echeance_id')
            try:
                echeance = Echeance.objects.get(id=echeance_id, operation=operation)
                montant = echeance.montant
                echeance.delete()
                
                # Si c'était payé, re-vérifier le statut
                if operation.statut == 'paye':
                    total_paye = operation.echeances.filter(paye=True).aggregate(
                        total=Sum('montant')
                    )['total'] or 0
                    
                    if total_paye < operation.montant_total:
                        operation.statut = 'realise'
                        operation.save()
                
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"🗑️ Paiement de {montant}€ supprimé",
                    utilisateur=request.user
                )
                
                messages.success(request, "Paiement supprimé")
            except Echeance.DoesNotExist:
                messages.error(request, "Paiement introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
        elif action == 'update_commentaires_dashboard':
            commentaires = request.POST.get('commentaires', '').strip()
            
            operation.commentaires = commentaires
            operation.save()
            
            HistoriqueOperation.objects.create(
                operation=operation,
                action="Commentaires mis à jour depuis dashboard",
                utilisateur=request.user
            )
            
            messages.success(request, "✅ Commentaire enregistré")
            return redirect('operation_detail', operation_id=operation.id)
        
        elif action == 'generer_facture_echeance':
            echeance_id = request.POST.get('echeance_id')
            
            try:
                echeance = Echeance.objects.get(id=echeance_id, operation=operation)
                
                if not echeance.paye:
                    messages.error(request, "❌ Le paiement doit être marqué comme payé avant de générer la facture")
                    return redirect('operation_detail', operation_id=operation.id)
                
                if echeance.facture_generee:
                    messages.warning(request, f"⚠️ Facture déjà générée : {echeance.numero_facture}")
                    return redirect('operation_detail', operation_id=operation.id)
                
                # ✅ GÉNÉRATION DU NUMÉRO DE FACTURE
                annee_courante = timezone.now().year
                prefix = f'FACTURE-{annee_courante}-U{request.user.id}-'
                
                dernieres_factures = Echeance.objects.filter(
                    operation__user=request.user,
                    facture_generee=True,
                    numero_facture__startswith=prefix
                ).values_list('numero_facture', flat=True)
                
                max_numero = 0
                for facture in dernieres_factures:
                    match = re.search(r'-(\d+)$', facture)
                    if match:
                        numero = int(match.group(1))
                        if numero > max_numero:
                            max_numero = numero
                
                nouveau_numero = max_numero + 1
                nouveau_numero_facture = f'{prefix}{nouveau_numero:05d}'
                
                # ═══════════════════════════════════════════════════════════
                # ✅ LOGIQUE AMÉLIORÉE V2 : DÉTERMINER LE TYPE DE FACTURE
                # ═══════════════════════════════════════════════════════════

                # 1️⃣ Compter les échéances
                total_echeances = operation.echeances.count()
                echeances_payees_count = operation.echeances.filter(paye=True).count()

                # 2️⃣ Compter combien de paiements PAYÉS n'ont PAS encore de facture
                echeances_payees_non_facturees = operation.echeances.filter(
                    paye=True,
                    facture_generee=False
                ).count()

                # 3️⃣ Calculer le montant total des échéances (payées + prévues)
                total_planifie = operation.echeances.aggregate(
                    total=Sum('montant')
                )['total'] or Decimal('0')

                # 4️⃣ Vérifier s'il reste des paiements NON ENREGISTRÉS
                reste_non_enregistre = operation.montant_total - total_planifie

                # 5️⃣ LOGIQUE DE DÉTERMINATION DU TYPE
                if echeances_payees_count == 1 and total_echeances == 1:
                    # ✅ CAS 1 : Un seul paiement unique
                    facture_type = 'globale'

                elif echeances_payees_non_facturees == 1 and reste_non_enregistre <= 0:
                    # ✅ CAS 2 : C'est le DERNIER paiement à facturer
                    # ET il n'y a plus rien à enregistrer
                    facture_type = 'solde'

                else:
                    # ✅ CAS 3 : Paiement intermédiaire
                    facture_type = 'acompte'
                
                # ═══════════════════════════════════════════════════════════
                # FIN LOGIQUE AMÉLIORÉE
                # ═══════════════════════════════════════════════════════════
                
                # ✅ ENREGISTRER LA FACTURE
                echeance.facture_generee = True
                echeance.numero_facture = nouveau_numero_facture
                echeance.facture_date_emission = timezone.now().date()
                echeance.facture_type = facture_type
                echeance.save()
                
                # Historique avec détails du type
                type_label = {
                    'globale': 'globale',
                    'acompte': "d'acompte",
                    'solde': 'de solde'
                }.get(facture_type, '')
                
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"📄 Facture {type_label} {nouveau_numero_facture} générée - Montant : {echeance.montant}€",
                    utilisateur=request.user
                )
                
                messages.success(request, f"✅ Facture {type_label} {nouveau_numero_facture} générée avec succès !")
                
            except Echeance.DoesNotExist:
                messages.error(request, "❌ Paiement introuvable")
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
            
            return redirect('operation_detail', operation_id=operation.id)
                
            
    # ========================================
    # GET - Récupérer les données
    # ========================================

    # NOUVEAU : Récupérer tous les devis de l'opération (du plus ancien au plus récent)
    devis_list = operation.devis_set.all().order_by('version')

    # Pour chaque devis, enrichir avec ses lignes
    for devis in devis_list:
        devis.lignes_list = devis.lignes.all().order_by('ordre')
        

    # Interventions (pour opérations SANS devis uniquement)
    interventions = operation.interventions.all().order_by('ordre')

    # Échéances (inchangé)
    echeances = operation.echeances.all().order_by('ordre')
    historique = operation.historique.all().order_by('-date')[:10]

    # Calculs financiers (inchangé)
    total_echeances_payees = echeances.filter(paye=True).aggregate(
        total=Sum('montant')
    )['total'] or 0

    total_echeances_prevus = echeances.filter(paye=False).aggregate(
        total=Sum('montant')
    )['total'] or 0

    total_echeances_tout = echeances.aggregate(
        total=Sum('montant')
    )['total'] or 0

    reste_a_payer = operation.montant_total - total_echeances_payees
    reste_a_enregistrer = operation.montant_total - total_echeances_tout
    reste_a_enregistrer_abs = abs(reste_a_enregistrer)

    if reste_a_enregistrer > 0:
        max_paiement = reste_a_enregistrer
    else:
        max_paiement = operation.montant_total

    # Préparer les données pour JavaScript (MODIFIÉ pour devis)
    lignes_json = json.dumps([])  # Vide car maintenant dans les devis
    echeances_json = json.dumps([
        {
            'id': int(e.id),
            'numero': e.numero,
            'montant': float(e.montant),
            'date_echeance': e.date_echeance.isoformat() if e.date_echeance else ''
        } for e in echeances
    ])
    
    # ✅ Compter les passages non réalisés (pour la confirmation JS)
    passages_non_realises = operation.passages.filter(realise=False).count()
    
    context = {
        'operation': operation,
        
        # ✅ NOUVEAU : Liste des devis
        'devis_list': devis_list,
        'nombre_devis': len(devis_list),
        
        # Interventions (pour sans devis)
        'interventions': interventions,
        
        # Échéances (inchangé)
        'echeances': echeances,
        'total_echeances': total_echeances_payees,
        'total_echeances_prevus': total_echeances_prevus,
        'total_echeances_tout': total_echeances_tout,
        'reste_a_payer': reste_a_payer,
        'reste_a_enregistrer': reste_a_enregistrer,
        'reste_a_enregistrer_abs': reste_a_enregistrer_abs,
        'max_paiement': max_paiement,
        'historique': historique,
        'statuts_choices': Operation.STATUTS,
        'montant_total': operation.montant_total,
        'lignes_json': lignes_json,
        'echeances_json': echeances_json,
        'now': timezone.now(),
        
        'passages_non_realises': passages_non_realises,  # ✅ AJOUTER
    }

    return render(request, 'operations/detail.html', context)

@login_required
def ajax_add_ligne_devis(request, operation_id):
    """Vue AJAX pour ajouter une ligne de devis sans recharger"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
    
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Requête non AJAX'}, status=400)
    
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    devis_id = request.POST.get('devis_id')
    description = request.POST.get('description', '').strip()
    quantite_str = request.POST.get('quantite', '1').strip()
    unite = request.POST.get('unite', 'forfait')
    prix_unitaire_str = request.POST.get('prix_unitaire_ht', '').strip()
    taux_tva_str = request.POST.get('taux_tva', '10').strip()
    
    if not (devis_id and description and prix_unitaire_str):
        return JsonResponse({'success': False, 'error': 'Champs obligatoires manquants'}, status=400)
    
    try:
        devis = Devis.objects.get(id=devis_id, operation=operation)
        
        if devis.est_verrouille:
            return JsonResponse({'success': False, 'error': 'Devis verrouillé'}, status=403)
        
        quantite = Decimal(quantite_str)
        prix_unitaire_ht = Decimal(prix_unitaire_str)
        taux_tva = Decimal(taux_tva_str)
        
        dernier_ordre = devis.lignes.aggregate(max_ordre=Max('ordre'))['max_ordre'] or 0
        
        ligne = LigneDevis.objects.create(
            devis=devis,
            description=description,
            quantite=quantite,
            unite=unite,
            prix_unitaire_ht=prix_unitaire_ht,
            taux_tva=taux_tva,
            ordre=dernier_ordre + 1
        )
        
        HistoriqueOperation.objects.create(
            operation=operation,
            action=f"➕ Ligne ajoutée au devis {devis.numero_devis} : {description}",
            utilisateur=request.user
        )
        
        devis.refresh_from_db()
        
        return JsonResponse({
            'success': True,
            'ligne': {
                'id': ligne.id,
                'description': ligne.description,
                'quantite': float(ligne.quantite),
                'unite': ligne.unite,
                'unite_display': ligne.get_unite_display(),
                'prix_unitaire_ht': float(ligne.prix_unitaire_ht),
                'taux_tva': float(ligne.taux_tva),
                'montant': float(ligne.montant)
            },
            'totaux': {
                'sous_total_ht': float(devis.sous_total_ht),
                'total_tva': float(devis.total_tva),
                'total_ttc': float(devis.total_ttc)
            }
        })
        
    except Devis.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Devis introuvable'}, status=404)
    except ValueError as e:
        return JsonResponse({'success': False, 'error': f'Données invalides: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def ajax_delete_ligne_devis(request, operation_id):
    """Vue AJAX pour supprimer une ligne de devis"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
    
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Requête non AJAX'}, status=400)
    
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    ligne_id = request.POST.get('ligne_id')
    
    try:
        ligne = LigneDevis.objects.get(id=ligne_id, devis__operation=operation)
        devis = ligne.devis
        
        if devis.est_verrouille:
            return JsonResponse({'success': False, 'error': 'Devis verrouillé'}, status=403)
        
        description = ligne.description
        ligne.delete()
        
        HistoriqueOperation.objects.create(
            operation=operation,
            action=f"🗑️ Ligne supprimée : {description}",
            utilisateur=request.user
        )
        
        devis.refresh_from_db()
        
        return JsonResponse({
            'success': True,
            'totaux': {
                'sous_total_ht': float(devis.sous_total_ht),
                'total_tva': float(devis.total_tva),
                'total_ttc': float(devis.total_ttc)
            }
        })
        
    except LigneDevis.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ligne introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def operation_delete(request, operation_id):
    """Suppression d'une opération avec ses données liées"""
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    if request.method == 'POST':
        force_delete = request.POST.get('force_delete') == 'true'
        id_operation = operation.id_operation
        type_prestation = operation.type_prestation
        client_nom = f"{operation.client.nom} {operation.client.prenom}"
        
        if force_delete:
            # Supprimer les données liées
            operation.interventions.all().delete()
            operation.historique.all().delete()
            operation.echeances.all().delete()
            
            # Supprimer l'opération
            operation.delete()
            
            messages.success(request, f"Opération {id_operation} ({type_prestation}) supprimée avec succès.")
            return redirect('operations')
        else:
            messages.error(request, "Confirmation requise pour la suppression")
            return redirect('operation_detail', operation_id=operation.id)
    
    # GET : rediriger vers la fiche opération
    return redirect('operation_detail', operation_id=operation.id)

@login_required
def operation_duplicate(request, operation_id):
    """Dupliquer une opération"""
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    # Créer la nouvelle opération
    nouvelle_operation = Operation.objects.create(
        user=request.user,
        client=operation.client,
        type_prestation=f"Copie - {operation.type_prestation}",
        adresse_intervention=operation.adresse_intervention,
        statut='en_attente_devis'
    )
    
    # Copier les interventions
    for intervention in operation.interventions.all():
        Intervention.objects.create(
            operation=nouvelle_operation,
            description=intervention.description,
            montant=intervention.montant,
            ordre=intervention.ordre
        )
    
    # Historique
    HistoriqueOperation.objects.create(
        operation=nouvelle_operation,
        action=f"Opération créée par duplication de {operation.id_operation}",
        utilisateur=request.user
    )
    
    messages.success(request, f"Opération dupliquée : {nouvelle_operation.id_operation}")
    return redirect('operation_detail', operation_id=nouvelle_operation.id)

@login_required
def clients_list(request):
    """Page de gestion des clients avec recherche et opérations"""
    try:
        # Récupérer tous les clients de l'utilisateur avec prefetch des opérations
        clients = Client.objects.filter(user=request.user).prefetch_related('operations')
        
        # Recherche
        recherche = request.GET.get('recherche', '')
        
        if recherche:
            clients = clients.filter(
                Q(nom__icontains=recherche) |
                Q(prenom__icontains=recherche) |
                Q(email__icontains=recherche) |
                Q(telephone__icontains=recherche) |
                Q(ville__icontains=recherche) |
                Q(adresse__icontains=recherche)
            )
        
        # Tri par nom par défaut
        clients = clients.order_by('nom', 'prenom')
        
        # Enrichir les clients avec les données d'opérations
        clients_enrichis = []
        for client in clients:
            operations = client.operations.all().order_by('-date_creation')
            
            # Dernière opération
            derniere_operation = operations.first() if operations.exists() else None
            
            # Prochaine opération (statut planifié + date future)
            from django.utils import timezone
            prochaines_operations = Operation.objects.filter(
                user=request.user,
                date_prevue__isnull=False,
                date_prevue__gte=timezone.now()  # ← Seulement les futures
            ).exclude(statut__in=['paye', 'annule']).select_related('client').order_by('date_prevue')[:5]
            
            client.derniere_op = derniere_operation
            client.prochaine_op = None
            clients_enrichis.append(client)
        
        # Statistiques
        total_clients = len(clients_enrichis)
        
        context = {
            'clients': clients_enrichis,
            'total_clients': total_clients,
            'recherche': recherche,
        }
        
        return render(request, 'clients/list.html', context)
        
    except Exception as e:
        return HttpResponse(f"Erreur clients: {str(e)}")

@login_required
def client_detail(request, client_id):
    """Fiche détaillée d'un client avec historique des opérations"""
    try:
        client = get_object_or_404(Client, id=client_id, user=request.user)
        
        # Changement de statut d'une opération depuis la fiche client
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'change_operation_status':
                operation_id = request.POST.get('operation_id')
                nouveau_statut = request.POST.get('statut')
                
                try:
                    operation = Operation.objects.get(
                        id=operation_id, 
                        client=client, 
                        user=request.user
                    )
                    
                    if nouveau_statut in dict(Operation.STATUTS):
                        ancien_statut = operation.get_statut_display()
                        operation.statut = nouveau_statut
                        operation.save()
                        
                        # Ajouter à l'historique
                        HistoriqueOperation.objects.create(
                            operation=operation,
                            action=f"Statut changé depuis fiche client : {ancien_statut} → {operation.get_statut_display()}",
                            utilisateur=request.user
                        )
                        
                        messages.success(request, f"Statut de l'opération {operation.id_operation} mis à jour")
                    
                except Operation.DoesNotExist:
                    messages.error(request, "Opération introuvable")
                
                return redirect('client_detail', client_id=client.id)
        
        # Récupérer toutes les opérations du client
        operations = client.operations.all().order_by('-date_creation')
        
        # Statistiques du client
        nb_operations = operations.count()
        ca_total = sum(op.montant_total for op in operations if op.statut == 'paye')
        
        context = {
            'client': client,
            'operations': operations,
            'nb_operations': nb_operations,
            'ca_total': ca_total,
            'statuts_choices': Operation.STATUTS,
        }
        
        return render(request, 'clients/detail.html', context)
        
    except Exception as e:
        return HttpResponse(f"Erreur client detail: {str(e)}")

@login_required
def operation_create(request):
    """Formulaire de création d'une nouvelle opération (Parcours A ou B)"""
    
    if request.method == 'POST':
        print("\n" + "="*80)
        print("DÉBUT CRÉATION OPÉRATION")
        print("="*80)
        print(f"User: {request.user.username} (ID: {request.user.id})")
        print(f"\nDonnées POST reçues:")
        for key, value in request.POST.items():
            if key != 'csrfmiddlewaretoken':
                print(f"  {key}: '{value}'")
        
        try:
            # ========================================
            # ÉTAPE 1 : GESTION DU CLIENT
            # ========================================
            client_type = request.POST.get('client_type', 'existant')
            
            print(f"\n{'─'*80}")
            print("ÉTAPE 1: GESTION DU CLIENT")
            print(f"{'─'*80}")
            print(f"Type: {client_type}")
            
            if client_type == 'existant':
                client_id = request.POST.get('client_id')
                if not client_id:
                    messages.error(request, "⚠️ Veuillez sélectionner un client")
                    return redirect('operation_create')
                
                client = get_object_or_404(Client, id=client_id, user=request.user)
                print(f"✓ Client existant: {client.nom} {client.prenom} (ID: {client.id})")
                
            else:  # Nouveau client
                nom = request.POST.get('nouveau_client_nom', '').strip()
                prenom = request.POST.get('nouveau_client_prenom', '').strip()
                telephone = request.POST.get('nouveau_client_telephone', '').strip()
                email = request.POST.get('nouveau_client_email', '').strip()
                adresse = request.POST.get('nouveau_client_adresse', '').strip()
                ville = request.POST.get('nouveau_client_ville', '').strip()
                
                print(f"Création nouveau client:")
                print(f"  Nom: '{nom}'")
                print(f"  Prénom: '{prenom}'")
                print(f"  Téléphone: '{telephone}'")
                
                if not (nom and prenom and telephone):
                    print("✗ ERREUR: Champs obligatoires manquants")
                    messages.error(request, "⚠️ Nom, prénom et téléphone sont obligatoires pour un nouveau client")
                    clients = Client.objects.filter(user=request.user).order_by('nom', 'prenom')
                    return render(request, 'operations/create.html', {'clients': clients})
                
                client = Client.objects.create(
                    user=request.user,
                    nom=nom,
                    prenom=prenom,
                    email=email,
                    telephone=telephone,
                    adresse=adresse,
                    ville=ville
                )
                print(f"✓ Nouveau client créé: {client.nom} {client.prenom} (ID: {client.id})")
            
            # ========================================
            # ÉTAPE 2 : INFORMATIONS OPÉRATION
            # ========================================
            type_prestation = request.POST.get('type_prestation', '').strip()
            adresse_intervention = request.POST.get('adresse_intervention', '').strip()
            commentaires = request.POST.get('commentaires', '').strip()
            
            print(f"\n{'─'*80}")
            print("ÉTAPE 2: INFORMATIONS OPÉRATION")
            print(f"{'─'*80}")
            print(f"Type prestation: '{type_prestation}'")
            print(f"Adresse intervention: '{adresse_intervention}'")
            print(f"Commentaires: '{commentaires}'")
            
            if not type_prestation:
                print("✗ ERREUR: Type de prestation manquant")
                messages.error(request, "⚠️ Le type de prestation est obligatoire")
                clients = Client.objects.filter(user=request.user).order_by('nom', 'prenom')
                return render(request, 'operations/create.html', {'clients': clients})
            
            # Adresse par défaut = adresse client
            adresse_finale = adresse_intervention or f"{client.adresse}, {client.ville}"
            print(f"Adresse finale: '{adresse_finale}'")
            
            # ========================================
            # ÉTAPE 3 : TYPE D'OPÉRATION (DEVIS OU DIRECTE)
            # ========================================
            operation_type = request.POST.get('operation_type', 'devis')
            
            print(f"\n{'─'*80}")
            print("ÉTAPE 3: TYPE D'OPÉRATION")
            print(f"{'─'*80}")
            print(f"Type: {operation_type}")
            
            # ========================================
            # PARCOURS A : AVEC DEVIS
            # ========================================
            if operation_type == 'devis':
                print(f"\n{'─'*80}")
                print("PARCOURS A : CRÉATION AVEC DEVIS")
                print(f"{'─'*80}")
                
                # Créer l'opération
                operation = Operation.objects.create(
                    user=request.user,
                    client=client,
                    type_prestation=type_prestation,
                    adresse_intervention=adresse_finale,
                    commentaires=commentaires,
                    avec_devis=True,
                    statut='en_attente_devis'
                )
                
                print(f"✓ Opération créée (AVEC DEVIS)")
                print(f"  ID: {operation.id}")
                print(f"  Code: {operation.id_operation}")
                print(f"  avec_devis: True")
                print(f"  statut: en_attente_devis")
                
                # ✅ NOUVEAU : Créer automatiquement le premier devis (version 1)
                try:
                    premier_devis = Devis.objects.create(
                        operation=operation,
                        statut='brouillon',
                        validite_jours=30
                    )
                    
                    print(f"✓ Premier devis créé automatiquement")
                    print(f"  Numéro: {premier_devis.numero_devis}")
                    print(f"  Version: {premier_devis.version}")
                    print(f"  Statut: brouillon")
                    
                    # Historique pour l'opération
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action="Opération créée (avec devis)",
                        utilisateur=request.user
                    )
                    
                    # Historique pour le premier devis
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"📄 Premier devis créé : {premier_devis.numero_devis} (brouillon)",
                        utilisateur=request.user
                    )

                    if client_type == 'nouveau':
                        HistoriqueOperation.objects.create(
                            operation=operation,
                            action=f"Client {client.nom} {client.prenom} créé automatiquement",
                            utilisateur=request.user
                        )
                    
                    print(f"\n{'='*80}")
                    print("✓✓✓ SUCCÈS - PARCOURS A TERMINÉ")
                    print(f"{'='*80}\n")
                    
                    messages.success(
                        request, 
                        f"✅ Opération {operation.id_operation} créée avec succès ! "
                        f"Le devis {premier_devis.numero_devis} est prêt à être complété."
                    )
                    
                except Exception as e:
                    print(f"✗ Erreur création premier devis: {e}")
                    # Supprimer l'opération si le devis échoue
                    operation.delete()
                    messages.error(request, f"❌ Erreur lors de la création du devis : {str(e)}")
                    return redirect('operation_create')
                
                return redirect('operation_detail', operation_id=operation.id)

            # ========================================
            # PARCOURS B : SANS DEVIS (OPÉRATION DIRECTE)
            # ========================================
            else:
                print(f"\n{'─'*80}")
                print("PARCOURS B : CRÉATION OPÉRATION DIRECTE")
                print(f"{'─'*80}")
                
                statut_initial = request.POST.get('statut_initial', 'a_planifier')
                print(f"Statut initial: {statut_initial}")
                
                # Gestion des dates
                
                date_intervention_str = request.POST.get('date_intervention', '')
                
                date_prevue = None
                date_realisation = None
                date_paiement = None
                
                print(f"\n{'─'*80}")
                print("TRAITEMENT DES DATES")
                print(f"{'─'*80}")
                print(f"date_intervention reçue: '{date_intervention_str}'")
                
                if date_intervention_str:
                    try:
                        date_intervention = datetime.fromisoformat(date_intervention_str.replace('T', ' '))
                        
                        if statut_initial == 'planifie':
                            date_prevue = date_intervention
                            print(f"✓ date_prevue = {date_prevue}")
                        elif statut_initial == 'realise':
                            date_realisation = date_intervention
                            print(f"✓ date_realisation = {date_realisation}")
                        elif statut_initial == 'paye':
                            date_realisation = date_intervention
                            date_paiement = date_intervention  # Par défaut même date
                            print(f"✓ date_realisation = {date_realisation}")
                            print(f"✓ date_paiement = {date_paiement}")
                    except ValueError as e:
                        print(f"✗ Erreur conversion date: {e}")
                        messages.error(request, f"⚠️ Format de date invalide: {e}")
                        clients = Client.objects.filter(user=request.user).order_by('nom', 'prenom')
                        return render(request, 'operations/create.html', {'clients': clients})
                
                # Création opération
                print(f"\n{'─'*80}")
                print("CRÉATION OPÉRATION")
                print(f"{'─'*80}")
                
                operation = Operation.objects.create(
                    user=request.user,
                    client=client,
                    type_prestation=type_prestation,
                    adresse_intervention=adresse_finale,
                    commentaires=commentaires,
                    avec_devis=False,
                    statut=statut_initial,
                    date_paiement=date_paiement
                )
                
                # ✅ AJOUTER CE BLOC ICI (après ligne 217)
                print(f"\n{'─'*80}")
                print("CRÉATION PASSAGE OPÉRATION")
                print(f"{'─'*80}")

                # Créer le passage selon le statut
                if statut_initial == 'a_planifier':
                    print(f"✓ Aucun passage créé (l'utilisateur ajoutera manuellement)")

                elif statut_initial == 'planifie':
                    # Passage planifié avec date
                    PassageOperation.objects.create(
                        operation=operation,
                        date_prevue=date_prevue,
                        realise=False
                    )
                    print(f"✓ Passage créé (planifié) - date: {date_prevue}")

                elif statut_initial == 'realise':
                    # Passage réalisé avec date
                    PassageOperation.objects.create(
                        operation=operation,
                        date_prevue=None,
                        date_realisation=date_realisation,
                        realise=True
                    )
                    print(f"✓ Passage créé (réalisé) - date: {date_realisation}")

                elif statut_initial == 'paye':
                    # Passage payé avec date
                    PassageOperation.objects.create(
                        operation=operation,
                        date_prevue=None,
                        date_realisation=date_realisation,
                        realise=True
                    )
                    print(f"✓ Passage créé (payé) - date: {date_realisation}")

                print(f"{'─'*80}\n")
                
                print(f"✓ Opération créée (DIRECTE)")
                print(f"  ID: {operation.id}")
                print(f"  Code: {operation.id_operation}")
                print(f"  avec_devis: False")
                print(f"  statut: {statut_initial}")
                print(f"  date_prevue: {date_prevue}")
                print(f"  date_realisation: {date_realisation}")
                print(f"  date_paiement: {date_paiement}")
                
                # ========================================
                # CRÉATION DES LIGNES D'INTERVENTION
                # ========================================
                # CRÉATION DES LIGNES D'INTERVENTION
                descriptions = request.POST.getlist('description[]')
                montants = request.POST.getlist('montant[]')

                interventions_creees = 0
                for i, (description, montant) in enumerate(zip(descriptions, montants)):
                    desc_clean = description.strip()
                    mont_clean = montant.strip()
                    
                    if desc_clean and mont_clean:
                        try:
                            # ✅ NOUVEAU FORMAT : montant saisi = prix unitaire HT
                            intervention = Intervention.objects.create(
                                operation=operation,
                                description=desc_clean,
                                quantite=Decimal('1'),
                                unite='forfait',
                                prix_unitaire_ht=Decimal(mont_clean),  # ← Le montant saisi = PU HT
                                taux_tva=Decimal('10'),
                                ordre=i + 1
                            )
                            interventions_creees += 1
                        except (ValueError, TypeError) as e:
                            print(f"  ✗ Erreur montant ligne {i+1}: {e}")
                
                # ========================================
                # GESTION AUTOMATIQUE PAIEMENT SI PAYÉ
                # ========================================
                if statut_initial == 'paye' and interventions_creees > 0:
                    print(f"\n{'─'*80}")
                    print("GESTION AUTOMATIQUE PAIEMENT (STATUT = PAYÉ)")
                    print(f"{'─'*80}")
                    
                    montant_total = operation.montant_total
                    print(f"Montant total: {montant_total}€")
                    
                    if montant_total > 0:
                        Echeance.objects.create(
                            operation=operation,
                            numero=1,
                            montant=montant_total,
                            date_echeance=date_paiement.date() if date_paiement else timezone.now().date(),
                            paye=True,
                            ordre=1
                        )
                        print(f"✓ Échéance automatique créée: {montant_total}€ (payée)")
                        
                        HistoriqueOperation.objects.create(
                            operation=operation,
                            action=f"💰 Paiement comptant enregistré: {montant_total}€",
                            utilisateur=request.user
                        )
                
                # ========================================
                # HISTORIQUE
                # ========================================
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"Opération créée (directe) - Statut: {operation.get_statut_display()}",
                    utilisateur=request.user
                )
                
                if client_type == 'nouveau':
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"Client {client.nom} {client.prenom} créé automatiquement",
                        utilisateur=request.user
                    )
                
                if interventions_creees > 0:
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"{interventions_creees} ligne(s) d'intervention ajoutée(s)",
                        utilisateur=request.user
                    )
                
                print(f"\n{'='*80}")
                print("✓✓✓ SUCCÈS - PARCOURS B TERMINÉ")
                print(f"{'='*80}\n")
                
                messages.success(request, f"✅ Opération {operation.id_operation} créée avec succès (statut: {operation.get_statut_display()})")
                return redirect('operation_detail', operation_id=operation.id)
            
        except Exception as e:
            print(f"\n{'='*80}")
            print("✗✗✗ ERREUR CRITIQUE")
            print(f"{'='*80}")
            print(f"Type d'erreur: {type(e).__name__}")
            print(f"Message: {str(e)}")
            print(f"\nTraceback complet:")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")
            
            messages.error(request, f"❌ Erreur lors de la création : {str(e)}")
            clients = Client.objects.filter(user=request.user).order_by('nom', 'prenom')
            return render(request, 'operations/create.html', {'clients': clients})
    
    # ========================================
    # GET - AFFICHAGE FORMULAIRE
    # ========================================
    clients = Client.objects.filter(user=request.user).order_by('nom', 'prenom')
    
    # Exclure 'devis_refuse' du formulaire de création
    statuts_disponibles = [
        (value, label) 
        for value, label in Operation.STATUTS 
        if value != 'devis_refuse' and value != 'en_attente_devis'
    ]
    
    context = {
        'clients': clients,
        'statuts_choices': statuts_disponibles,
    }
    
    return render(request, 'operations/create.html', context)


@login_required
def client_create(request):
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        email = request.POST.get('email', '').strip()
        adresse = request.POST.get('adresse', '').strip()
        ville = request.POST.get('ville', '').strip()
        
        if not nom or not telephone:
            messages.error(request, "Le nom et le téléphone sont obligatoires")
        else:
            try:
                client = Client.objects.create(
                    user=request.user,
                    nom=nom,
                    prenom=prenom,
                    telephone=telephone,
                    email=email,
                    adresse=adresse,
                    ville=ville
                )
                messages.success(request, f"Client {client.nom} {client.prenom} créé avec succès !")
                return redirect('client_detail', client_id=client.id)
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
    
    return render(request, 'clients/client_form.html', {
        'is_edit': False,
        'nom': '',
        'prenom': '',
        'telephone': '',
        'email': '',
        'adresse': '',
        'ville': ''
    })

@login_required
def client_delete(request, client_id):
    """Suppression d'un client avec ou sans ses opérations"""
    client = get_object_or_404(Client, id=client_id, user=request.user)
    
    if request.method == 'POST':
        force_delete = request.POST.get('force_delete') == 'true'
        operations = Operation.objects.filter(client=client)
        nom_client = f"{client.nom} {client.prenom}"
        
        if force_delete and operations.exists():
            # Suppression forcée : client + opérations
            nb_operations = operations.count()
            
            # Supprimer les interventions et historiques
            for operation in operations:
                operation.interventions.all().delete()
                operation.historique.all().delete()
            
            # Supprimer les opérations puis le client
            operations.delete()
            client.delete()
            
            messages.success(request, f"Client {nom_client} et ses {nb_operations} opération(s) supprimés avec succès.")
        else:
            # Suppression normale
            if operations.exists():
                messages.error(request, f"Impossible de supprimer {nom_client} : ce client a des opérations liées.")
                return redirect('client_detail', client_id=client.id)
            
            client.delete()
            messages.success(request, f"Client {nom_client} supprimé avec succès.")
        
        return redirect('clients')
    
    # GET : rediriger vers la fiche client
    return redirect('client_detail', client_id=client.id)

@login_required
def client_edit(request, client_id):
    """Modification d'un client en AJAX"""
    client = get_object_or_404(Client, id=client_id, user=request.user)
    
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        email = request.POST.get('email', '').strip()
        adresse = request.POST.get('adresse', '').strip()
        ville = request.POST.get('ville', '').strip()
        
        if not nom or not telephone:
            messages.error(request, "Le nom et le téléphone sont obligatoires")
        else:
            try:
                client.nom = nom
                client.prenom = prenom
                client.telephone = telephone
                client.email = email
                client.adresse = adresse
                client.ville = ville
                client.save()
                
                messages.success(request, f"Client {client.nom} {client.prenom} modifié avec succès !")
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
        
        # Rediriger vers la même page pour rafraîchir
        return redirect('client_detail', client_id=client.id)

@login_required
def profil_entreprise(request):
    """Page de profil de l'entreprise"""
    
    # Récupérer ou créer le profil
    profil, created = ProfilEntreprise.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Récupérer tous les champs du formulaire
        profil.nom_entreprise = request.POST.get('nom_entreprise', '').strip()
        profil.forme_juridique = request.POST.get('forme_juridique', '')
        profil.adresse = request.POST.get('adresse', '').strip()
        profil.code_postal = request.POST.get('code_postal', '').strip()
        profil.ville = request.POST.get('ville', '').strip()
        profil.siret = request.POST.get('siret', '').strip()
        profil.rcs = request.POST.get('rcs', '').strip()
        profil.code_ape = request.POST.get('code_ape', '').strip()
        
        capital_social_str = request.POST.get('capital_social', '').strip()
        if capital_social_str:
            try:
                profil.capital_social = Decimal(capital_social_str)
            except:
                profil.capital_social = None
        else:
            profil.capital_social = None
        
        profil.tva_intracommunautaire = request.POST.get('tva_intracommunautaire', '').strip()
        profil.telephone = request.POST.get('telephone', '').strip()
        profil.email = request.POST.get('email', '').strip()
        profil.site_web = request.POST.get('site_web', '').strip()
        
        profil.assurance_decennale_nom = request.POST.get('assurance_decennale_nom', '').strip()
        profil.assurance_decennale_numero = request.POST.get('assurance_decennale_numero', '').strip()
        
        assurance_validite_str = request.POST.get('assurance_decennale_validite', '')
        if assurance_validite_str:
            try:
                
                profil.assurance_decennale_validite = datetime.strptime(assurance_validite_str, '%Y-%m-%d').date()
            except:
                profil.assurance_decennale_validite = None
        else:
            profil.assurance_decennale_validite = None
        
        profil.qualifications = request.POST.get('qualifications', '').strip()
        profil.iban = request.POST.get('iban', '').strip()
        profil.bic = request.POST.get('bic', '').strip()
        profil.mentions_legales_devis = request.POST.get('mentions_legales_devis', '').strip()
        
        # Gestion du logo
        if 'logo' in request.FILES:
            profil.logo = request.FILES['logo']
        
        profil.save()
        
        messages.success(request, "✅ Profil entreprise mis à jour avec succès !")
        return redirect('profil')
    
    context = {
        'profil': profil,
        'formes_juridiques': ProfilEntreprise.FORMES_JURIDIQUES,
    }
    
    return render(request, 'core/profil.html', context)

    # Dans views.py
@login_required
def operation_edit(request, operation_id):
    """Modification des informations générales d'une opération"""
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    if request.method == 'POST':
        type_prestation = request.POST.get('type_prestation', '').strip()
        adresse_intervention = request.POST.get('adresse_intervention', '').strip()
        
        if not type_prestation or not adresse_intervention:
            messages.error(request, "Le type de prestation et l'adresse sont obligatoires")
        else:
            try:
                operation.type_prestation = type_prestation
                operation.adresse_intervention = adresse_intervention
                operation.save()
                
                # Ajouter à l'historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"Informations mises à jour : {type_prestation}",
                    utilisateur=request.user
                )
                
                messages.success(request, "Opération modifiée avec succès !")
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
        
        return redirect('operation_detail', operation_id=operation.id)

@login_required
def telecharger_devis_pdf(request, devis_id):
    """
    Vue pour télécharger le PDF d'un devis spécifique
    """
    # ✅ CHANGEMENT : On récupère maintenant un Devis, pas une Operation
    devis = get_object_or_404(Devis, id=devis_id, operation__user=request.user)
    operation = devis.operation
    
    # Vérifier que le devis a au moins une ligne
    if not devis.lignes.exists():
        messages.error(request, "❌ Le devis ne contient aucune ligne.")
        return redirect('operation_detail', operation_id=operation.id)
    
    # Vérifier que le devis n'est pas en brouillon
    if devis.statut == 'brouillon':
        messages.warning(request, "⚠️ Le devis est encore en brouillon. Générez-le d'abord.")
        return redirect('operation_detail', operation_id=operation.id)
    
    # Récupérer le profil entreprise
    try:
        profil = ProfilEntreprise.objects.get(user=request.user)
    except ProfilEntreprise.DoesNotExist:
        messages.error(request, "❌ Veuillez d'abord compléter votre profil entreprise.")
        return redirect('profil')
    
    # Vérifier que le profil est complet
    if not profil.est_complet:
        messages.error(request, "❌ Votre profil entreprise est incomplet. Complétez-le pour générer des PDF.")
        return redirect('profil')
    
    # ✅ CHANGEMENT : Passer le devis au générateur PDF (pas l'opération)
    pdf_data = generer_devis_pdf(devis, profil)
    
    # Retourner le PDF en téléchargement
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="devis_{devis.numero_devis}.pdf"'
    
    return response

@login_required
def telecharger_facture_pdf(request, echeance_id):
    """
    Vue pour télécharger le PDF d'une facture
    """
    echeance = get_object_or_404(Echeance, id=echeance_id, operation__user=request.user)
    
    # Vérifier que la facture est générée
    if not echeance.facture_generee or not echeance.numero_facture:
        messages.error(request, "❌ La facture n'a pas encore été générée.")
        return redirect('operation_detail', operation_id=echeance.operation.id)
    
    # Récupérer le profil entreprise
    try:
        profil = ProfilEntreprise.objects.get(user=request.user)
    except ProfilEntreprise.DoesNotExist:
        messages.error(request, "❌ Veuillez d'abord compléter votre profil entreprise.")
        return redirect('profil')
    
    # Vérifier que le profil est complet
    if not profil.est_complet:
        messages.error(request, "❌ Votre profil entreprise est incomplet. Complétez-le pour générer des PDF.")
        return redirect('profil')
    
    # ✅ GÉNÉRATION DU PDF (VERSION FINALE)
    from .pdf_generator import generer_facture_pdf
    
    pdf_data = generer_facture_pdf(echeance, profil)
    
    # Retourner le PDF en téléchargement
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="facture_{echeance.numero_facture}.pdf"'
    
    return response

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            
            # ✅ CRÉER LE PROFIL ENTREPRISE AUTOMATIQUEMENT
            ProfilEntreprise.objects.create(user=user)
            
            messages.success(request, f'Compte créé pour {username}! Connectez-vous.')
            # ✅ TEST : Rediriger vers login au lieu de connecter
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def simple_logout(request):
    if request.user.is_authenticated:
        logout(request)
    return redirect('/login/')

# ════════════════════════════════════════════════════════════════════════
# ✅ NOUVELLES ACTIONS POUR INTERVENTIONS MULTIPLES
# ════════════════════════════════════════════════════════════════════════

@login_required
def planifier_intervention(request, operation_id, intervention_id):
    """
    Planifie ou replanifie une intervention
    Modifie la date_prevue d'une intervention existante
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    intervention = get_object_or_404(Intervention, id=intervention_id, operation=operation)
    
    if request.method == 'POST':
        date_prevue_str = request.POST.get('date_prevue')
        
        if date_prevue_str:
            try:
                # Parser la date au format ISO (YYYY-MM-DDTHH:MM)
                from datetime import datetime
                date_prevue = datetime.fromisoformat(date_prevue_str)
                
                # Mettre à jour la date prévue
                intervention.date_prevue = date_prevue
                intervention.save()  # Le save() recalcule automatiquement l'ordre et le statut
                
                messages.success(
                    request,
                    f"✅ Intervention planifiée le {date_prevue.strftime('%d/%m/%Y à %H:%M')}"
                )
                
                # Enregistrer dans l'historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    utilisateur=request.user,
                    action=f"Intervention planifiée : {intervention.description[:50]} - {date_prevue.strftime('%d/%m/%Y %H:%M')}"
                )
                
            except ValueError:
                messages.error(request, "❌ Format de date invalide")
        else:
            messages.error(request, "❌ Veuillez saisir une date")
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def marquer_realise(request, operation_id, intervention_id):
    """
    Marque une intervention comme réalisée (ou inverse)
    Bascule le champ 'realise' et remplit automatiquement 'date_realisation'
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    intervention = get_object_or_404(Intervention, id=intervention_id, operation=operation)
    
    if request.method == 'POST':
        # Basculer l'état réalisé
        intervention.realise = not intervention.realise
        intervention.save()  # Le save() gère automatiquement date_realisation
        
        if intervention.realise:
            messages.success(
                request,
                f"✅ Intervention marquée comme réalisée"
            )
            action = f"Intervention réalisée : {intervention.description[:50]}"
        else:
            messages.info(
                request,
                f"ℹ️ Intervention marquée comme non réalisée"
            )
            action = f"Intervention marquée comme non réalisée : {intervention.description[:50]}"
        
        # Enregistrer dans l'historique
        HistoriqueOperation.objects.create(
            operation=operation,
            utilisateur=request.user,
            action=action
        )
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def ajouter_commentaire(request, operation_id, intervention_id):
    """
    Ajoute ou modifie un commentaire sur une intervention
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    intervention = get_object_or_404(Intervention, id=intervention_id, operation=operation)
    
    if request.method == 'POST':
        commentaire = request.POST.get('commentaire', '').strip()
        
        intervention.commentaire = commentaire
        intervention.save()
        
        if commentaire:
            messages.success(request, "✅ Commentaire ajouté")
        else:
            messages.info(request, "ℹ️ Commentaire supprimé")
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def creer_nouvelle_intervention(request, operation_id):
    """
    Crée une nouvelle intervention pour une opération existante
    (pour les opérations qui nécessitent plusieurs passages)
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    if request.method == 'POST':
        description = request.POST.get('description', '').strip()
        date_prevue_str = request.POST.get('date_prevue', '').strip()
        
        if not description:
            messages.error(request, "❌ Veuillez saisir une description")
            return redirect('operation_detail', operation_id=operation.id)
        
        # Créer la nouvelle intervention
        nouvelle_intervention = Intervention.objects.create(
            operation=operation,
            description=description,
            quantite=1,
            unite='forfait',
            prix_unitaire_ht=0,
            montant=0,
            taux_tva=10.0
        )
        
        # Si une date prévue est fournie, la définir
        if date_prevue_str:
            try:
                from datetime import datetime
                date_prevue = datetime.fromisoformat(date_prevue_str)
                nouvelle_intervention.date_prevue = date_prevue
                nouvelle_intervention.save()
            except ValueError:
                pass  # Si format invalide, on laisse sans date
        
        messages.success(
            request,
            f"✅ Nouvelle intervention ajoutée : {description}"
        )
        
        # Enregistrer dans l'historique
        HistoriqueOperation.objects.create(
            operation=operation,
            utilisateur=request.user,
            action=f"Nouvelle intervention créée : {description}"
        )
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def supprimer_intervention(request, operation_id, intervention_id):
    """
    Supprime une intervention
    ATTENTION : Vérifie que ce n'est pas la dernière intervention de l'opération
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    intervention = get_object_or_404(Intervention, id=intervention_id, operation=operation)
    
    if request.method == 'POST':
        # Vérifier qu'il reste au moins une intervention
        nb_interventions = operation.interventions.count()
        
        if nb_interventions <= 1:
            messages.error(
                request,
                "❌ Impossible de supprimer la dernière intervention d'une opération"
            )
            return redirect('operation_detail', operation_id=operation.id)
        
        # Enregistrer la description avant suppression
        description = intervention.description[:50]
        
        # Supprimer l'intervention
        intervention.delete()
        
        messages.success(
            request,
            f"✅ Intervention supprimée : {description}"
        )
        
        # Enregistrer dans l'historique
        HistoriqueOperation.objects.create(
            operation=operation,
            utilisateur=request.user,
            action=f"Intervention supprimée : {description}"
        )
        
        # Recalculer le statut de l'opération
        operation.update_statut_from_interventions()
    
    return redirect('operation_detail', operation_id=operation.id)

@login_required
def ajouter_passage_operation(request, operation_id):
    """
    Ajoute un nouveau passage pour une opération
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    if request.method == 'POST':
        date_prevue_str = request.POST.get('date_prevue', '').strip()
        commentaire = request.POST.get('commentaire', '').strip()
        
        # ✅ Mémoriser le statut avant modification
        statut_avant = operation.statut
        
        # Créer le passage
        passage = PassageOperation.objects.create(
            operation=operation,
            commentaire=commentaire
        )
        
        # Si une date est fournie
        if date_prevue_str:
            try:
                date_prevue = datetime.fromisoformat(date_prevue_str)
                passage.date_prevue = date_prevue
                passage.save()
                
                # ✅ LOGIQUE DE MISE À JOUR DU STATUT
                if operation.statut in ['realise', 'paye']:
                    # Opération déjà terminée → repasse en planifié avec avertissement
                    operation.statut = 'planifie'
                    operation.save()
                    
                    messages.warning(
                        request,
                        f"⚠️ Nouveau passage ajouté ! L'opération repasse de '{statut_avant}' à 'Planifié'."
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        utilisateur=request.user,
                        action=f"Passage {passage.numero} ajouté - {date_prevue.strftime('%d/%m/%Y %H:%M')} - ⚠️ Opération repassée de '{statut_avant}' à 'planifie'"
                    )
                    
                elif operation.statut in ['en_attente_devis', 'a_planifier']:
                    # Opération pas encore planifiée → passe en planifié
                    operation.statut = 'planifie'
                    operation.save()
                    
                    messages.success(
                        request,
                        f"✅ Passage {passage.numero} planifié le {date_prevue.strftime('%d/%m/%Y à %H:%M')}"
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        utilisateur=request.user,
                        action=f"Passage {passage.numero} ajouté - Planifié le {date_prevue.strftime('%d/%m/%Y %H:%M')}"
                    )
                else:
                    # Déjà en planifié → juste ajouter
                    messages.success(
                        request,
                        f"✅ Passage {passage.numero} planifié le {date_prevue.strftime('%d/%m/%Y à %H:%M')}"
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        utilisateur=request.user,
                        action=f"Passage {passage.numero} ajouté - Planifié le {date_prevue.strftime('%d/%m/%Y %H:%M')}"
                    )
                
            except ValueError:
                messages.success(request, f"✅ Passage {passage.numero} créé (à planifier)")
                HistoriqueOperation.objects.create(
                    operation=operation,
                    utilisateur=request.user,
                    action=f"Passage {passage.numero} ajouté (à planifier)"
                )
        else:
            # Pas de date fournie
            messages.success(request, f"✅ Passage {passage.numero} créé (à planifier)")
            HistoriqueOperation.objects.create(
                operation=operation,
                utilisateur=request.user,
                action=f"Passage {passage.numero} ajouté (à planifier)"
            )
    
    return redirect('operation_detail', operation_id=operation.id)

@login_required
def marquer_passage_realise(request, operation_id, passage_id):
    """
    Marque un passage comme réalisé (ou inverse)
    Avec confirmation si c'est le dernier passage
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        # Récupérer si l'utilisateur a confirmé la réalisation de l'opération
        confirmer_realise = request.POST.get('confirmer_realise') == 'true'
        
        # Basculer l'état du passage
        passage.realise = not passage.realise
        passage.save()
        
        if passage.realise:
            # ✅ Passage marqué comme réalisé
            messages.success(request, f"✅ Passage {passage.numero} marqué comme réalisé")
            action = f"Passage {passage.numero} réalisé"
            
            # Compter les passages non réalisés APRÈS cette validation
            passages_non_realises = operation.passages.filter(realise=False).count()
            
            if passages_non_realises == 0:
                # ✅ C'était le DERNIER passage !
                if confirmer_realise:
                    # L'utilisateur a confirmé → passer l'opération en réalisé
                    operation.statut = 'realise'
                    operation.date_realisation = timezone.now()
                    operation.save()
                    
                    messages.success(
                        request, 
                        "🎉 Tous les passages sont réalisés ! L'opération est marquée comme RÉALISÉE."
                    )
                    action += " - ✅ Opération marquée comme réalisée"
                else:
                    # L'utilisateur n'a pas confirmé → garder en planifié
                    messages.info(
                        request,
                        "ℹ️ Tous les passages sont validés. Vous pouvez marquer l'opération comme réalisée manuellement."
                    )
            else:
                # Il reste des passages → s'assurer que le statut est cohérent
                if operation.statut == 'a_planifier':
                    operation.statut = 'planifie'
                    operation.save()
        else:
            # ✅ Passage marqué comme NON réalisé (annulation)
            messages.info(request, f"ℹ️ Passage {passage.numero} marqué comme non réalisé")
            action = f"Passage {passage.numero} annulé (non réalisé)"
            
            # Si l'opération était réalisée, repasser en planifié
            if operation.statut == 'realise':
                operation.statut = 'planifie'
                operation.save()
                messages.warning(request, "⚠️ L'opération repasse en 'Planifié' car un passage n'est plus réalisé.")
                action += " - ⚠️ Opération repassée en 'planifie'"
        
        HistoriqueOperation.objects.create(
            operation=operation,
            utilisateur=request.user,
            action=action
        )
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def supprimer_passage_operation(request, operation_id, passage_id):
    """
    Supprime un passage
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        numero = passage.numero
        passage.delete()
        
        messages.success(request, f"✅ Passage {numero} supprimé")
        
        HistoriqueOperation.objects.create(
            operation=operation,
            utilisateur=request.user,
            action=f"Passage {numero} supprimé"
        )
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def ajouter_commentaire_passage(request, operation_id, passage_id):
    """
    Ajoute/modifie un commentaire sur un passage
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        commentaire = request.POST.get('commentaire', '').strip()
        
        passage.commentaire = commentaire
        passage.save()
        
        if commentaire:
            messages.success(request, "✅ Commentaire ajouté")
        else:
            messages.info(request, "ℹ️ Commentaire supprimé")
    
    return redirect('operation_detail', operation_id=operation.id)

@login_required
def planifier_passage_operation(request, operation_id, passage_id):
    """
    Planifie ou modifie la date d'un passage existant
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        date_prevue_str = request.POST.get('date_prevue')
        
        if date_prevue_str:
            try:
                date_prevue = datetime.fromisoformat(date_prevue_str)
                
                passage.date_prevue = date_prevue
                passage.save()
                
                # ✅ Mémoriser le statut avant
                statut_avant = operation.statut
                
                # ✅ LOGIQUE DE MISE À JOUR DU STATUT
                if operation.statut in ['realise', 'paye']:
                    # Opération terminée → repasse en planifié
                    operation.statut = 'planifie'
                    operation.save()
                    
                    messages.warning(
                        request,
                        f"⚠️ Passage {passage.numero} replanifié ! L'opération repasse de '{statut_avant}' à 'Planifié'."
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        utilisateur=request.user,
                        action=f"Passage {passage.numero} planifié : {date_prevue.strftime('%d/%m/%Y %H:%M')} - ⚠️ Opération repassée en 'planifie'"
                    )
                    
                elif operation.statut in ['en_attente_devis', 'a_planifier']:
                    # Pas encore planifié → passe en planifié
                    operation.statut = 'planifie'
                    operation.save()
                    
                    messages.success(
                        request,
                        f"✅ Passage {passage.numero} planifié le {date_prevue.strftime('%d/%m/%Y à %H:%M')}"
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        utilisateur=request.user,
                        action=f"Passage {passage.numero} planifié : {date_prevue.strftime('%d/%m/%Y %H:%M')}"
                    )
                else:
                    # Déjà planifié → juste mettre à jour
                    messages.success(
                        request,
                        f"✅ Passage {passage.numero} planifié le {date_prevue.strftime('%d/%m/%Y à %H:%M')}"
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        utilisateur=request.user,
                        action=f"Passage {passage.numero} planifié : {date_prevue.strftime('%d/%m/%Y %H:%M')}"
                    )
                
            except ValueError:
                messages.error(request, "❌ Format de date invalide")
        else:
            messages.error(request, "❌ Veuillez saisir une date")
    
    return redirect('operation_detail', operation_id=operation.id)


@login_required
def supprimer_compte(request):
    """Suppression définitive du compte utilisateur"""
    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirmation = request.POST.get('confirmation', '')
        
        if confirmation != 'SUPPRIMER':
            messages.error(request, "Veuillez taper SUPPRIMER pour confirmer.")
            return redirect('profil')
        
        if not check_password(password, request.user.password):
            messages.error(request, "Mot de passe incorrect.")
            return redirect('profil')
        
        user = request.user
        logout(request)
        user.delete()
        
        messages.success(request, "Votre compte a été supprimé.")
        return redirect('login')
    
    return redirect('profil')