from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from io import BytesIO
from django.utils import timezone
import os


def generer_devis_pdf(operation, profil):
    """
    Génère un PDF de devis professionnel (mise en forme plus classique/pro)
    
    Args:
        operation: Instance de Operation
        profil: Instance de ProfilEntreprise
    
    Returns:
        bytes: contenu du PDF
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
        textColor=colors.HexColor("#111827"),
    )

    style_small = ParagraphStyle(
        "Small",
        parent=style_base,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4b5563"),
    )

    style_section_title = ParagraphStyle(
        "SectionTitle",
        parent=style_base,
        fontSize=10,
        leading=12,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#111827"),
        spaceBefore=8,
        spaceAfter=4,
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
    # EN-TÊTE : ENTREPRISE + BLOC DEVIS
    # ============================

    # --- Colonne gauche : entreprise ---
    left_cells = []

    # Logo éventuel
    # if profil.logo and os.path.exists(profil.logo.path):
    #     logo = Image(profil.logo.path, width=3 * cm, height=3 * cm)
    #     left_cells.append(logo)
    #     left_cells.append(Spacer(1, 0.2 * cm))

    nom_entreprise = profil.nom_entreprise or "Entreprise"
    left_cells.append(Paragraph(f"<b>{nom_entreprise}</b>", style_base))

    if profil.adresse:
        left_cells.append(
            Paragraph(profil.adresse.replace("\n", "<br/>"), style_small)
        )

    if profil.code_postal or profil.ville:
        left_cells.append(
            Paragraph(
                f"{profil.code_postal or ''} {profil.ville or ''}",
                style_small,
            )
        )

    if profil.siret:
        left_cells.append(
            Paragraph(f"SIRET : {profil.siret}", style_small)
        )

    if profil.telephone:
        left_cells.append(
            Paragraph(f"Tél : {profil.telephone}", style_small)
        )

    if profil.email:
        left_cells.append(
            Paragraph(f"Email : {profil.email}", style_small)
        )

    # TODO plus tard : forme juridique / TVA / RCS / RM
    # if getattr(profil, "forme_juridique", None):
    #     left_cells.append(Paragraph(profil.forme_juridique, style_small))
    # if getattr(profil, "tva_intracommunautaire", None):
    #     left_cells.append(Paragraph(f"TVA : {profil.tva_intracommunautaire}", style_small))

    # --- Colonne droite : bloc "DEVIS" ---
    date_emission = timezone.now().date()
    # TODO plus tard : utiliser operation.date_devis si tu l’ajoutes
    # date_emission = operation.date_devis or timezone.now().date()

    right_cells = [
        Paragraph("<b>DEVIS</b>", ParagraphStyle(
            "DocType",
            parent=style_base,
            fontSize=14,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#111827"),
            alignment=2,  # droite
            spaceAfter=4,
        )),
        Paragraph(f"N° {operation.numero_devis}", ParagraphStyle(
            "DocNumber",
            parent=style_base,
            alignment=2,
        )),
        Spacer(1, 0.1 * cm),
        Paragraph(
            f"Date d'émission : {date_emission.strftime('%d/%m/%Y')}",
            ParagraphStyle("RightSmall", parent=style_small, alignment=2),
        ),
        Paragraph(
            f"Validité : {operation.devis_validite_jours} jours",
            ParagraphStyle("RightSmall2", parent=style_small, alignment=2),
        ),
    ]

    if operation.devis_date_limite:
        right_cells.append(
            Paragraph(
                f"Valable jusqu'au : {operation.devis_date_limite.strftime('%d/%m/%Y')}",
                ParagraphStyle("RightSmall3", parent=style_small, alignment=2),
            )
        )

    header_table = Table(
        [[left_cells, right_cells]],
        colWidths=[10 * cm, 6 * cm],
        hAlign="LEFT",
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    elements.append(header_table)
    elements.append(Spacer(1, 0.5 * cm))

    # Petite ligne de séparation
    elements.append(Spacer(1, 0.1 * cm))
    elements.append(
        Table(
            [[Paragraph("", style_small)]],
            colWidths=[16 * cm],
            style=TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ]
            ),
        )
    )
    elements.append(Spacer(1, 0.5 * cm))

    # ============================
    # BLOC CLIENT / INFOS COMPLÉMENTAIRES
    # ============================

    client_block = [
        Paragraph("Client", style_section_title),
        Paragraph(
            f"{operation.client.nom} {operation.client.prenom}",
            style_base,
        ),
    ]

    if operation.adresse_intervention:
        client_block.append(
            Paragraph(
                operation.adresse_intervention.replace("\n", "<br/>"),
                style_base,
            )
        )

    if operation.client.telephone:
        client_block.append(
            Paragraph(f"Tél : {operation.client.telephone}", style_small)
        )

    if operation.client.email:
        client_block.append(
            Paragraph(f"Email : {operation.client.email}", style_small)
        )

    info_block = [
        Paragraph("Informations", style_section_title),
        Paragraph(
            f"Référence devis : {operation.numero_devis}",
            style_base,
        ),
    ]

    # TODO plus tard : conditions de paiement, délai d’exécution, etc.
    # if getattr(operation, "conditions_paiement", None):
    #     info_block.append(
    #         Paragraph(f"Conditions de paiement : {operation.conditions_paiement}", style_small)
    #     )

    info_table = Table(
        [[client_block, info_block]],
        colWidths=[10 * cm, 6 * cm],
        hAlign="LEFT",
    )
    info_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
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
    # OBJET DU DEVIS
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

    for intervention in interventions:
        table_data.append(
            [
                Paragraph(intervention.description or "", style_base),
                f"{intervention.quantite:,.2f}".replace(",", " ").replace(".", ","),
                intervention.get_unite_display(),
                f"{intervention.prix_unitaire_ht:,.2f} €".replace(",", " ").replace(".", ","),
                f"{intervention.taux_tva:,.0f}%".replace(".", ","),
                f"{intervention.montant:,.2f} €".replace(",", " ").replace(".", ","),
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
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),  # violet très pâle
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3730a3")),   # violet foncé lisible

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
            ]
        )
    )

    elements.append(lignes_table)
    elements.append(Spacer(1, 0.7 * cm))

    # ============================
    # TOTAUX
    # ============================

    totaux_data = [
        [
            Paragraph("Sous-total HT", style_totaux_label),
            Paragraph(
                f"{operation.sous_total_ht:,.2f} €".replace(",", " ").replace(".", ","),
                style_totaux_value,
            ),
        ],
        [
            Paragraph("TVA", style_totaux_label),
            Paragraph(
                f"{operation.total_tva:,.2f} €".replace(",", " ").replace(".", ","),
                style_totaux_value,
            ),
        ],
        [
            Paragraph("<b>TOTAL TTC</b>", style_totaux_label),
            Paragraph(
                f"<b>{operation.total_ttc:,.2f} €</b>".replace(",", " ").replace(".", ","),
                style_totaux_value,
            ),
        ],
    ]

    totaux_table = Table(
        totaux_data,
        colWidths=[4.5 * cm, 4.5 * cm],
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
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4ff")),
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
    # MENTIONS / CONDITIONS GÉNÉRALES
    # ============================

    if profil.mentions_legales_devis:
        elements.append(Paragraph("Conditions générales", style_section_title))
        elements.append(
            Paragraph(
                profil.mentions_legales_devis.replace("\n", "<br/>"),
                style_small,
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
        colWidths=[10 * cm, 6 * cm],
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
    # GÉNÉRATION
    # ============================

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
from io import BytesIO


def generer_facture_pdf(echeance, profil):
    """
    Génère une facture avec la même DA que le devis,
    en respectant une grille rigoureuse (9 cm / 7 cm).
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
    styles = getSampleStyleSheet()

    # =======================================================
    # STYLES (alignés sur le devis)
    # =======================================================
    style_base = ParagraphStyle(
        "Base",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )

    style_small = ParagraphStyle(
        "Small",
        parent=style_base,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4b5563"),
    )

    style_section_title = ParagraphStyle(
        "SectionTitle",
        parent=style_base,
        fontSize=10,
        leading=12,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#111827"),
        spaceBefore=8,
        spaceAfter=4,
    )

    style_totaux_label = ParagraphStyle(
        "TotauxLabel",
        parent=style_base,
        alignment=TA_RIGHT,
    )

    style_totaux_value = ParagraphStyle(
        "TotauxValue",
        parent=style_base,
        alignment=TA_RIGHT,
        fontName="Helvetica-Bold",
    )

    # =======================================================
    # DONNÉES
    # =======================================================
    operation = echeance.operation
    client = operation.client

    type_label = {
        "acompte": "FACTURE D'ACOMPTE",
        "solde": "FACTURE DE SOLDE",
        "globale": "FACTURE",
    }.get(echeance.facture_type, "FACTURE")

    # =======================================================
    # EN-TÊTE : ENTREPRISE / FACTURE (9 cm / 7 cm)
    # =======================================================
    left_cells = []
    nom_entreprise = profil.nom_entreprise or "Entreprise"

    left_cells.append(Paragraph(f"<b>{nom_entreprise}</b>", style_base))

    if profil.adresse:
        left_cells.append(
            Paragraph(profil.adresse.replace("\n", "<br/>"), style_small)
        )

    if profil.code_postal or profil.ville:
        left_cells.append(
            Paragraph(f"{profil.code_postal or ''} {profil.ville or ''}", style_small)
        )

    if profil.siret:
        left_cells.append(
            Paragraph(f"SIRET : {profil.siret}", style_small)
        )

    if profil.telephone:
        left_cells.append(
            Paragraph(f"Tél : {profil.telephone}", style_small)
        )

    if profil.email:
        left_cells.append(
            Paragraph(f"Email : {profil.email}", style_small)
        )

    # TODO plus tard : forme juridique, TVA, RCS / RM, etc.

    style_doc_type = ParagraphStyle(
        "DocType",
        parent=style_base,
        fontSize=14,
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    )
    style_doc_num = ParagraphStyle(
        "DocNum",
        parent=style_base,
        alignment=TA_RIGHT,
    )
    style_right_small = ParagraphStyle(
        "RightSmall",
        parent=style_small,
        alignment=TA_RIGHT,
    )

    right_cells = [
        Paragraph(type_label, style_doc_type),
        Paragraph(f"N° {echeance.numero_facture}", style_doc_num),
        Spacer(1, 0.1 * cm),
        Paragraph(
            f"Émise le : {echeance.facture_date_emission.strftime('%d/%m/%Y')}",
            style_right_small,
        ),
        Paragraph(
            f"Échéance : {echeance.date_echeance.strftime('%d/%m/%Y')}",
            style_right_small,
        ),
    ]

    header_table = Table(
        [[left_cells, right_cells]],
        colWidths=[9 * cm, 7 * cm],
        hAlign="LEFT",
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    elements.append(header_table)
    elements.append(Spacer(1, 0.4 * cm))

    # Ligne séparatrice pleine largeur
    elements.append(
        Table(
            [[Paragraph("", style_small)]],
            colWidths=[16 * cm],
            style=TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ]
            ),
        )
    )
    elements.append(Spacer(1, 0.5 * cm))

    # =======================================================
    # BLOC CLIENT / INFORMATIONS FACTURE (même grille)
    # =======================================================
    client_block = [
        Paragraph("Client", style_section_title),
        Paragraph(f"{client.nom} {client.prenom}", style_base),
    ]

    if client.adresse:
        client_block.append(
            Paragraph(client.adresse.replace("\n", "<br/>"), style_base)
        )

    if client.telephone:
        client_block.append(
            Paragraph(f"Tél : {client.telephone}", style_small)
        )

    if client.email:
        client_block.append(
            Paragraph(f"Email : {client.email}", style_small)
        )

    info_block = [
        Paragraph("Informations", style_section_title),
        Paragraph(f"Opération : {operation.id_operation}", style_base),
        Paragraph(f"Montant facturé : {echeance.montant:.2f} €", style_small),
        # TODO plus tard : conditions de paiement, mode de règlement, etc.
    ]

    info_table = Table(
        [[client_block, info_block]],
        colWidths=[9 * cm, 7 * cm],
        hAlign="LEFT",
    )
    info_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    elements.append(info_table)
    elements.append(Spacer(1, 0.7 * cm))

    # =======================================================
    # DÉTAIL DES LIGNES (tableau)
    # =======================================================
    data = [
        [
            Paragraph("<b>Description</b>", style_base),
            Paragraph("<b>Qté</b>", style_base),
            Paragraph("<b>Unité</b>", style_base),
            Paragraph("<b>P.U. HT</b>", style_base),
            Paragraph("<b>TVA</b>", style_base),
            Paragraph("<b>Total HT</b>", style_base),
        ]
    ]

    for intervention in operation.interventions.all():
        data.append(
            [
                Paragraph(intervention.description or "", style_base),
                f"{intervention.quantite:.2f}".replace(".", ","),
                intervention.get_unite_display(),
                f"{intervention.prix_unitaire_ht:.2f} €".replace(".", ","),
                f"{intervention.taux_tva:.0f}%",
                f"{intervention.montant:.2f} €".replace(".", ","),
            ]
        )

    table_lignes = Table(
        data,
        colWidths=[7 * cm, 1.5 * cm, 2 * cm, 2.5 * cm, 1.5 * cm, 3 * cm],
        hAlign="LEFT",
    )
    table_lignes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    elements.append(table_lignes)
    elements.append(Spacer(1, 0.7 * cm))

    # =======================================================
    # TOTAUX (alignés, compact)
    # =======================================================
    totaux = [
        ["Sous-total HT", f"{operation.sous_total_ht:.2f} €"],
        ["TVA", f"{operation.total_tva:.2f} €"],
        ["TOTAL TTC", f"{operation.total_ttc:.2f} €"],
    ]

    if echeance.facture_type in ["acompte", "solde"]:
        totaux.append(["", ""])
        totaux.append(
            [Paragraph(f"Montant de la facture<br/>({echeance.facture_type})", style_totaux_label),
            Paragraph(f"{echeance.montant:.2f} €", style_totaux_value)]
        )

    totaux_table = Table(
        totaux,
        colWidths=[5 * cm, 5 * cm],
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
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4ff")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#6366f1")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )

    elements.append(totaux_table)
    elements.append(Spacer(1, 0.8 * cm))

    # =======================================================
    # MENTIONS
    # =======================================================
    if profil.mentions_legales_devis:
        elements.append(Paragraph("Conditions générales", style_section_title))
        elements.append(
            Paragraph(
                profil.mentions_legales_devis.replace("\n", "<br/>"),
                style_small,
            )
        )
        elements.append(Spacer(1, 0.6 * cm))

    # =======================================================
    # SIGNATURE (même grille 9 / 7)
    # =======================================================
    signature_table = Table(
        [
            [
                Paragraph("<b>Signature du client</b>", style_base),
                Paragraph(f"<b>{nom_entreprise}</b>", style_base),
            ]
        ],
        colWidths=[9 * cm, 7 * cm],
        hAlign="LEFT",
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 18),
            ]
        )
    )

    elements.append(signature_table)

    # =======================================================
    # GÉNÉRATION
    # =======================================================
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
