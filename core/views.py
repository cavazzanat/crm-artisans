# ================================
# core/views.py - Version complète et corrigée
# ================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Q, Max
from django.db import models
from django.contrib import messages
from .models import Client, Operation, Intervention, HistoriqueOperation
from .fix_database import fix_client_constraint
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout  # ← Ajoutez logout

from django.core.management import call_command
from django.http import HttpResponse
import io
import sys
import json


# Dans core/views.py, remplacez la section du dashboard par :
# Dans core/views.py, remplacez la section du dashboard par :
# Dans core/views.py, remplacez la section du dashboard par :

@login_required
def dashboard(request):
    fix_client_constraint()
    try:
        # KPI
        nb_clients = Client.objects.filter(user=request.user).count()
        nb_operations = Operation.objects.filter(user=request.user).count()
        nb_en_attente_devis = Operation.objects.filter(user=request.user, statut='en_attente_devis').count()
        nb_a_planifier = Operation.objects.filter(user=request.user, statut='a_planifier').count()
        nb_realise = Operation.objects.filter(user=request.user, statut='realise').count()
        
        # CA du mois
        from django.utils import timezone
        from django.db.models import Sum
        debut_mois = timezone.now().replace(day=1)
        ca_mois = Operation.objects.filter(
            user=request.user, 
            statut='paye',
            date_creation__gte=debut_mois
        ).aggregate(total=Sum('interventions__montant'))['total'] or 0
        
        # ✅ CALENDRIER : Logique simplifiée pour les opérations qui nécessitent attention
        from datetime import timedelta
        
        today = timezone.now().date()
        start_date = today - timedelta(days=30)  # 30 jours passés
        end_date = today + timedelta(days=14)    # 14 jours futurs
        
        operations_calendrier = Operation.objects.filter(
            user=request.user,
            date_prevue__isnull=False,
            date_prevue__gte=start_date,
            date_prevue__lte=end_date
        ).filter(
            # Seulement les statuts qui nécessitent attention
            statut__in=['planifie', 'a_planifier']
        ).select_related('client').order_by('date_prevue')
        
        # ✅ TABLEAU : opérations à planifier (remplace prochaines_operations)
        operations_a_planifier = Operation.objects.filter(
            user=request.user,
            statut__in=['en_attente_devis', 'a_planifier']
        ).select_related('client').order_by('-date_creation')[:5]
        
        # ✅ FORMATER avec logique d'alerte pour le calendrier
        calendar_events = []
        for op in operations_calendrier:
            is_past = op.date_prevue < timezone.now()
            
            if op.statut == 'planifie':
                if is_past:
                    color_class = 'event-attention'  # Rouge clignotant
                    status_text = "À valider"
                else:
                    color_class = 'event-planifie'   # Vert
                    status_text = op.get_statut_display()
            elif op.statut == 'a_planifier':
                color_class = 'event-pending'        # Gris
                status_text = "À replanifier"
            else:
                color_class = 'event-default'
                status_text = op.get_statut_display()
            
            calendar_events.append({
                'id': op.id,
                'client_nom': f"{op.client.nom} {op.client.prenom}",
                'service': op.type_prestation,
                'date': op.date_prevue.strftime('%Y-%m-%d'),
                'time': op.date_prevue.strftime('%H:%M'),
                'address': op.adresse_intervention,
                'phone': op.client.telephone,
                'url': f'/operations/{op.id}/',
                'statut': op.statut,
                'statut_display': status_text,
                'color_class': color_class,
                'is_past': is_past
            })
        
        context = {
            'nb_clients': nb_clients,
            'nb_operations': nb_operations,
            'nb_en_attente_devis': nb_en_attente_devis,
            'nb_a_planifier': nb_a_planifier,
            'nb_realise': nb_realise,
            'ca_mois': ca_mois,
            'operations_a_planifier': operations_a_planifier,  # ← Changé
            'calendar_events_json': json.dumps(calendar_events),
            'calendar_events': calendar_events,
        }
        
        return render(request, 'core/dashboard.html', context)
        
    except Exception as e:
        return HttpResponse(f"<h1>CRM Artisans</h1><p>Erreur : {str(e)}</p><p><a href='/admin/'>Admin</a></p>")
    
