from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Opérations
    path('operations/', views.operations_list, name='operations'),
    path('operations/nouvelle/', views.operation_create, name='operation_create'),
    path('operations/<int:operation_id>/', views.operation_detail, name='operation_detail'),
    path('operations/<int:operation_id>/modifier/', views.operation_edit, name='operation_edit'),
    path('operations/<int:operation_id>/delete/', views.operation_delete, name='operation_delete'),
    path('operations/<int:operation_id>/duplicate/', views.operation_duplicate, name='operation_duplicate'),
    
    # Documents PDF
    path('devis/<int:devis_id>/pdf/', views.telecharger_devis_pdf, name='telecharger_devis_pdf'),
    path('factures/<int:echeance_id>/pdf/', views.telecharger_facture_pdf, name='telecharger_facture_pdf'),
    
    # Clients
    path('clients/', views.clients_list, name='clients'),
    path('clients/nouveau/', views.client_create, name='client_create'),
    path('clients/<int:client_id>/', views.client_detail, name='client_detail'),
    path('clients/<int:client_id>/modifier/', views.client_edit, name='client_edit'),
    path('clients/<int:client_id>/supprimer/', views.client_delete, name='client_delete'),
    
    # Profil entreprise
    path('profil/', views.profil_entreprise, name='profil'),
    
    # Authentification
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('register/', views.register, name='register'),
    
    path('operations/<int:operation_id>/ajax/add-ligne-devis/', views.ajax_add_ligne_devis, name='ajax_add_ligne_devis'),
    path('operations/<int:operation_id>/ajax/delete-ligne-devis/', views.ajax_delete_ligne_devis, name='ajax_delete_ligne_devis'),
    
    # Utilitaires
    path('run-migration/', views.run_migration, name='run_migration'),
    
    # ✅ ROUTES POUR INTERVENTIONS MULTIPLES
    path('operation/<int:operation_id>/intervention/<int:intervention_id>/planifier/', 
        views.planifier_intervention, name='planifier_intervention'),
    path('operation/<int:operation_id>/intervention/<int:intervention_id>/marquer-realise/', 
        views.marquer_realise, name='marquer_realise'),
    path('operation/<int:operation_id>/intervention/<int:intervention_id>/commentaire/', 
        views.ajouter_commentaire, name='ajouter_commentaire'),
    path('operation/<int:operation_id>/intervention/<int:intervention_id>/supprimer/', 
        views.supprimer_intervention, name='supprimer_intervention'),
    path('operation/<int:operation_id>/intervention/creer/', 
        views.creer_nouvelle_intervention, name='creer_nouvelle_intervention'),
    
    # Dans urls.py
    path('operations/<int:operation_id>/passages/ajouter/', views.ajouter_passage_operation, name='ajouter_passage_operation'),
    path('operations/<int:operation_id>/passages/<int:passage_id>/planifier/', views.planifier_passage_operation, name='planifier_passage_operation'),
    path('operations/<int:operation_id>/passages/<int:passage_id>/realise/', views.marquer_passage_realise, name='marquer_passage_realise'),
    path('operations/<int:operation_id>/passages/<int:passage_id>/supprimer/', views.supprimer_passage_operation, name='supprimer_passage_operation'),
    path('operations/<int:operation_id>/passages/<int:passage_id>/commentaire/', views.ajouter_commentaire_passage, name='ajouter_commentaire_passage'),
]