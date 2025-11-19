from django.contrib import admin
from .models import (
    Client, 
    Operation, 
    Devis,
    LigneDevis,
    Intervention, 
    HistoriqueOperation, 
    Echeance,
    ProfilEntreprise
)

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['id_client', 'nom', 'prenom', 'ville', 'telephone', 'date_creation']
    list_filter = ['ville', 'date_creation']
    search_fields = ['nom', 'prenom', 'telephone', 'email']
    readonly_fields = ['id_client', 'date_creation']


# ========================================
# NOUVEAUX INLINES POUR DEVIS
# ========================================
class LigneDevisInline(admin.TabularInline):
    model = LigneDevis
    extra = 1
    fields = ['description', 'quantite', 'unite', 'prix_unitaire_ht', 'taux_tva', 'montant', 'ordre']
    readonly_fields = ['montant']


class DevisInline(admin.TabularInline):
    model = Devis
    extra = 0
    fields = ['numero_devis', 'version', 'statut', 'date_envoi', 'date_reponse']
    readonly_fields = ['numero_devis', 'version']
    can_delete = False
    show_change_link = True  # Lien pour éditer le devis en détail


# ========================================
# INLINES EXISTANTS (CONSERVÉS)
# ========================================
class InterventionInline(admin.TabularInline):
    model = Intervention
    extra = 1
    fields = ['description', 'quantite', 'unite', 'prix_unitaire_ht', 'taux_tva', 'montant', 'ordre']
    readonly_fields = ['montant']


class EcheanceInline(admin.TabularInline):
    model = Echeance
    extra = 1
    fields = ['numero', 'montant', 'date_echeance', 'paye', 'facture_generee', 'numero_facture', 'ordre']
    readonly_fields = ['facture_generee', 'numero_facture']


# ========================================
# ADMIN OPERATION (REFACTORISÉ)
# ========================================
@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ['id_operation', 'client', 'type_prestation', 'statut', 'avec_devis', 'mode_paiement', 'date_prevue']
    list_filter = ['statut', 'avec_devis', 'mode_paiement', 'date_creation']
    search_fields = ['id_operation', 'client__nom', 'type_prestation']
    readonly_fields = ['id_operation', 'date_creation', 'date_modification']
    
    # Afficher les inlines selon le type d'opération
    def get_inlines(self, request, obj=None):
        if obj and obj.avec_devis:
            # Opération avec devis : afficher les devis
            return [DevisInline, EcheanceInline]
        else:
            # Opération sans devis : afficher les interventions
            return [InterventionInline, EcheanceInline]
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('id_operation', 'user', 'client', 'type_prestation', 'adresse_intervention', 'statut', 'avec_devis')
        }),
        ('Dates', {
            'fields': ('date_prevue', 'date_realisation', 'date_paiement', 'date_creation', 'date_modification')
        }),
        ('Paiement', {
            'fields': ('mode_paiement',),
        }),
        ('Commentaires', {
            'fields': ('commentaires',),
            'classes': ('collapse',)
        }),
    )


# ========================================
# ADMIN DEVIS (NOUVEAU)
# ========================================
@admin.register(Devis)
class DevisAdmin(admin.ModelAdmin):
    list_display = ['numero_devis', 'version', 'operation', 'statut', 'date_creation', 'date_envoi', 'sous_total_ht', 'total_ttc']
    list_filter = ['statut', 'operation__user', 'date_creation']
    search_fields = ['numero_devis', 'operation__id_operation', 'operation__client__nom']
    readonly_fields = ['numero_devis', 'version', 'date_creation', 'sous_total_ht', 'total_tva', 'total_ttc']
    inlines = [LigneDevisInline]
    
    fieldsets = (
        ('Identification', {
            'fields': ('numero_devis', 'version', 'operation', 'date_creation')
        }),
        ('Statut et dates', {
            'fields': ('statut', 'date_envoi', 'date_reponse', 'validite_jours')
        }),
        ('Contenu', {
            'fields': ('notes',)
        }),
        ('Totaux (calculés)', {
            'fields': ('sous_total_ht', 'total_tva', 'total_ttc'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        """Verrouiller les champs si le devis n'est plus en brouillon"""
        readonly = list(self.readonly_fields)
        if obj and obj.est_verrouille:
            readonly.extend(['operation', 'notes', 'validite_jours'])
        return readonly


# ========================================
# ADMIN LIGNE DEVIS (NOUVEAU)
# ========================================
@admin.register(LigneDevis)
class LigneDevisAdmin(admin.ModelAdmin):
    list_display = ['devis', 'description', 'quantite', 'unite', 'prix_unitaire_ht', 'taux_tva', 'montant', 'montant_ttc']
    list_filter = ['devis__statut', 'devis__operation__user']
    search_fields = ['description', 'devis__numero_devis']
    readonly_fields = ['montant', 'montant_tva', 'montant_ttc']


# ========================================
# ADMIN INTERVENTION (CONSERVÉ)
# ========================================
@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ['operation', 'description', 'quantite', 'unite', 'prix_unitaire_ht', 'montant', 'montant_ttc']
    list_filter = ['operation__user']
    search_fields = ['description', 'operation__id_operation']
    readonly_fields = ['montant', 'montant_tva', 'montant_ttc']


# ========================================
# ADMIN ECHEANCE (CONSERVÉ)
# ========================================
@admin.register(Echeance)
class EcheanceAdmin(admin.ModelAdmin):
    list_display = ['operation', 'numero', 'montant', 'date_echeance', 'paye', 'facture_generee', 'numero_facture']
    list_filter = ['paye', 'facture_generee', 'date_echeance']
    search_fields = ['operation__id_operation', 'operation__client__nom', 'numero_facture']
    ordering = ['operation', 'ordre']
    readonly_fields = ['facture_generee', 'numero_facture', 'facture_date_emission']


# ========================================
# ADMIN HISTORIQUE (CONSERVÉ)
# ========================================
@admin.register(HistoriqueOperation)
class HistoriqueOperationAdmin(admin.ModelAdmin):
    list_display = ['operation', 'action', 'utilisateur', 'date']
    list_filter = ['date', 'utilisateur']
    readonly_fields = ['date']
    search_fields = ['operation__id_operation', 'action']


# ========================================
# ADMIN PROFIL ENTREPRISE (NOUVEAU)
# ========================================
@admin.register(ProfilEntreprise)
class ProfilEntrepriseAdmin(admin.ModelAdmin):
    list_display = ['user', 'nom_entreprise', 'siret', 'telephone', 'email', 'est_complet']
    search_fields = ['nom_entreprise', 'siret', 'user__username']
    readonly_fields = ['date_creation', 'date_modification']
    
    fieldsets = (
        ('Utilisateur', {
            'fields': ('user',)
        }),
        ('Identification', {
            'fields': ('nom_entreprise', 'forme_juridique', 'siret', 'rcs', 'code_ape', 'capital_social', 'tva_intracommunautaire')
        }),
        ('Adresse', {
            'fields': ('adresse', 'code_postal', 'ville')
        }),
        ('Contact', {
            'fields': ('telephone', 'email', 'site_web')
        }),
        ('Assurance', {
            'fields': ('assurance_decennale_nom', 'assurance_decennale_numero', 'assurance_decennale_validite')
        }),
        ('Qualifications', {
            'fields': ('qualifications',)
        }),
        ('Facturation', {
            'fields': ('iban', 'bic', 'mentions_legales_devis')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )