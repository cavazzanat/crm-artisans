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
        
        # CA du mois (exemple)
        from django.utils import timezone
        from django.db.models import Sum
        debut_mois = timezone.now().replace(day=1)
        ca_mois = Operation.objects.filter(
            user=request.user, 
            statut='paye',
            date_creation__gte=debut_mois
        ).aggregate(total=Sum('interventions__montant'))['total'] or 0
        
        # Prochaines opérations planifiées
        prochaines_operations = Operation.objects.filter(
            user=request.user,
            statut='planifie',
            date_prevue__isnull=False
        ).select_related('client').order_by('date_prevue')[:5]
        
        context = {
            'nb_clients': nb_clients,
            'nb_operations': nb_operations,
            'nb_en_attente_devis': nb_en_attente_devis,
            'nb_a_planifier': nb_a_planifier,
            'nb_realise': nb_realise,
            'ca_mois': ca_mois,
            'prochaines_operations': prochaines_operations,
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
    
    # Changement de statut via POST
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'change_status':
            nouveau_statut = request.POST.get('statut')
            if nouveau_statut in dict(Operation.STATUTS):
                ancien_statut = operation.get_statut_display()
                operation.statut = nouveau_statut
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
            description = request.POST.get('description')
            montant = request.POST.get('montant')
            
            if description and montant:
                try:
                    # Calculer l'ordre (dernier + 1)
                    last_order = operation.interventions.aggregate(
                        max_order=Max('ordre')
                    )['max_order'] or 0
                    
                    Intervention.objects.create(
                        operation=operation,
                        description=description,
                        montant=float(montant),
                        ordre=last_order + 1
                    )
                    
                    # Ajouter à l'historique
                    HistoriqueOperation.objects.create(
                        operation=operation,
                        action=f"Intervention ajoutée : {description} ({montant}€)",
                        utilisateur=request.user
                    )
                    
                    messages.success(request, "Intervention ajoutée avec succès")
                except ValueError:
                    messages.error(request, "Montant invalide")
                
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
                
                # Ajouter à l'historique
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
            prochaine_operation = operations.filter(
                statut='planifie',
                date_prevue__gte=timezone.now()
            ).order_by('date_prevue').first()
            
            client.derniere_op = derniere_operation
            client.prochaine_op = prochaine_operation
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
        date_prevue = request.POST.get('date_prevue', '')
        heure_prevue = request.POST.get('heure_prevue', '')
        statut = request.POST.get('statut', 'en_attente_devis')
        
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
            
            # Créer l'opération
            date_prevue_complete = None
            if date_prevue:
                from datetime import datetime, time
                if heure_prevue:
                    try:
                        heure = datetime.strptime(heure_prevue, '%H:%M').time()
                        date_prevue_complete = datetime.combine(
                            datetime.strptime(date_prevue, '%Y-%m-%d').date(),
                            heure
                        )
                    except ValueError:
                        pass
                else:
                    date_prevue_complete = datetime.strptime(date_prevue, '%Y-%m-%d')
            
            operation = Operation.objects.create(
                user=request.user,
                client=client,
                type_prestation=type_prestation,
                adresse_intervention=adresse_intervention or f"{client.adresse}, {client.ville}",
                date_prevue=date_prevue_complete,
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
    logout(request)
    return redirect('/login/')