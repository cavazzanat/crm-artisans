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
            # Génère un ID unique : USER_ID + UUID court
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
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_attente_devis')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.id_operation} - {self.type_prestation}"
    
    def save(self, *args, **kwargs):
        if not self.id_operation:
            import uuid
            # Génère un ID unique : USER_ID + UUID court
            unique_suffix = str(uuid.uuid4())[:6].upper()
            self.id_operation = f"U{self.user.id}OP{unique_suffix}"
        super().save(*args, **kwargs)
    
    @property
    def montant_total(self):
        return sum(intervention.montant for intervention in self.interventions.all())
    
    @property
    def peut_generer_facture(self):
        return self.statut in ['realise', 'paye']

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