@login_required
def operations_list(request):
    """Page de gestion des opérations avec filtres"""
    
    # Récupérer toutes les opérations de l'utilisateur
    operations = Operation.objects.filter(user=request.user).select_related('client')
    
    # Filtres
    statut_filtre = request.GET.get('statut', '')
    ville_filtre = request.GET.get('ville', '')
    recherche = request.GET.get('recherche', '')
    tri = request.GET.get('tri', '-date_creation')
    
    # Appliquer les filtres
    if statut_filtre:
        operations = operations.filter(statut=statut_filtre)
    
    if ville_filtre:
        operations = operations.filter(client__ville__icontains=ville_filtre)
    
    if recherche:
        operations = operations.filter(
            Q(client__nom__icontains=recherche) |
            Q(client__prenom__icontains=recherche) |
            Q(type_prestation__icontains=recherche) |
            Q(client__ville__icontains=recherche) |
            Q(client__telephone__icontains=recherche) |
            Q(adresse_intervention__icontains=recherche)
        )
    
    # Tri
    if tri == 'date_prochaine_asc':
        operations = operations.order_by('date_prevue')
    elif tri == 'date_prochaine_desc':
        operations = operations.order_by('-date_prevue')
    else:
        operations = operations.order_by('-date_creation')
    
    # Statistiques pour le titre
    total_operations = operations.count()
    
    # Choix pour les filtres
    statuts_choices = Operation.STATUTS
    villes = Client.objects.filter(user=request.user).values_list('ville', flat=True).distinct()
    
    context = {
        'operations': operations,
        'total_operations': total_operations,
        'statut_filtre': statut_filtre,
        'ville_filtre': ville_filtre,
        'recherche': recherche,
        'tri': tri,
        'statuts_choices': statuts_choices,
        'villes': villes,
    }
    
    return render(request, 'operations/list.html', context)

