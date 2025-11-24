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
    fix_client_constraint()
    try:
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
        # 🔥 CALENDRIER - VERSION PASSAGES
        # ========================================
        today = timezone.now().date()
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
            # KPI essentiels
            'nb_clients': nb_clients,
            'ca_mois': ca_mois,
            'nb_en_attente_devis': nb_en_attente_devis,
            'nb_a_planifier': nb_a_planifier,
            'nb_paiements_retard': nb_paiements_retard,
            'nb_operations_sans_paiement': nb_operations_sans_paiement,
            
            # Calendrier
            'calendar_events_json': json.dumps(calendar_events),
            'calendar_events': calendar_events,
        }
        
        return render(request, 'core/dashboard.html', context)
        
    except Exception as e:
        return HttpResponse(f"<h1>CRM Artisans</h1><p>Erreur : {str(e)}</p>")

@login_required
def operations_list(request):
    """Page Opérations avec filtrage par période + vue financière"""
    
    # ========================================
    # GESTION DE LA PÉRIODE
    # ========================================
    today = timezone.now().date()
    
    # Récupérer les paramètres de période
    periode = request.GET.get('periode', 'this_month')
    mois_param = request.GET.get('mois', '')
    nav = request.GET.get('nav', '')
    
    # Calculer les dates de début et fin selon la période
    if mois_param and nav:
        # Navigation mensuelle (précédent/suivant)
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
        # Sélection directe d'un mois
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
    
    elif periode == 'ytd':  # Year To Date
        periode_start = today.replace(month=1, day=1)
        periode_end = today
    
    else:
        periode_start = today.replace(day=1)
        periode_end = (periode_start + relativedelta(months=1)) - timedelta(days=1)
    
    # ========================================
    # CALCULS FINANCIERS (PÉRIODE)
    # ========================================
    # Pour les calculs financiers (limité à la période)
    operations_periode = Operation.objects.filter(
        user=request.user,
        statut__in=['realise', 'paye'],
        date_realisation__gte=periode_start,
        date_realisation__lte=periode_end
    ).prefetch_related('echeances')

    # Pour détecter les paiements non planifiés (TOUTES les opérations réalisées)
    operations_pour_paiements = Operation.objects.filter(
        user=request.user,
        statut__in=['realise', 'paye']
    ).prefetch_related('echeances')

    ca_encaisse = 0
    ca_en_attente_total = 0
    ca_retard = 0
    ca_non_planifies = 0
    nb_paiements_retard = 0
    nb_operations_sans_paiement = 0

    operations_avec_retards_ids = []
    operations_sans_echeances_ids = []

    # ✅ Boucle 1 : Calculs financiers sur la PÉRIODE
    for op in operations_periode:
        montant_total = op.montant_total
        
        # Montants payés
        montant_paye = op.echeances.filter(paye=True).aggregate(
            total=Sum('montant')
        )['total'] or 0
        ca_encaisse += montant_paye
        
        # Montants planifiés
        total_planifie = op.echeances.aggregate(
            total=Sum('montant')
        )['total'] or 0
        
        reste = montant_total - montant_paye
        
        if reste > 0:
            ca_en_attente_total += reste
        
        # Retards
        retards = op.echeances.filter(
            paye=False,
            date_echeance__lt=today
        )
        
        if retards.exists():
            montant_retard = retards.aggregate(total=Sum('montant'))['total'] or 0
            ca_retard += montant_retard
            nb_paiements_retard += retards.count()
            operations_avec_retards_ids.append(op.id)
        
        # Non planifiés (DANS la période uniquement) - pour le KPI CA
        reste_a_planifier = montant_total - total_planifie
        
        if reste_a_planifier > 0:
            ca_non_planifies += reste_a_planifier

    # ✅ Boucle 2 : Détecter TOUTES les opérations sans paiement complet (pour le filtre)
    for op in operations_pour_paiements:
        total_planifie = op.echeances.aggregate(
            total=Sum('montant')
        )['total'] or 0
        
        reste = op.montant_total - total_planifie
        
        if reste > 0:
            if op.id not in operations_sans_echeances_ids:
                operations_sans_echeances_ids.append(op.id)
                nb_operations_sans_paiement += 1

    # ✅ CA Prévisionnel 30 jours - CORRECTION
    date_dans_30j = today + timedelta(days=30)
    operations_previsionnel = Operation.objects.filter(
        user=request.user,
        statut='planifie',
        date_prevue__gte=today,
        date_prevue__lte=date_dans_30j
    )
    ca_previsionnel_30j = sum(op.montant_total for op in operations_previsionnel if op.montant_total)  # ← Filtre les None
    
    # ✅ Variation vs période précédente (pour le KPI)
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
    # FILTRAGE DES OPÉRATIONS
    # ========================================
    operations = Operation.objects.filter(
        user=request.user
    ).select_related('client').prefetch_related('interventions', 'echeances')
    
    # Filtrer par période (sauf pour certains filtres)
    filtre = request.GET.get('filtre', 'toutes')

    recherche = request.GET.get('recherche', '')
    
    # ✅ NOUVEAU
    if filtre == 'brouillon':
        # Opérations qui ont au moins 1 devis en brouillon
        operations = operations.filter(
            avec_devis=True
        ).filter(
            Exists(Devis.objects.filter(operation=OuterRef('pk'), statut='brouillon'))
        )
        
    # ✅ NOUVEAU : Opérations AVEC DEVIS mais SANS aucun devis créé
    elif filtre == 'sans_devis':
        # Opérations marquées "avec_devis=True" mais qui n'ont AUCUN devis
        operations = operations.annotate(
            nb_devis=Count('devis_set')
        ).filter(
            avec_devis=True,
            nb_devis=0
        )

    elif filtre == 'genere_non_envoye':
        # Opérations qui ont au moins 1 devis prêt (généré mais pas encore envoyé)
        operations = operations.filter(
            avec_devis=True
        ).filter(
            Exists(Devis.objects.filter(operation=OuterRef('pk'), statut='pret'))
        )
        
    # ✅ NOUVEAU
    elif filtre == 'devis_en_attente':
        # Opérations qui ont au moins 1 devis envoyé et en attente (non expiré)
        operations_en_attente_ids = []
        
        for op in operations.filter(avec_devis=True):
            devis_en_attente = op.devis_set.filter(statut='envoye', date_envoi__isnull=False)
            
            for devis in devis_en_attente:
                if devis.date_limite and devis.date_limite >= timezone.now().date():
                    operations_en_attente_ids.append(op.id)
                    break
                elif not devis.date_limite:
                    operations_en_attente_ids.append(op.id)
                    break
        
        operations = operations.filter(id__in=operations_en_attente_ids)

    # ✅ NOUVEAU
    elif filtre == 'expire':
        # Opérations qui ont au moins 1 devis expiré
        operations_expire_ids = []
        
        for op in operations.filter(avec_devis=True):
            devis_envoyes = op.devis_set.filter(statut='envoye', date_envoi__isnull=False)
            
            for devis in devis_envoyes:
                if devis.est_expire:
                    operations_expire_ids.append(op.id)
                    break
        
        operations = operations.filter(id__in=operations_expire_ids)

    elif filtre == 'a_traiter':
        # ✅ CORRECTION : Passages en retard OU opérations planifiées en retard
        now = timezone.now()
        
        # 1. Passages avec date passée et non réalisés
        passages_en_retard = PassageOperation.objects.filter(
            operation__user=request.user,
            date_prevue__lt=now,
            realise=False
        ).values_list('operation_id', flat=True).distinct()
        
        # 2. Opérations planifiées (ancien système) avec date_prevue passée
        operations_planifiees_retard = Operation.objects.filter(
            user=request.user,
            statut='planifie',
            date_prevue__lt=now
        ).values_list('id', flat=True)
        
        # 3. Combiner les deux listes
        ids_a_traiter = set(passages_en_retard) | set(operations_planifiees_retard)
        
        operations = operations.filter(id__in=ids_a_traiter)

    # ✅ ENRICHISSEMENT POUR FILTRES SPÉCIAUX
    elif filtre == 'retards':
        operations = operations.filter(id__in=operations_avec_retards_ids)
        
        for op in operations:
            premier_retard = op.echeances.filter(
                paye=False,
                date_echeance__lt=today
            ).order_by('date_echeance').first()
            
            if premier_retard:
                op.premier_retard = premier_retard
                op.jours_retard = (today - premier_retard.date_echeance).days

    elif filtre == 'non_planifies':
        operations = operations.filter(id__in=operations_sans_echeances_ids)
        
        for op in operations:
            total_planifie = op.echeances.aggregate(
                total=Sum('montant')
            )['total'] or 0
            
            op.reste_a_planifier = op.montant_total - total_planifie

    elif filtre == 'toutes':
        pass

    else:
        # Pour les autres filtres standards (statut)
        operations = operations.filter(statut=filtre)
    
    # Recherche
    if recherche:
        operations = operations.filter(
            Q(client__nom__icontains=recherche) |
            Q(client__prenom__icontains=recherche) |
            Q(type_prestation__icontains=recherche) |
            Q(client__ville__icontains=recherche) |
            Q(client__telephone__icontains=recherche) |
            Q(id_operation__icontains=recherche)
        )
    
    operations = operations.order_by('-date_creation')
    
    # ========================================
    # COMPTEURS (SUR LA PÉRIODE)
    # ========================================
    all_operations_periode = Operation.objects.filter(
        user=request.user
    ).filter(
        Q(date_realisation__gte=periode_start, date_realisation__lte=periode_end) |
        Q(date_prevue__gte=periode_start, date_prevue__lte=periode_end) |
        Q(date_creation__gte=periode_start, date_creation__lte=periode_end)
    )
    
    nb_total = all_operations_periode.count()
    nb_en_attente_devis = all_operations_periode.filter(statut='en_attente_devis').count()
    nb_a_planifier = all_operations_periode.filter(statut='a_planifier').count()
    nb_planifie = all_operations_periode.filter(statut='planifie').count()
    nb_realise = all_operations_periode.filter(statut='realise').count()
    nb_paye = all_operations_periode.filter(statut='paye').count()
    nb_refuse = all_operations_periode.filter(statut='devis_refuse').count()

    # ✅ Compteur "À traiter" basé sur PassageOperation
    now = timezone.now()
    passages_en_retard_ids = PassageOperation.objects.filter(
        operation__user=request.user,
        date_prevue__lt=now,
        realise=False
    ).values_list('operation_id', flat=True).distinct()

    nb_a_traiter = len(set(passages_en_retard_ids))

    # ========================================
    # NOUVEAUX COMPTEURS DEVIS (KPI)
    # ========================================

    # 1️⃣ BROUILLON : Devis commencé mais pas généré
    nb_devis_brouillon = Devis.objects.filter(
        operation__user=request.user,
        statut='brouillon'
    ).count()

    # ✅ CORRECTION : Devis "prêt" = généré mais pas encore envoyé
    nb_devis_genere_non_envoye = Devis.objects.filter(
        operation__user=request.user,
        statut='pret'  # ← Statut "prêt" = PDF généré, en attente d'envoi
    ).count()
    
    # ✅ NOUVEAU : Opérations avec_devis=True mais sans aucun devis créé
    nb_sans_devis = Operation.objects.filter(
        user=request.user,
        avec_devis=True
    ).annotate(
        nb_devis=Count('devis_set')  # ← CORRECTION : utiliser 'devis_set'
    ).filter(nb_devis=0).count()

    # ✅ NOUVEAU (version simple)
    nb_devis_expire = 0
    for op in Operation.objects.filter(user=request.user, avec_devis=True):
        for devis in op.devis_set.filter(statut='envoye'):
            if devis.est_expire:
                nb_devis_expire += 1

    # ✅ NOUVEAU
    nb_devis_en_attente = 0
    for op in Operation.objects.filter(user=request.user, avec_devis=True):
        for devis in op.devis_set.filter(statut='envoye', date_envoi__isnull=False):
            if not devis.est_expire:
                nb_devis_en_attente += 1
    
    # Options de cycle pour les boutons
    cycle_options = [
        ('toutes', 'Toutes'),
        ('en_attente_devis', 'Devis'),
        ('a_planifier', 'À planifier'),
    ]


    context = {
        'operations': operations,
        'total_operations': operations.count(),
        'filtre_actif': filtre,
        'recherche': recherche,
        
        # Période
        'periode': periode,
        'periode_start': periode_start,
        'periode_end': periode_end,
        
        # Financier
        'ca_encaisse': ca_encaisse,
        'ca_encaisse_var': ca_encaisse_var,
        'ca_en_attente_total': ca_en_attente_total,
        'ca_retard': ca_retard,
        'ca_non_planifies': ca_non_planifies,
        'ca_previsionnel_30j': ca_previsionnel_30j,
        
        # Compteurs
        'nb_total': nb_total,
        'nb_en_attente_devis': nb_en_attente_devis,
        'nb_a_planifier': nb_a_planifier,
        'nb_planifie': nb_planifie,
        'nb_a_traiter': nb_a_traiter, 
        'nb_realise': nb_realise,
        'nb_paiements_retard': nb_paiements_retard,
        'nb_operations_sans_paiement': nb_operations_sans_paiement,
        'nb_paye': nb_paye,
        'nb_refuse': nb_refuse,
        
        # ✅ NOUVEAUX COMPTEURS DEVIS
        'nb_devis_brouillon': nb_devis_brouillon,
        'nb_devis_genere_non_envoye': nb_devis_genere_non_envoye,
        'nb_devis_en_attente': nb_devis_en_attente,
        'nb_devis_expire': nb_devis_expire,
        'nb_sans_devis': nb_sans_devis,
        
        # Options
        'cycle_options': cycle_options,
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
                devis.date_reponse = datetime.now().date()
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
                devis.date_reponse = datetime.now().date()
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
            
            if montant_str and date_paiement_str:
                try:
                    
                    
                    montant = Decimal(montant_str)  # ✅ CORRECTION
                    date_paiement = datetime.strptime(date_paiement_str, '%Y-%m-%d').date()
                    paye = (paye_str == 'true')
                    
                    # ✅ VÉRIFICATION : Calculer le total avec ce nouveau paiement
                    total_actuel_tout = operation.echeances.aggregate(
                        total=Sum('montant')
                    )['total'] or 0
                    
                    # Total si on ajoute ce paiement
                    nouveau_total = total_actuel_tout + montant
                    
                    # Vérifier le dépassement
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
                    
                    Echeance.objects.create(
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
                    
                    # Vérifier si tout est payé
                    total_paye = operation.echeances.filter(paye=True).aggregate(
                        total=Sum('montant')
                    )['total'] or 0
                    
                    if total_paye >= operation.montant_total:
                        operation.statut = 'paye'
                        operation.save()
                        messages.success(request, f"✅ Paiement enregistré - Opération soldée ! 🎉")
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
                
                # Vérifier si tout est payé
                total_paye = operation.echeances.filter(paye=True).aggregate(
                    total=Sum('montant')
                )['total'] or 0
                
                if total_paye >= operation.montant_total:
                    operation.statut = 'paye'
                    operation.save()
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"✅ Paiement de {echeance.montant}€ confirmé - Opération soldée ! 🎉",
                        utilisateur=request.user
                    )
                    messages.success(request, "🎉 Opération soldée !")
                else:
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"✅ Paiement de {echeance.montant}€ marqué comme reçu",
                        utilisateur=request.user
                    )
                    messages.success(request, f"✅ Paiement de {echeance.montant}€ confirmé")
                    
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
                annee_courante = datetime.now().year
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
                    # Passage vide (à planifier plus tard)
                    PassageOperation.objects.create(
                        operation=operation,
                        date_prevue=None,
                        realise=False
                    )
                    print(f"✓ Passage créé (à planifier)")

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
            messages.success(request, f'Compte créé pour {username}!')
            login(request, user)  # Connexion automatique
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def simple_logout(request):
    if request.user.is_authenticated:
        logout(request)
    return redirect('/login/')

