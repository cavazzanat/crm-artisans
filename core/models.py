# ================================
# core/models.py - Version refactorisée avec système de devis multiple
# ================================

from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal


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
        ('en_cours', '🔵 En cours'),
        ('a_traiter', '🟠 À traiter'),
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
    # SYSTÈME DE DEVIS
    # ========================================
    avec_devis = models.BooleanField(
        default=False,
        verbose_name="Opération avec devis"
    )
    
    # ========================================
    # MODE DE PAIEMENT
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
        
        super().save(*args, **kwargs)
    
    # ========================================
    # PROPERTIES POUR MONTANT TOTAL
    # ========================================
    @property
    def montant_total(self):
        """
        Calcule le montant total de l'opération :
        - Si avec_devis : somme des devis acceptés
        - Si sans devis : somme des interventions
        """
        if self.avec_devis:
            devis_acceptes = self.devis_set.filter(statut='accepte')
            total = sum(devis.total_ttc for devis in devis_acceptes)
            return Decimal(str(total))
        else:
            return self.total_ttc
    
    @property
    def sous_total_ht(self):
        """Sous-total HT - logique pour opérations SANS devis uniquement"""
        if self.avec_devis:
            return Decimal('0.00')
        
        total = self.interventions.aggregate(
            total=Sum('montant')
        )['total']
        return total if total is not None else Decimal('0.00')
    
    @property
    def total_tva(self):
        """Total de la TVA - logique pour opérations SANS devis uniquement"""
        if self.avec_devis:
            return Decimal('0.00')
        
        total_tva = Decimal('0.00')
        for intervention in self.interventions.all():
            total_tva += intervention.montant_tva
        return total_tva
    
    @property
    def total_ttc(self):
        """Total TTC - logique pour opérations SANS devis uniquement"""
        if self.avec_devis:
            return Decimal('0.00')
        
        return self.sous_total_ht + self.total_tva
    
    # ========================================
    # PROPERTIES POUR GESTION DEVIS
    # ========================================
    @property
    def dernier_devis(self):
        """Retourne le devis avec la version la plus élevée"""
        return self.devis_set.order_by('-version').first()
    
    @property
    def statut_devis_global(self):
        """Retourne le statut du dernier devis créé"""
        dernier = self.dernier_devis
        return dernier.statut if dernier else None
    
    @property
    def nombre_devis(self):
        """Compte le nombre total de devis"""
        return self.devis_set.count()
    
    @property
    def nombre_devis_acceptes(self):
        """Compte le nombre de devis acceptés"""
        return self.devis_set.filter(statut='accepte').count()
    
    # ========================================
    # ✅ MÉTHODE CRITIQUE POUR INTERVENTIONS MULTIPLES
    # ========================================
    def update_statut_from_interventions(self):
        """
        Recalcule automatiquement le statut de l'opération
        selon l'état des interventions multiples
        """
        interventions = self.interventions.all()
        
        if not interventions.exists():
            return
        
        nb_total = interventions.count()
        nb_realisees = interventions.filter(realise=True).count()
        nb_non_planifiees = interventions.filter(date_prevue__isnull=True).count()
        
        maintenant = timezone.now()
        en_retard = interventions.filter(
            realise=False,
            date_prevue__lt=maintenant
        ).exists()
        
        # ✅ LOGIQUE DE CALCUL DU STATUT
        if nb_realisees == nb_total:
            nouveau_statut = 'realise'
        elif nb_realisees > 0:
            nouveau_statut = 'en_cours'
        elif nb_non_planifiees > 0:
            nouveau_statut = 'a_planifier'
        elif en_retard:
            nouveau_statut = 'a_traiter'
        else:
            nouveau_statut = 'planifie'
        
        # Sauvegarder uniquement si changement
        if self.statut != nouveau_statut:
            self.statut = nouveau_statut
            super(Operation, self).save(update_fields=['statut'])
    
    def get_interventions_stats(self):
        """Retourne stats des interventions planifiées"""
        planifiees = self.interventions.exclude(date_prevue__isnull=True)
        return {
            'total': planifiees.count(),
            'realisees': planifiees.filter(realise=True).count()
        }        
    