@login_required
def operation_detail(request, operation_id):
    """Fiche détaillée d'une opération avec gestion complète"""
    operation = get_object_or_404(Operation, id=operation_id, user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'change_status':
            nouveau_statut = request.POST.get('statut')
            date_prevue_str = request.POST.get('date_prevue', '')
            date_realisation_str = request.POST.get('date_realisation', '')
            date_paiement_str = request.POST.get('date_paiement', '')
            
            if nouveau_statut in dict(Operation.STATUTS):
                ancien_statut = operation.get_statut_display()
                operation.statut = nouveau_statut
                
                # Gérer les dates selon le statut
                from datetime import datetime
                
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
                
                # Ajouter à l'historique
                HistoriqueOperation.objects.create(
                    operation=operation,
                    action=f"Statut changé : {ancien_statut} → {operation.get_statut_display()}",
                    utilisateur=request.user
                )
                
                messages.success(request, f"Statut mis à jour : {operation.get_statut_display()}")
                return redirect('operation_detail', operation_id=operation.id)

        elif action == 'add_intervention':
            description = request.POST.get('description', '').strip()
            montant_str = request.POST.get('montant', '').strip()
            
            if description and montant_str:
                try:
                    montant = float(montant_str)
                    
                    # Déterminer l'ordre
                    dernier_ordre = operation.interventions.aggregate(
                        max_ordre=Max('ordre')
                    )['max_ordre'] or 0
                    
                    Intervention.objects.create(
                        operation=operation,
                        description=description,
                        montant=montant,
                        ordre=dernier_ordre + 1
                    )
                    
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"Intervention ajoutée : {description} ({montant}€)",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, "Intervention ajoutée avec succès")
                    
                except ValueError:
                    messages.error(request, "Montant invalide")
            else:
                messages.error(request, "Description et montant obligatoires")
            
            return redirect('operation_detail', operation_id=operation.id)

        elif action == 'delete_intervention':
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
                    action=f"Intervention supprimée : {description}",
                    utilisateur=request.user
                )
                
                messages.success(request, "Intervention supprimée")
                
            except Intervention.DoesNotExist:
                messages.error(request, "Intervention introuvable")
            
            return redirect('operation_detail', operation_id=operation.id)
        
    # Récupérer les données pour l'affichage
    interventions = operation.interventions.all()
    historique = operation.historique.all()[:10]  # 10 dernières actions
    
    context = {
        'operation': operation,
        'interventions': interventions,
        'historique': historique,
        'statuts_choices': Operation.STATUTS,
        'montant_total': operation.montant_total,
    }
    
    return render(request, 'operations/detail.html', context)


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
    """Formulaire de création d'une nouvelle opération"""
    if request.method == 'POST':
        # Récupération des données du formulaire
        client_id = request.POST.get('client_id')
        nouveau_client_nom = request.POST.get('nouveau_client_nom', '').strip()
        nouveau_client_prenom = request.POST.get('nouveau_client_prenom', '').strip()
        nouveau_client_email = request.POST.get('nouveau_client_email', '').strip()
        nouveau_client_telephone = request.POST.get('nouveau_client_telephone', '').strip()
        nouveau_client_adresse = request.POST.get('nouveau_client_adresse', '').strip()
        nouveau_client_ville = request.POST.get('nouveau_client_ville', '').strip()
        
        type_prestation = request.POST.get('type_prestation', '').strip()
        adresse_intervention = request.POST.get('adresse_intervention', '').strip()
        statut = request.POST.get('statut', 'en_attente_devis')
        
        # NOUVEAU : Gestion des dates selon le statut
        date_prevue_str = request.POST.get('date_prevue', '')
        date_realisation_str = request.POST.get('date_realisation', '')
        
        # Interventions (lignes du devis)
        descriptions = request.POST.getlist('description[]')
        montants = request.POST.getlist('montant[]')
        
        try:
            # Déterminer le client
            if client_id and client_id != 'nouveau':
                client = get_object_or_404(Client, id=client_id, user=request.user)
            else:
                # Créer un nouveau client
                if not (nouveau_client_nom and nouveau_client_prenom and nouveau_client_telephone):
                    messages.error(request, "Nom, prénom et téléphone sont obligatoires pour un nouveau client")
                    return redirect('operation_create')
                
                client = Client.objects.create(
                    user=request.user,
                    nom=nouveau_client_nom,
                    prenom=nouveau_client_prenom,
                    email=nouveau_client_email,
                    telephone=nouveau_client_telephone,
                    adresse=nouveau_client_adresse,
                    ville=nouveau_client_ville
                )
            
            # Dans operation_create, remplacez la section "NOUVELLE LOGIQUE" par :

            # LOGIQUE A 3 DATES : Traitement selon le statut
            from datetime import datetime
            date_prevue_complete = None
            date_realisation_complete = None
            date_paiement_complete = None

            if statut == 'planifie' and date_prevue_str:
                # Statut planifié : utiliser date_prevue
                try:
                    date_prevue_complete = datetime.fromisoformat(date_prevue_str.replace('T', ' '))
                except ValueError:
                    pass

            elif statut == 'realise':
                # Statut réalisé : utiliser date_realisation
                date_realisation_str = request.POST.get('date_realisation', '')
                if date_realisation_str:
                    try:
                        date_realisation_complete = datetime.fromisoformat(date_realisation_str.replace('T', ' '))
                    except ValueError:
                        pass

            elif statut == 'paye':
                # Statut payé : récupérer les 2 dates (réalisation + paiement)
                date_realisation_str = request.POST.get('date_realisation', '')
                date_paiement_str = request.POST.get('date_paiement', '')
                
                if date_realisation_str:
                    try:
                        date_realisation_complete = datetime.fromisoformat(date_realisation_str.replace('T', ' '))
                    except ValueError:
                        pass
                        
                if date_paiement_str:
                    try:
                        date_paiement_complete = datetime.fromisoformat(date_paiement_str.replace('T', ' '))
                    except ValueError:
                        pass
            
            # Créer l'opération
            # Remplacez la partie création d'opération par :
            operation = Operation.objects.create(
                user=request.user,
                client=client,
                type_prestation=type_prestation,
                adresse_intervention=adresse_intervention or f"{client.adresse}, {client.ville}",
                date_prevue=date_prevue_complete,
                date_realisation=date_realisation_complete,  # À décommenter après migration
                date_paiement=date_paiement_complete,        # À décommenter après migration
                statut=statut
            )
            
            # Créer les interventions
            for i, (description, montant) in enumerate(zip(descriptions, montants)):
                if description.strip() and montant.strip():
                    try:
                        Intervention.objects.create(
                            operation=operation,
                            description=description.strip(),
                            montant=float(montant),
                            ordre=i + 1
                        )
                    except ValueError:
                        pass  # Ignorer les montants invalides
            
            # Ajouter à l'historique
            HistoriqueOperation.objects.create(
                operation=operation,
                action="Opération créée",
                utilisateur=request.user
            )
            
            messages.success(request, f"Opération {operation.id_operation} créée avec succès")
            return redirect('operation_detail', operation_id=operation.id)
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la création : {str(e)}")
    
    # GET - Afficher le formulaire
    clients = Client.objects.filter(user=request.user).order_by('nom', 'prenom')
    
    context = {
        'clients': clients,
        'statuts_choices': Operation.STATUTS,
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