def run_migration(request):
    """Vue temporaire pour exécuter les migrations"""
    try:
        # Capturer la sortie
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        
        call_command('migrate', verbosity=2)
        
        # Restaurer stdout
        sys.stdout = old_stdout
        output = buffer.getvalue()
        
        return HttpResponse(f"<pre>Migration exécutée:\n{output}</pre>")
    except Exception as e:
        sys.stdout = old_stdout
        return HttpResponse(f"<pre>Erreur migration: {str(e)}</pre>")
    

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
        
        # Créer le passage
        passage = PassageOperation.objects.create(
            operation=operation,
            commentaire=commentaire
        )
        
        # Si une date est fournie, l'assigner
        if date_prevue_str:
            try:
                date_prevue = datetime.fromisoformat(date_prevue_str)
                passage.date_prevue = date_prevue
                passage.save()
                
                # ✅ NOUVEAU : Mettre à jour le statut de l'opération
                if operation.statut in ['en_attente_devis', 'a_planifier']:
                    operation.statut = 'planifie'
                    operation.save()
                    print(f"✓ Statut opération mis à jour : {operation.statut}")
                
                messages.success(
                    request,
                    f"✅ Passage {passage.numero} planifié le {date_prevue.strftime('%d/%m/%Y à %H:%M')}"
                )
            except ValueError:
                messages.success(request, f"✅ Passage {passage.numero} créé (à planifier)")
        else:
            messages.success(request, f"✅ Passage {passage.numero} créé (à planifier)")
        
        # Historique
        HistoriqueOperation.objects.create(
            operation=operation,
            utilisateur=request.user,
            action=f"Passage {passage.numero} ajouté" + (f" - Planifié le {date_prevue.strftime('%d/%m/%Y %H:%M')}" if date_prevue_str else " (à planifier)")
        )
    
    return redirect('operation_detail', operation_id=operation.id)