# ========================================
# NOUVEAU MODÈLE : DEVIS
# ========================================
class Devis(models.Model):
    STATUTS_DEVIS = [
        ('brouillon', 'Brouillon'),
        ('pret', 'Prêt (PDF généré)'),
        ('envoye', 'Envoyé'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé'),
    ]
    
    operation = models.ForeignKey(
        Operation, 
        on_delete=models.CASCADE, 
        related_name='devis_set'
    )
    
    # Identification
    numero_devis = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="Numéro de devis",
        help_text="Format: DEVIS-2025-U1-00001"
    )
    
    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Version du devis",
        help_text="1, 2, 3... (incrémenté automatiquement)"
    )
    
    # Dates
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    date_envoi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'envoi au client"
    )
    
    date_reponse = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de réponse du client"
    )
    
    # Statut
    statut = models.CharField(
        max_length=20,
        choices=STATUTS_DEVIS,
        default='brouillon',
        verbose_name="Statut du devis"
    )
    
    # Contenu
    notes = models.TextField(
        blank=True,
        verbose_name="Notes du devis",
        help_text="Notes qui apparaîtront sur le PDF"
    )
    
    validite_jours = models.IntegerField(
        default=30,
        verbose_name="Validité (jours)",
        help_text="Nombre de jours de validité"
    )
    
    class Meta:
        ordering = ['version']  # Du plus ancien au plus récent
        verbose_name = "Devis"
        verbose_name_plural = "Devis"
        unique_together = [['operation', 'version']]
    
    def __str__(self):
        return f"{self.numero_devis} - Version {self.version}"
    
    def save(self, *args, **kwargs):
        from django.db.models import Max
        
        # Auto-générer le numéro si nouveau devis
        if not self.numero_devis:
            import re
            from datetime import datetime
            
            annee_courante = datetime.now().year
            prefix = f'DEVIS-{annee_courante}-U{self.operation.user.id}-'
            
            # Récupérer tous les devis existants de cet utilisateur pour cette année
            derniers_devis = Devis.objects.filter(
                operation__user=self.operation.user,
                numero_devis__startswith=prefix
            ).values_list('numero_devis', flat=True)
            
            # Extraire le numéro le plus élevé
            max_numero = 0
            for devis in derniers_devis:
                match = re.search(r'-(\d+)$', devis)
                if match:
                    numero = int(match.group(1))
                    if numero > max_numero:
                        max_numero = numero
            
            # Nouveau numéro = max + 1
            nouveau_numero = max_numero + 1
            self.numero_devis = f'{prefix}{nouveau_numero:05d}'
        
        # ✅ CORRECTION FINALE : Auto-incrémenter la version
        if not self.pk:  # Seulement pour les nouveaux devis
            # ✅ EXCLURE le devis actuel (self) de la requête
            autres_devis = Devis.objects.filter(
                operation=self.operation
            ).exclude(pk=self.pk)  # ← CRITIQUE : exclure self
            
            max_version = autres_devis.aggregate(
                Max('version')
            )['version__max'] or 0
            
            self.version = max_version + 1
        
        super().save(*args, **kwargs)
    
    # ========================================
    # PROPERTIES POUR CALCULS
    # ========================================
    @property
    def sous_total_ht(self):
        """Sous-total HT (somme des lignes HT)"""
        total = self.lignes.aggregate(
            total=Sum('montant')
        )['total']
        return total if total is not None else Decimal('0.00')
    
    @property
    def total_tva(self):
        """Total de la TVA"""
        total_tva = Decimal('0.00')
        for ligne in self.lignes.all():
            total_tva += ligne.montant_tva
        return total_tva
    
    @property
    def total_ttc(self):
        """Total TTC (ce que paie le client)"""
        return self.sous_total_ht + self.total_tva
    
    @property
    def date_limite(self):
        """Date limite de validité du devis"""
        if self.date_envoi and self.validite_jours:
            from datetime import timedelta
            return self.date_envoi + timedelta(days=self.validite_jours)
        return None
    
    @property
    def est_expire(self):
        """Vérifie si le devis est expiré"""
        if not self.date_envoi or not self.validite_jours:
            return False
        
        date_limite = self.date_limite
        return (
            date_limite 
            and date_limite < timezone.now().date()
            and self.statut == 'envoye'
        )
    
    @property
    def delai_reponse(self):
        """Délai de réponse du client en jours"""
        if self.date_envoi and self.date_reponse:
            return (self.date_reponse - self.date_envoi).days
        return None
    
    @property
    def est_verrouille(self):
        """Un devis est verrouillé s'il n'est plus en brouillon"""
        return self.statut != 'brouillon'
    
    @property
    def peut_etre_supprime(self):
        """On peut supprimer les devis en brouillon, prêt ou refusé"""
        return self.statut in ['brouillon', 'pret', 'refuse']

