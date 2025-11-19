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
]