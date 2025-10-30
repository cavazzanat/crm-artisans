# ================================
# core/models.py - Version avec devis/facture
# ================================

from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

class Client(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    id_client = models.CharField(max_length=15, blank=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=20)
    adresse = models.TextField()
    ville = models.CharField(max_length=100)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['nom', 'prenom']
    
    def __str__(self):
        return f"{self.nom} {self.prenom}"
    
    def save(self, *args, **kwargs):
        if not self.id_client:
            import uuid
            unique_suffix = str(uuid.uuid4())[:6].upper()
            self.id_client = f"U{self.user.id}CL{unique_suffix}"
        super().save(*args, **kwargs)
    
    @property
    def derniere_operation(self):
        return self.operations.order_by('-date_creation').first()
    
    @property
    def prochaine_operation(self):
        return self.operations.filter(
            statut='planifie', 
            date_prevue__gte=timezone.now()
        ).order_by('date_prevue').first()


class Operation(models.Model):
    STATUTS = [
        ('en_attente_devis', 'En attente devis'),
        ('a_planifier', 'À planifier'),
        ('planifie', 'Planifié'),
        ('realise', 'Réalisé'),
        ('paye', 'Payé'),
        ('devis_refuse', 'Devis refusé / Opération annulée'),
    ]
    
    PLANNING_MODE_CHOICES = [
        ('a_planifier', 'À planifier'),
        ('replanifier', 'Replanifier'),
        ('deja_realise', 'Déjà réalisé'),
    ]
    
    # ========================================
    # INFORMATIONS DE BASE
    # ========================================
    planning_mode = models.CharField(
        max_length=20,
        choices=PLANNING_MODE_CHOICES,
        default='a_planifier',
        verbose_name="Mode de planification"
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='operations')
    id_operation = models.CharField(max_length=15, blank=True)
    type_prestation = models.CharField(max_length=200)
    adresse_intervention = models.TextField()
    commentaires = models.TextField(blank=True, null=True, verbose_name="Commentaires / Notes")
    
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_attente_devis')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    # ========================================
    # DATES D'OPÉRATION
    # ========================================
    date_prevue = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="Date prévue d'intervention"
    )
    date_realisation = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="Date de réalisation"
    )
    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de paiement"
    )
    
    # ========================================
    # NOUVEAU : CHAMPS POUR LE DEVIS
    # ========================================
    avec_devis = models.BooleanField(
        default=False,
        verbose_name="Opération avec devis"
    )
    
    numero_devis = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Numéro de devis",
        help_text="Format: DEV-2025-001"
    )
    
    devis_date_envoi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'envoi du devis"
    )
    
    devis_date_reponse = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de réponse du client"
    )
    
    devis_statut = models.CharField(
        max_length=20,
        choices=[
            ('en_attente', 'En attente de réponse'),
            ('accepte', 'Devis accepté'),
            ('refuse', 'Devis refusé'),
            ('relance', 'À relancer'),
        ],
        null=True,
        blank=True,
        verbose_name="Statut du devis"
    )
    
    devis_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes du devis",
        help_text="Notes qui apparaîtront sur le PDF du devis"
    )
    
    devis_validite_jours = models.IntegerField(
        default=30,
        verbose_name="Validité du devis (jours)",
        help_text="Nombre de jours de validité du devis"
    )
    
    devis_historique_numeros = models.TextField(
        blank=True,
        null=True,
        verbose_name="Historique des numéros de devis",
        help_text="Liste JSON des anciens numéros de devis (en cas de refus et nouveau devis)"
    )
    
    # ========================================
    # ANCIEN : CHAMPS POUR LE DEVIS (À SUPPRIMER APRÈS MIGRATION)
    # ========================================
    devis_cree = models.BooleanField(default=False, verbose_name="Devis créé")
    
    # ========================================
    # NOUVEAU : CHAMPS POUR LA FACTURE
    # ========================================
    facture_generee = models.BooleanField(
        default=False,
        verbose_name="Facture générée"
    )
    
    numero_facture = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Numéro de facture",
        help_text="Format: FAC-2025-001"
    )
    
    facture_date_emission = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'émission de la facture"
    )
    
    facture_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes de la facture",
        help_text="Notes qui apparaîtront sur le PDF de la facture"
    )
    
    # ========================================
    # CHAMP POUR LE MODE DE PAIEMENT
    # ========================================
    mode_paiement = models.CharField(
        max_length=20,
        choices=[
            ('comptant', 'Comptant'),
            ('echelonne', 'Échelonné'),
        ],
        default='comptant',
        verbose_name="Mode de paiement"
    )
    
    class Meta:
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.id_operation} - {self.type_prestation}"
    
    def save(self, *args, **kwargs):
        # Générer l'ID opération
        if not self.id_operation:
            import uuid
            unique_suffix = str(uuid.uuid4())[:6].upper()
            self.id_operation = f"U{self.user.id}OP{unique_suffix}"
        
        # Synchroniser automatiquement devis_statut et statut
        if self.devis_statut == 'refuse' and self.statut != 'devis_refuse':
            self.statut = 'devis_refuse'
        elif self.devis_statut == 'accepte' and self.statut == 'en_attente_devis':
            self.statut = 'a_planifier'
        
        super().save(*args, **kwargs)
    
    # ========================================
    # PROPERTIES EXISTANTES
    # ========================================
    @property
    def montant_total(self):
        """Calcule le montant total de l'opération (somme des lignes d'intervention)"""
        return sum(intervention.montant for intervention in self.interventions.all())
    
    # ========================================
    # NOUVELLES PROPERTIES POUR DEVIS/FACTURE
    # ========================================
    @property
    def peut_generer_devis(self):
        """
        Vérifie si on peut générer un devis PDF.
        
        Conditions :
        - avec_devis = True
        - statut = EN_ATTENTE_DEVIS
        - Au moins 1 ligne d'intervention
        - Pas encore de numéro de devis
        """
        return (
            self.avec_devis == True 
            and self.statut == 'en_attente_devis' 
            and self.interventions.exists()
            and not self.numero_devis
        )
    
    @property
    def peut_generer_facture(self):
        """
        Vérifie si on peut générer une facture PDF.
        
        Conditions :
        - statut in [REALISE, PAYE]
        - facture_generee = False
        - Au moins 1 ligne d'intervention
        """
        return (
            self.statut in ['realise', 'paye'] 
            and self.facture_generee == False
            and self.interventions.exists()
        )
    
    @property
    def peut_creer_nouveau_devis(self):
        """
        Vérifie si on peut créer un nouveau devis après un refus.
        
        Conditions :
        - avec_devis = True
        - devis_statut = 'refuse'
        """
        return (
            self.avec_devis == True 
            and self.devis_statut == 'refuse'
        )
    
    @property
    def devis_date_limite(self):
        """
        Calcule la date limite de validité du devis.
        
        Retourne None si pas de date d'envoi.
        """
        if self.devis_date_envoi and self.devis_validite_jours:
            from datetime import timedelta
            return self.devis_date_envoi + timedelta(days=self.devis_validite_jours)
        return None
    
    @property
    def delai_reponse_client(self):
        """
        Calcule le délai de réponse du client en jours.
        
        Retourne None si pas de date de réponse ou d'envoi.
        """
        if self.devis_date_envoi and self.devis_date_reponse:
            return (self.devis_date_reponse - self.devis_date_envoi).days
        return None


