# core/pdf_generator.py

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, Image
)
from io import BytesIO
from django.conf import settings
from django.utils import timezone
import os


def generer_devis_pdf(operation, profil):
    """
    Génère un PDF de devis professionnel (mise en page améliorée)
    
    Args:
        operation: Instance de Operation
        profil: Instance de ProfilEntreprise
    
    Returns:
        bytes: Contenu du PDF
    """

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    elements = []

    # ============================
    # STYLES
    # ============================
    styles = getSampleStyleSheet()

    style_base = ParagraphStyle(
        "Base",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
    )

    style_small_grey = ParagraphStyle(
        "SmallGrey",
        parent=style_base,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#64748b"),
    )

    style_section_title = ParagraphStyle(
        "SectionTitle",
        parent=style_base,
        fontSize=11,
        leading=14,
        spaceBefore=6,
        spaceAfter=4,
        textColor=colors.HexColor("#111827"),
        fontName="Helvetica-Bold",
    )

    style_title_devis = ParagraphStyle(
        "TitleDevis",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=colors.HexColor("#6366f1"),
        alignment=1,  # centre
        spaceAfter=12,
        spaceBefore=6,
    )

    style_totaux_label = ParagraphStyle(
        "TotauxLabel",
        parent=style_base,
        alignment=2,  # droite
    )

    style_totaux_value = ParagraphStyle(
        "TotauxValue",
        parent=style_base,
        alignment=2,
        fontName="Helvetica-Bold",
    )

    # ============================
    # EN-TÊTE ENTREPRISE
    # ============================

    # Logo éventuel à gauche
    header_cells_left = []

    # Si tu ajoutes un logo plus tard :
    # if profil.logo and os.path.exists(profil.logo.path):
    #     logo = Image(profil.logo.path, width=3 * cm, height=3 * cm)
    #     header_cells_left.append(logo)
    #     header_cells_left.append(Spacer(1, 0.2 * cm))

    # Bloc texte entreprise
    entreprise_lines = []

    nom_entreprise = profil.nom_entreprise or "Entreprise"
    entreprise_lines.append(
        Paragraph(f"<b>{nom_entreprise}</b>", style_base)
    )

    # TODO: plus tard, tu pourras ajouter forme juridique ici :
    # if getattr(profil, "forme_juridique", None):
    #     entreprise_lines.append(
    #         Paragraph(profil.forme_juridique, style_small_grey)
    #     )

    if profil.adresse:
        entreprise_lines.append(
            Paragraph(profil.adresse.replace("\n", "<br/>"), style_small_grey)
        )

    if profil.code_postal or profil.ville:
        entreprise_lines.append(
            Paragraph(
                f"{profil.code_postal or ''} {profil.ville or ''}",
                style_small_grey,
            )
        )

    if profil.siret:
        entreprise_lines.append(
            Paragraph(f"SIRET : {profil.siret}", style_small_grey)
        )

    # TODO: plus tard : TVA / RCS / RM
    # if getattr(profil, "tva_intracommunautaire", None):
    #     entreprise_lines.append(
    #         Paragraph(f"TVA intracom. : {profil.tva_intracommunautaire}", style_small_grey)
    #     )
    # if getattr(profil, "rcs_ou_rm", None):
    #     entreprise_lines.append(
    #         Paragraph(profil.rcs_ou_rm, style_small_grey)
    #     )

    if profil.telephone:
        entreprise_lines.append(
            Paragraph(f"Tél : {profil.telephone}", style_small_grey)
        )

    if profil.email:
        entreprise_lines.append(
            Paragraph(f"Email : {profil.email}", style_small_grey)
        )

    header_cells_left.extend(entreprise_lines)

    # Colonne droite : bloc "DEMANDE / INFO DOC"
    date_emission = timezone.now().date()
    # Plus tard : tu pourras utiliser operation.date_devis
    # date_emission = operation.date_devis or timezone.now().date()

    header_right = [
        Paragraph("<b>DEVIS</b>", style_section_title),
        Paragraph(f"N° {operation.numero_devis}", style_base),
        Spacer(1, 0.2 * cm),
        Paragraph(
            f"Émis le : {date_emission.strftime('%d/%m/%Y')}",
            style_small_grey,
        ),
        Paragraph(
            f"Validité : {operation.devis_validite_jours} jours",
            style_small_grey,
        ),
    ]

    if operation.devis_date_limite:
        header_right.append(
            Paragraph(
                f"Valable jusqu'au : {operation.devis_date_limite.strftime('%d/%m/%Y')}",
                style_small_grey,
            )
        )

    # Table en-tête (2 colonnes)
    header_table = Table(
        [[header_cells_left, header_right]],
        colWidths=[9 * cm, 7 * cm],
        hAlign="LEFT",
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    elements.append(header_table)
    elements.append(Spacer(1, 0.5 * cm))

    # Gros titre central
    elements.append(Paragraph("DEVIS", style_title_devis))
    elements.append(Spacer(1, 0.3 * cm))

    # ============================
    # INFO CLIENT / INFO DEVIS
    # ============================

    client_lines = [
        Paragraph("<b>Client</b>", style_section_title),
        Paragraph(
            f"{operation.client.nom} {operation.client.prenom}",
            style_base,
        ),
    ]

    if operation.adresse_intervention:
        client_lines.append(
            Paragraph(
                operation.adresse_intervention.replace("\n", "<br/>"),
                style_base,
            )
        )

    if operation.client.telephone:
        client_lines.append(
            Paragraph(f"Tél : {operation.client.telephone}", style_small_grey)
        )

    if operation.client.email:
        client_lines.append(
            Paragraph(f"Email : {operation.client.email}", style_small_grey)
        )

    # Bloc info devis complémentaire (si tu veux séparer du header)
    info_devis_lines = [
        Paragraph("<b>Informations devis</b>", style_section_title),
        Paragraph(
            f"Référence opération : {operation.id_operation}",
            style_base,
        ),
    ]

    # TODO : plus tard, tu pourras ajouter conditions de paiement, etc.
    # if getattr(operation, "conditions_paiement", None):
    #     info_devis_lines.append(
    #         Paragraph(operation.conditions_paiement, style_small_grey)
    #     )

    info_table = Table(
        [[client_lines, info_devis_lines]],
        colWidths=[9 * cm, 7 * cm],
        hAlign="LEFT",
    )
    info_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    elements.append(info_table)
    elements.append(Spacer(1, 0.7 * cm))

    # ============================
    # OBJET
    # ============================
    elements.append(Paragraph("Objet du devis", style_section_title))
    elements.append(
        Paragraph(operation.type_prestation or "", style_base)
    )
    elements.append(Spacer(1, 0.5 * cm))

    # ============================
    # TABLEAU DES LIGNES
    # ============================

    table_data = [
        [
            Paragraph("<b>Description</b>", style_base),
            Paragraph("<b>Qté</b>", style_base),
            Paragraph("<b>Unité</b>", style_base),
            Paragraph("<b>P.U. HT</b>", style_base),
            Paragraph("<b>TVA</b>", style_base),
            Paragraph("<b>Total HT</b>", style_base),
        ]
    ]

    interventions = operation.interventions.all()

    for idx, intervention in enumerate(interventions):
        table_data.append(
            [
                Paragraph(intervention.description or "", style_base),
                f"{intervention.quantite:,.2f}".replace(",", " ").replace(
                    ".", ","
                ),
                intervention.get_unite_display(),
                f"{intervention.prix_unitaire_ht:,.2f} €".replace(
                    ",", " "
                ).replace(".", ","),
                f"{intervention.taux_tva:,.0f}%".replace(".", ","),
                f"{intervention.montant:,.2f} €".replace(",", " ").replace(
                    ".", ","
                ),
            ]
        )

    lignes_table = Table(
        table_data,
        colWidths=[7 * cm, 1.5 * cm, 2 * cm, 2.5 * cm, 1.5 * cm, 3 * cm],
        hAlign="LEFT",
    )
    lignes_table.setStyle(
        TableStyle(
            [
                # En-tête
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                # Corps
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
                # Bandes alternées
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ]
        )
    )

    elements.append(lignes_table)
    elements.append(Spacer(1, 0.7 * cm))

    # ============================
    # BLOC TOTAUX
    # ============================

    totaux_data = []

    totaux_data.append(
        [
            Paragraph("Sous-total HT", style_totaux_label),
            Paragraph(
                f"{operation.sous_total_ht:,.2f} €".replace(
                    ",", " "
                ).replace(".", ","),
                style_totaux_value,
            ),
        ]
    )

    totaux_data.append(
        [
            Paragraph("TVA", style_totaux_label),
            Paragraph(
                f"{operation.total_tva:,.2f} €".replace(
                    ",", " "
                ).replace(".", ","),
                style_totaux_value,
            ),
        ]
    )

    totaux_data.append(
        [
            Paragraph("<b>TOTAL TTC</b>", style_totaux_label),
            Paragraph(
                f"<b>{operation.total_ttc:,.2f} €</b>".replace(
                    ",", " "
                ).replace(".", ","),
                style_totaux_value,
            ),
        ]
    )

    totaux_table = Table(
        totaux_data,
        colWidths=[4 * cm, 4 * cm],
        hAlign="RIGHT",
    )
    totaux_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 0), (-1, -2), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2ff")),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#6366f1")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ]
        )
    )

    elements.append(totaux_table)
    elements.append(Spacer(1, 0.8 * cm))

    # ============================
    # NOTES
    # ============================

    if operation.devis_notes:
        elements.append(Paragraph("Notes", style_section_title))
        elements.append(
            Paragraph(
                operation.devis_notes.replace("\n", "<br/>"),
                style_base,
            )
        )
        elements.append(Spacer(1, 0.6 * cm))

    # ============================
    # MENTIONS LÉGALES
    # ============================

    if profil.mentions_legales_devis:
        elements.append(Paragraph("Conditions générales", style_section_title))
        elements.append(
            Paragraph(
                profil.mentions_legales_devis.replace("\n", "<br/>"),
                style_small_grey,
            )
        )
        elements.append(Spacer(1, 0.8 * cm))

    # ============================
    # SIGNATURE
    # ============================

    signature_data = [
        [
            Paragraph(
                "<b>Signature du client</b><br/><font size='7' color='#6b7280'>(Précédée de la mention manuscrite 'Bon pour accord')</font>",
                style_base,
            ),
            Paragraph(f"<b>{nom_entreprise}</b>", style_base),
        ]
    ]

    signature_table = Table(
        signature_data,
        colWidths=[9 * cm, 7 * cm],
        hAlign="LEFT",
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 18),
            ]
        )
    )

    elements.append(signature_table)

    # ============================
    # CONSTRUCTION DU PDF
    # ============================

    doc.build(elements)
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