# ========================================
# NOUVEAU MODÈLE : LIGNE DE DEVIS
# ========================================
class LigneDevis(models.Model):
    UNITES_CHOICES = [
        ('unite', 'Unité'),
        ('forfait', 'Forfait'),
        ('heure', 'Heure'),
        ('jour', 'Jour'),
        ('m2', 'm²'),
        ('ml', 'Mètre linéaire'),
    ]
    
    devis = models.ForeignKey(
        Devis,
        on_delete=models.CASCADE,
        related_name='lignes'
    )
    
    description = models.TextField(verbose_name="Description")
    
    quantite = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name="Quantité"
    )
    
    unite = models.CharField(
        max_length=20,
        choices=UNITES_CHOICES,
        default='forfait',
        verbose_name="Unité"
    )
    
    prix_unitaire_ht = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire HT (€)"
    )
    
    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        verbose_name="Taux TVA (%)"
    )
    
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Total HT",
        help_text="Calculé automatiquement (quantité × prix unitaire HT)"
    )
    
    ordre = models.PositiveIntegerField(default=1)
    
    class Meta:
        ordering = ['ordre']
        verbose_name = "Ligne de devis"
        verbose_name_plural = "Lignes de devis"
    
    def __str__(self):
        return f"{self.description} - {self.montant}€ HT"
    
    def save(self, *args, **kwargs):
        """Calcul automatique du montant HT"""
        self.montant = self.quantite * self.prix_unitaire_ht
        super().save(*args, **kwargs)
    
    @property
    def montant_tva(self):
        """Montant de la TVA pour cette ligne"""
        return (self.montant * self.taux_tva) / Decimal('100')
    
    @property
    def montant_ttc(self):
        """Total TTC de cette ligne"""
        return self.montant + self.montant_tva