# MODÈLE SÉPARÉ pour les échéances (pas à l'intérieur de Operation!)
class Echeance(models.Model):
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='echeances')
    numero = models.IntegerField(verbose_name="Numéro d'échéance")
    montant = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant")
    date_echeance = models.DateField(verbose_name="Date d'échéance")
    paye = models.BooleanField(default=False, verbose_name="Payé")
    ordre = models.IntegerField(default=1)
    
    class Meta:
        ordering = ['ordre']
        verbose_name = "Échéance de paiement"
        verbose_name_plural = "Échéances de paiement"
    
    def __str__(self):
        return f"Échéance {self.numero} - {self.montant}€ ({self.operation.id_operation})"
    
    def statut_display(self):
        """Retourne le statut dynamique de l'échéance"""
        from django.utils import timezone
        
        if self.paye:
            return 'paye'
        elif self.date_echeance < timezone.now().date():
            return 'retard'
        else:
            return 'en_attente'


class Intervention(models.Model):
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='interventions')
    description = models.CharField(max_length=200)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    ordre = models.PositiveIntegerField(default=1)
    
    class Meta:
        ordering = ['ordre']
    
    def __str__(self):
        return f"{self.description} - {self.montant}€"


class HistoriqueOperation(models.Model):
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='historique')
    action = models.CharField(max_length=200)
    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.operation.id_operation} - {self.action}"