@login_required
def planifier_passage_operation(request, operation_id, passage_id):
    """
    Planifie ou modifie la date d'un passage
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        date_prevue_str = request.POST.get('date_prevue')
        
        if date_prevue_str:
            try:
                from datetime import datetime
                date_prevue = datetime.fromisoformat(date_prevue_str)
                
                passage.date_prevue = date_prevue
                passage.save()
                
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
def marquer_passage_realise(request, operation_id, passage_id):
    """
    Marque un passage comme réalisé (ou inverse)
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        # Basculer l'état
        passage.realise = not passage.realise
        passage.save()  # Le save() gère automatiquement date_realisation
        
        if passage.realise:
            messages.success(request, f"✅ Passage {passage.numero} marqué comme réalisé")
            action = f"Passage {passage.numero} réalisé"
        else:
            messages.info(request, f"ℹ️ Passage {passage.numero} marqué comme non réalisé")
            action = f"Passage {passage.numero} marqué comme non réalisé"
        
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
    Planifie ou modifie la date d'un passage
    """
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    passage = get_object_or_404(PassageOperation, id=passage_id, operation=operation)
    
    if request.method == 'POST':
        date_prevue_str = request.POST.get('date_prevue')
        
        if date_prevue_str:
            try:
                from datetime import datetime
                date_prevue = datetime.fromisoformat(date_prevue_str)
                
                passage.date_prevue = date_prevue
                passage.save()
                
                # ✅ NOUVEAU : Mettre à jour le statut de l'opération
                if operation.statut in ['en_attente_devis', 'a_planifier']:
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
                
            except ValueError:
                messages.error(request, "❌ Format de date invalide")
        else:
            messages.error(request, "❌ Veuillez saisir une date")
    
    return redirect('operation_detail', operation_id=operation.id)