# ========================================
# MODÈLE INTERVENTION (CONSERVÉ POUR OPÉRATIONS SANS DEVIS)
# ========================================
# ========================================
# MODÈLE INTERVENTION - VERSION INTERVENTIONS MULTIPLES
# ========================================
class Intervention(models.Model):
    """
    Modèle Intervention - Supporte maintenant les interventions multiples
    Chaque intervention = une étape de réalisation d'une opération
    """
    
    UNITES_CHOICES = [
        ('unite', 'Unité'),
        ('forfait', 'Forfait'),
        ('heure', 'Heure'),
        ('jour', 'Jour'),
        ('m2', 'm²'),
        ('ml', 'Mètre linéaire'),
    ]
    
    # ════════════════════════════════════════════════════════════
    # CHAMPS EXISTANTS (CONSERVÉS)
    # ════════════════════════════════════════════════════════════
    
    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name='interventions'
    )
    
    description = models.TextField(
        verbose_name="Description de l'intervention"
    )
    
    quantite = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name="Quantité",
        help_text="Quantité (ex: 2, 1.5, 10)"
    )
    
    unite = models.CharField(
        max_length=20,
        choices=UNITES_CHOICES,
        default='forfait',
        verbose_name="Unité",
        help_text="Unité de mesure"
    )
    
    prix_unitaire_ht = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix unitaire HT (€)",
        help_text="Prix unitaire HT en euros"
    )
    
    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        verbose_name="Taux TVA (%)",
        help_text="Taux de TVA en %"
    )
    
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant HT",
        help_text="Total HT de la ligne (quantité × prix unitaire HT)"
    )
    
    ordre = models.PositiveIntegerField(
        default=999,  # ← MODIFIÉ : 999 au lieu de 1
        verbose_name="Ordre d'affichage"
    )
    
    # ════════════════════════════════════════════════════════════
    # ✅ NOUVEAUX CHAMPS POUR INTERVENTIONS MULTIPLES
    # ════════════════════════════════════════════════════════════
    
    date_prevue = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date prévue",
        help_text="Date et heure planifiées pour cette intervention"
    )
    
    date_realisation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de réalisation",
        help_text="Rempli automatiquement quand l'intervention est marquée comme réalisée"
    )
    
    realise = models.BooleanField(
        default=False,
        verbose_name="Réalisée",
        help_text="Cocher si l'intervention a été effectuée"
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name="Commentaire",
        help_text="Notes libres sur cette intervention"
    )
    
    # ════════════════════════════════════════════════════════════
    # META & __STR__
    # ════════════════════════════════════════════════════════════
    
    class Meta:
        ordering = ['ordre', 'date_prevue']
        verbose_name = "Intervention"
        verbose_name_plural = "Interventions"
    
    def __str__(self):
        if self.date_prevue:
            date_str = self.date_prevue.strftime('%d/%m/%Y %H:%M')
            return f"{self.description[:50]} - {date_str}"
        return f"{self.description[:50]} - {self.montant}€ HT"
    
    # ════════════════════════════════════════════════════════════
    # PROPERTIES EXISTANTES (CONSERVÉES)
    # ════════════════════════════════════════════════════════════
    
    @property
    def montant_tva(self):
        """Montant de la TVA pour cette ligne"""
        return (self.montant * self.taux_tva) / Decimal('100')
    
    @property
    def montant_ttc(self):
        """Total TTC de cette ligne"""
        return self.montant + self.montant_tva
    
    # ════════════════════════════════════════════════════════════
    # ✅ NOUVELLES PROPERTIES POUR INTERVENTIONS MULTIPLES
    # ════════════════════════════════════════════════════════════
    
    @property
    def est_planifiee(self):
        """Vérifie si l'intervention a une date prévue"""
        return self.date_prevue is not None
    
    @property
    def est_en_retard(self):
        """Vérifie si l'intervention est en retard (date passée et non réalisée)"""
        if not self.date_prevue or self.realise:
            return False
        return self.date_prevue < timezone.now()
    
    @property
    def statut_display(self):
        """Retourne le statut de l'intervention pour affichage"""
        if self.realise:
            return "✅ Réalisé"
        elif not self.date_prevue:
            return "📅 À planifier"
        elif self.est_en_retard:
            return "⚠️ En retard"
        else:
            return "⏰ Planifié"
        
    
    @property
    def montant_ttc(self):
        """Calcul du montant TTC"""
        return self.montant * (1 + self.taux_tva / 100)
    
    # ════════════════════════════════════════════════════════════
    # ✅ MÉTHODE SAVE() SURCHARGÉE
    # ════════════════════════════════════════════════════════════
    
    def save(self, *args, **kwargs):
        """
        Calcul automatique lors de la sauvegarde :
        1. Montant HT (quantité × prix unitaire)
        2. Ordre selon date_prevue
        3. Date de réalisation si marquée comme réalisée
        4. Recalcul du statut de l'opération parent
        """
        
        # ✅ CALCUL 1 : Montant HT
        if self.prix_unitaire_ht is not None:
            self.montant = self.quantite * self.prix_unitaire_ht
        
        # ✅ CALCUL 2 : Ordre automatique selon date_prevue
        if self.date_prevue:
            # Compter combien d'interventions ont une date_prevue antérieure
            interventions_avant = Intervention.objects.filter(
                operation=self.operation,
                date_prevue__lt=self.date_prevue
            ).exclude(pk=self.pk if self.pk else None)
            
            self.ordre = interventions_avant.count() + 1
        else:
            # Pas de date = ordre 999 (à la fin)
            self.ordre = 999
        
        # ✅ CALCUL 3 : Date de réalisation automatique
        if self.realise and not self.date_realisation:
            self.date_realisation = timezone.now()
        elif not self.realise:
            # Si on décoche "réalisé", on efface la date de réalisation
            self.date_realisation = None
        
        # Sauvegarder l'intervention
        super().save(*args, **kwargs)
        
        # ✅ CALCUL 4 : Recalculer le statut de l'opération parent
        self.operation.update_statut_from_interventions()


