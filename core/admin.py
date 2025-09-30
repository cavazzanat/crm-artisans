from django.contrib import admin
from .models import Client, Operation, Intervention, HistoriqueOperation, Echeance

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['id_client', 'nom', 'prenom', 'ville', 'telephone', 'date_creation']
    list_filter = ['ville', 'date_creation']
    search_fields = ['nom', 'prenom', 'telephone', 'email']
    readonly_fields = ['id_client', 'date_creation']

class InterventionInline(admin.TabularInline):
    model = Intervention
    extra = 1
    fields = ['description', 'montant', 'ordre']

class EcheanceInline(admin.TabularInline):
    model = Echeance
    extra = 1
    fields = ['numero', 'montant', 'date_echeance', 'date_paiement', 'statut', 'ordre']

@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ['id_operation', 'client', 'type_prestation', 'statut', 'mode_paiement', 'date_prevue']
    list_filter = ['statut', 'mode_paiement', 'devis_statut', 'date_creation']
    search_fields = ['id_operation', 'client__nom', 'type_prestation']
    readonly_fields = ['id_operation', 'date_creation', 'date_modification']
    inlines = [InterventionInline, EcheanceInline]
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('id_operation', 'user', 'client', 'type_prestation', 'adresse_intervention', 'statut')
        }),
        ('Dates', {
            'fields': ('date_prevue', 'date_realisation', 'date_paiement', 'date_creation', 'date_modification')
        }),
        ('Devis', {
            'fields': ('devis_cree', 'devis_date_envoi', 'devis_statut'),
            'classes': ('collapse',)
        }),
        ('Paiement', {
            'fields': ('mode_paiement',),
        }),
    )

@admin.register(Echeance)
class EcheanceAdmin(admin.ModelAdmin):
    list_display = ['operation', 'numero', 'montant', 'date_echeance', 'date_paiement', 'statut']
    list_filter = ['statut', 'date_echeance']
    search_fields = ['operation__id_operation', 'operation__client__nom']
    ordering = ['operation', 'ordre']

@admin.register(HistoriqueOperation)
class HistoriqueOperationAdmin(admin.ModelAdmin):
    list_display = ['operation', 'action', 'utilisateur', 'date']
    list_filter = ['date', 'utilisateur']
    readonly_fields = ['date']