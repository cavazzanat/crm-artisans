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
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='operations')
    id_operation = models.CharField(max_length=15, blank=True)
    type_prestation = models.CharField(max_length=200)
    adresse_intervention = models.TextField()
    date_prevue = models.DateTimeField(null=True, blank=True)
    date_realisation = models.DateTimeField(null=True, blank=True)
    date_paiement = models.DateTimeField(null=True, blank=True)
    
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_attente_devis')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    # CHAMPS POUR LE DEVIS
    devis_cree = models.BooleanField(default=False, verbose_name="Devis créé")
    devis_date_envoi = models.DateField(null=True, blank=True, verbose_name="Date envoi devis")
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
    
    # CHAMP POUR LE MODE DE PAIEMENT
    mode_paiement = models.CharField(
        max_length=20,
        choices=[
            ('comptant', 'Comptant'),
            ('echelonne', 'Échelonné'),
        ],
        default='comptant',
        verbose_name="Mode de paiement"
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
    
    class Meta:
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.id_operation} - {self.type_prestation}"
    
    def save(self, *args, **kwargs):
        if not self.id_operation:
            import uuid
            unique_suffix = str(uuid.uuid4())[:6].upper()
            self.id_operation = f"U{self.user.id}OP{unique_suffix}"
        # ✅ NOUVEAU : Synchroniser automatiquement devis_statut et statut
        if self.devis_statut == 'refuse' and self.statut != 'devis_refuse':
            self.statut = 'devis_refuse'
        elif self.devis_statut == 'accepte' and self.statut == 'en_attente_devis':
            self.statut = 'a_planifier'
        super().save(*args, **kwargs)
    
    @property
    def montant_total(self):
        return sum(intervention.montant for intervention in self.interventions.all())
    
    @property
    def peut_generer_facture(self):
        return self.statut in ['realise', 'paye']


# MODÈLE SÉPARÉ pour les échéances (pas à l'intérieur de Operation!)
class Echeance(models.Model):
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='echeances')
    numero = models.IntegerField(verbose_name="Numéro d'échéance")
    montant = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant")
    date_echeance = models.DateField(verbose_name="Date d'échéance")
    paye = models.BooleanField(default=False, verbose_name="Payé")  # ← AJOUTEZ cette ligne
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