# ========================================
# MODÈLE ÉCHEANCE (INCHANGÉ)
# ========================================
class Echeance(models.Model):
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='echeances')
    numero = models.IntegerField(verbose_name="Numéro d'échéance")
    montant = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant")
    date_echeance = models.DateField(verbose_name="Date d'échéance")
    paye = models.BooleanField(default=False, verbose_name="Payé")
    ordre = models.IntegerField(default=1)
    
    # Champs facture
    facture_generee = models.BooleanField(
        default=False,
        verbose_name="Facture générée"
    )
    numero_facture = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Numéro de facture"
    )
    facture_date_emission = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date d'émission facture"
    )
    facture_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('globale', 'Facture globale'),
            ('acompte', 'Facture d\'acompte'),
            ('solde', 'Facture de solde'),
        ],
        verbose_name="Type de facture"
    )
    
    class Meta:
        ordering = ['ordre']
        verbose_name = "Échéance de paiement"
        verbose_name_plural = "Échéances de paiement"
    
    def __str__(self):
        return f"Échéance {self.numero} - {self.montant}€ ({self.operation.id_operation})"
    
    def statut_display(self):
        """Retourne le statut dynamique de l'échéance"""
        if self.paye:
            return 'paye'
        elif self.date_echeance < timezone.now().date():
            return 'retard'
        else:
            return 'en_attente'
    
    @property
    def peut_generer_facture(self):
        """Une facture peut être générée si le paiement est marqué comme payé"""
        return self.paye and not self.facture_generee


# ========================================
# MODÈLE HISTORIQUE (INCHANGÉ)
# ========================================
class HistoriqueOperation(models.Model):
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='historique')
    action = models.CharField(max_length=200)
    utilisateur = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.operation.id_operation} - {self.action}"


# ========================================
# MODÈLE PROFIL ENTREPRISE (INCHANGÉ)
# ========================================
class ProfilEntreprise(models.Model):
    """Profil de l'entreprise pour générer les devis/factures"""
    
    FORMES_JURIDIQUES = [
        ('auto_entrepreneur', 'Auto-entrepreneur / Micro-entreprise'),
        ('eurl', 'EURL'),
        ('sarl', 'SARL'),
        ('sas', 'SAS'),
        ('sasu', 'SASU'),
        ('ei', 'Entreprise Individuelle'),
        ('autre', 'Autre'),
    ]
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profil_entreprise'
    )
    
    # Identification entreprise
    nom_entreprise = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Nom de l'entreprise / Raison sociale"
    )
    forme_juridique = models.CharField(
        max_length=50,
        choices=FORMES_JURIDIQUES,
        blank=True,
        verbose_name="Forme juridique"
    )
    
    adresse = models.TextField(blank=True, verbose_name="Adresse du siège social")
    code_postal = models.CharField(max_length=10, blank=True, verbose_name="Code postal")
    ville = models.CharField(max_length=100, blank=True, verbose_name="Ville")
    
    siret = models.CharField(max_length=14, blank=True, verbose_name="N° SIRET")
    rcs = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="N° RCS + Ville",
        help_text="Ex: RCS Paris 123 456 789"
    )
    code_ape = models.CharField(max_length=10, blank=True, verbose_name="Code APE/NAF")
    capital_social = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Capital social (€)"
    )
    tva_intracommunautaire = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="N° TVA intracommunautaire"
    )
    
    # Coordonnées professionnelles
    telephone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone professionnel")
    email = models.EmailField(blank=True, verbose_name="Email professionnel")
    site_web = models.URLField(blank=True, verbose_name="Site web")
    
    # Assurances
    assurance_decennale_nom = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Nom de l'assureur"
    )
    assurance_decennale_numero = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="N° de police"
    )
    assurance_decennale_validite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de validité"
    )
    
    # Qualifications
    qualifications = models.TextField(
        blank=True,
        verbose_name="Qualifications / Certifications",
        help_text="Ex: RGE, Qualibat, etc."
    )
    
    # Facturation
    iban = models.CharField(max_length=34, blank=True, verbose_name="IBAN")
    bic = models.CharField(max_length=11, blank=True, verbose_name="BIC/SWIFT")
    
    # Mentions légales
    mentions_legales_devis = models.TextField(
        blank=True,
        verbose_name="Mentions légales sur le devis",
        help_text="Texte qui apparaîtra en bas du devis"
    )
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Profil entreprise"
        verbose_name_plural = "Profils entreprise"
    
    def __str__(self):
        return f"{self.nom_entreprise or 'Profil'} - {self.user.username}"
    
    @property
    def est_complet(self):
        """Vérifie si le profil contient les informations minimales"""
        champs_obligatoires = [
            self.nom_entreprise,
            self.adresse,
            self.siret,
            self.telephone,
            self.email,
        ]
        return all(champs_obligatoires)