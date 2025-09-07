from django.contrib import admin
from .models import Client, Operation, Intervention, HistoriqueOperation

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['id_client', 'nom', 'prenom', 'ville', 'telephone', 'date_creation']
    list_filter = ['ville', 'date_creation']
    search_fields = ['nom', 'prenom', 'telephone', 'email']
    readonly_fields = ['id_client', 'date_creation']

class InterventionInline(admin.TabularInline):
    model = Intervention
    extra = 1

@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ['id_operation', 'client', 'type_prestation', 'statut', 'date_prevue']
    list_filter = ['statut', 'date_creation']
    search_fields = ['id_operation', 'client__nom', 'type_prestation']
    readonly_fields = ['id_operation', 'date_creation', 'date_modification']
    inlines = [InterventionInline]

@admin.register(HistoriqueOperation)
class HistoriqueOperationAdmin(admin.ModelAdmin):
    list_display = ['operation', 'action', 'utilisateur', 'date']
    list_filter = ['date', 'utilisateur']
    readonly_fields = ['date']