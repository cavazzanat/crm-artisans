# ================================
# core/pdf_generator.py
# Générateur de PDF pour devis
# ================================

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from django.conf import settings
import os

def generer_devis_pdf(operation, profil):
    """
    Génère un PDF de devis professionnel
    
    Args:
        operation: Instance de Operation
        profil: Instance de ProfilEntreprise
    
    Returns:
        BytesIO contenant le PDF généré
    """
    
    # Créer un buffer en mémoire
    buffer = BytesIO()
    
    # Créer le document PDF
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # Container pour les éléments
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    style_normal = styles['Normal']
    style_heading = styles['Heading1']
    
    # Style personnalisé pour le titre
    style_titre = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#6366f1'),
        spaceAfter=30,
        alignment=1  # Centré
    )
    
    # ========================================
    # EN-TÊTE : Infos entreprise
    # ========================================
    
    # Logo (si existe)
    #if profil.logo and os.path.exists(profil.logo.path):
    #   logo = Image(profil.logo.path, width=4*cm, height=2*cm)
    #   elements.append(logo)
    #   elements.append(Spacer(1, 0.5*cm))
    
    # Informations entreprise
    entreprise_data = [
        [Paragraph(f"<b>{profil.nom_entreprise}</b>", style_normal)],
        [Paragraph(profil.adresse.replace('\n', '<br/>'), style_normal)],
        [Paragraph(f"{profil.code_postal} {profil.ville}", style_normal)],
    ]
    
    if profil.siret:
        entreprise_data.append([Paragraph(f"SIRET : {profil.siret}", style_normal)])
    
    if profil.telephone:
        entreprise_data.append([Paragraph(f"Tél : {profil.telephone}", style_normal)])
    
    if profil.email:
        entreprise_data.append([Paragraph(f"Email : {profil.email}", style_normal)])
    
    table_entreprise = Table(entreprise_data, colWidths=[17*cm])
    table_entreprise.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(table_entreprise)
    elements.append(Spacer(1, 1*cm))
    
    # ========================================
    # TITRE DU DEVIS
    # ========================================
    
    titre = Paragraph(f"DEVIS N° {operation.numero_devis}", style_titre)
    elements.append(titre)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========================================
    # INFORMATIONS CLIENT ET DEVIS
    # ========================================
    
    # Bloc gauche : Client
    client_data = [
        [Paragraph("<b>CLIENT</b>", style_normal)],
        [Paragraph(f"{operation.client.nom} {operation.client.prenom}", style_normal)],
        [Paragraph(operation.adresse_intervention.replace('\n', '<br/>'), style_normal)],
    ]
    
    if operation.client.telephone:
        client_data.append([Paragraph(f"Tél : {operation.client.telephone}", style_normal)])
    
    if operation.client.email:
        client_data.append([Paragraph(f"Email : {operation.client.email}", style_normal)])
    
    # Bloc droit : Infos devis
    from django.utils import timezone
    date_emission = timezone.now().date()
    date_limite = operation.devis_date_limite if operation.devis_date_limite else None
    
    devis_data = [
        [Paragraph("<b>INFORMATIONS</b>", style_normal)],
        [Paragraph(f"Date : {date_emission.strftime('%d/%m/%Y')}", style_normal)],
        [Paragraph(f"Validité : {operation.devis_validite_jours} jours", style_normal)],
    ]
    
    if date_limite:
        devis_data.append([Paragraph(f"Valable jusqu'au : {date_limite.strftime('%d/%m/%Y')}", style_normal)])
    
    # Créer un tableau 2 colonnes
    info_table_data = [
        [
            Table(client_data, colWidths=[8*cm]),
            Table(devis_data, colWidths=[8*cm])
        ]
    ]
    
    info_table = Table(info_table_data, colWidths=[8.5*cm, 8.5*cm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(info_table)
    elements.append(Spacer(1, 1*cm))
    
    # ========================================
    # OBJET / TYPE DE PRESTATION
    # ========================================
    
    objet = Paragraph(f"<b>Objet :</b> {operation.type_prestation}", style_normal)
    elements.append(objet)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========================================
    # TABLEAU DES LIGNES
    # ========================================
    
    # En-tête du tableau
    table_data = [
        ['Description', 'Qté', 'Unité', 'P.U. HT', 'TVA', 'Total HT']
    ]
    
    # Lignes d'intervention
    interventions = operation.interventions.all()
    
    for intervention in interventions:
        table_data.append([
            Paragraph(intervention.description, style_normal),
            f"{intervention.quantite:,.2f}".replace(',', ' ').replace('.', ','),
            intervention.get_unite_display(),
            f"{intervention.prix_unitaire_ht:,.2f} €".replace(',', ' ').replace('.', ','),
            f"{intervention.taux_tva:,.0f}%".replace('.', ','),
            f"{intervention.montant:,.2f} €".replace(',', ' ').replace('.', ',')
        ])
    
    # Ligne vide
    table_data.append(['', '', '', '', '', ''])
    
    # Totaux
    table_data.append(['', '', '', '', 'Sous-total HT', f"{operation.sous_total_ht:,.2f} €".replace(',', ' ').replace('.', ',')])
    table_data.append(['', '', '', '', 'TVA', f"{operation.total_tva:,.2f} €".replace(',', ' ').replace('.', ',')])
    table_data.append(['', '', '', '', Paragraph('<b>TOTAL TTC</b>', style_normal), Paragraph(f"<b>{operation.total_ttc:,.2f} €</b>".replace(',', ' ').replace('.', ','), style_normal)])
    
    # Créer le tableau
    table = Table(table_data, colWidths=[7*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm])
    table.setStyle(TableStyle([
        # En-tête
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Corps du tableau
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -4), 0.5, colors.grey),
        
        # Totaux
        ('ALIGN', (4, -3), (5, -1), 'RIGHT'),
        ('FONTNAME', (4, -1), (5, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (4, -3), (5, -1), 10),
        ('LINEABOVE', (4, -3), (5, -3), 1, colors.grey),
        ('LINEABOVE', (4, -1), (5, -1), 2, colors.HexColor('#6366f1')),
        ('BACKGROUND', (4, -1), (5, -1), colors.HexColor('#eef2ff')),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    
    # ========================================
    # NOTES DU DEVIS
    # ========================================
    
    if operation.devis_notes:
        notes_titre = Paragraph("<b>Notes :</b>", style_normal)
        elements.append(notes_titre)
        elements.append(Spacer(1, 0.3*cm))
        
        notes_contenu = Paragraph(operation.devis_notes.replace('\n', '<br/>'), style_normal)
        elements.append(notes_contenu)
        elements.append(Spacer(1, 0.5*cm))
    
    # ========================================
    # MENTIONS LÉGALES
    # ========================================
    
    if profil.mentions_legales_devis:
        elements.append(Spacer(1, 0.5*cm))
        mentions_titre = Paragraph("<b>Conditions générales :</b>", style_normal)
        elements.append(mentions_titre)
        elements.append(Spacer(1, 0.3*cm))
        
        mentions = Paragraph(
            profil.mentions_legales_devis.replace('\n', '<br/>'),
            ParagraphStyle(
                'SmallText',
                parent=style_normal,
                fontSize=8,
                textColor=colors.grey
            )
        )
        elements.append(mentions)
    
    # ========================================
    # SIGNATURE
    # ========================================
    
    elements.append(Spacer(1, 1.5*cm))
    
    signature_data = [
        [
            Paragraph("<b>Signature du client</b><br/>(Précédée de 'Bon pour accord')", style_normal),
            Paragraph(f"<b>{profil.nom_entreprise}</b>", style_normal)
        ]
    ]
    
    signature_table = Table(signature_data, colWidths=[8.5*cm, 8.5*cm])
    signature_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    
    elements.append(signature_table)
    
    # ========================================
    # CONSTRUIRE LE PDF
    # ========================================
    
    doc.build(elements)
    
    # Récupérer le PDF du buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf

def generer_facture_pdf(echeance, profil):
    """
    Génère le PDF d'une facture pour une échéance
    
    Args:
        echeance: Instance de Echeance
        profil: Instance de ProfilEntreprise
    
    Returns:
        bytes: Contenu du PDF
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from io import BytesIO
    from datetime import datetime
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # ═══════════════════════════════════════
    # STYLES PERSONNALISÉS
    # ═══════════════════════════════════════
    style_title = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#6366f1'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    style_header = ParagraphStyle(
        'CustomHeader',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    style_normal = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6
    )
    
    # ═══════════════════════════════════════
    # EN-TÊTE ENTREPRISE
    # ═══════════════════════════════════════
    elements.append(Paragraph(profil.nom_entreprise or "Entreprise", style_title))
    elements.append(Spacer(1, 0.5*cm))
    
    # Infos entreprise
    if profil.adresse:
        elements.append(Paragraph(profil.adresse, style_normal))
    if profil.code_postal and profil.ville:
        elements.append(Paragraph(f"{profil.code_postal} {profil.ville}", style_normal))
    if profil.telephone:
        elements.append(Paragraph(f"Tél : {profil.telephone}", style_normal))
    if profil.email:
        elements.append(Paragraph(f"Email : {profil.email}", style_normal))
    if profil.siret:
        elements.append(Paragraph(f"SIRET : {profil.siret}", style_normal))
    
    elements.append(Spacer(1, 1*cm))
    
    # ═════════════════════════════════════════
    # TITRE FACTURE + TYPE
    # ═══════════════════════════════════════════
    type_facture_label = {
        'acompte': 'FACTURE D\'ACOMPTE',
        'solde': 'FACTURE DE SOLDE',
        'globale': 'FACTURE'
    }.get(echeance.facture_type, 'FACTURE')
    
    style_facture_title = ParagraphStyle(
        'FactureTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#ef4444'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    elements.append(Paragraph(type_facture_label, style_facture_title))
    elements.append(Paragraph(f"N° {echeance.numero_facture}", style_header))
    elements.append(Spacer(1, 0.5*cm))
    
    # ═══════════════════════════════════════
    # INFOS CLIENT + FACTURE
    # ═══════════════════════════════════════
    operation = echeance.operation
    client = operation.client
    
    data_info = [
        ['CLIENT', 'FACTURE'],
        [
            f"{client.nom} {client.prenom}\n{client.adresse or ''}\n{client.ville or ''}\n{client.telephone or ''}",
            f"Date d'émission : {echeance.facture_date_emission.strftime('%d/%m/%Y')}\nDate d'échéance : {echeance.date_echeance.strftime('%d/%m/%Y')}\nOpération : {operation.id_operation}"
        ]
    ]
    
    table_info = Table(data_info, colWidths=[8*cm, 8*cm])
    table_info.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#64748b')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
    ]))
    
    elements.append(table_info)
    elements.append(Spacer(1, 1*cm))
    
    # ═══════════════════════════════════════
    # DÉTAILS LIGNES (TOUTES LES INTERVENTIONS)
    # ═══════════════════════════════════════
    elements.append(Paragraph("Détail de la prestation", style_header))
    elements.append(Spacer(1, 0.3*cm))
    
    data_lignes = [['Description', 'Qté', 'Unité', 'PU HT', 'TVA', 'Total HT']]
    
    for intervention in operation.interventions.all():
        data_lignes.append([
            intervention.description,
            f"{intervention.quantite:.2f}",
            intervention.get_unite_display(),
            f"{intervention.prix_unitaire_ht:.2f} €",
            f"{intervention.taux_tva:.0f}%",
            f"{intervention.montant:.2f} €"
        ])
    
    table_lignes = Table(data_lignes, colWidths=[7*cm, 1.5*cm, 2*cm, 2*cm, 1.5*cm, 2*cm])
    table_lignes.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table_lignes)
    elements.append(Spacer(1, 0.5*cm))
    
    # ═══════════════════════════════════════
    # TOTAUX
    # ═══════════════════════════════════════
    data_totaux = [
        ['Sous-total HT', f"{operation.sous_total_ht:.2f} €"],
        ['TVA', f"{operation.total_tva:.2f} €"],
        ['TOTAL TTC', f"{operation.total_ttc:.2f} €"],
    ]
    
    # ✅ AJOUT : Montant de cette facture (si acompte/solde)
    if echeance.facture_type in ['acompte', 'solde']:
        data_totaux.append(['', ''])  # Ligne vide
        data_totaux.append([f'Montant de cet {echeance.facture_type}', f"{echeance.montant:.2f} €"])
    
    table_totaux = Table(data_totaux, colWidths=[12*cm, 4*cm])
    table_totaux.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -2), 10),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#6366f1')),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#6366f1')),
        ('TOPPADDING', (0, -1), (-1, -1), 12),
    ]))
    
    elements.append(table_totaux)
    elements.append(Spacer(1, 1*cm))
    
    # ═══════════════════════════════════════
    # MENTIONS LÉGALES
    # ═══════════════════════════════════════
    if profil.mentions_legales_devis:
        elements.append(Spacer(1, 0.5*cm))
        style_mentions = ParagraphStyle(
            'Mentions',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#64748b'),
            leading=10
        )
        elements.append(Paragraph(profil.mentions_legales_devis.replace('\n', '<br/>'), style_mentions))
    
    # ═══════════════════════════════════════
    # GÉNÉRATION DU PDF
    # ═══════════════════════════════════════
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf