# ================================
# core/views.py - Étape 1 : Dashboard avec KPI
# ================================

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Client, Operation

@login_required
def dashboard(request):
    try:
        # KPI simples et sécurisés
        nb_clients = Client.objects.filter(user=request.user).count()
        nb_operations = Operation.objects.filter(user=request.user).count()
        nb_en_attente_devis = Operation.objects.filter(user=request.user, statut='en_attente_devis').count()
        nb_a_planifier = Operation.objects.filter(user=request.user, statut='a_planifier').count()
        nb_realise = Operation.objects.filter(user=request.user, statut='realise').count()
        
        # Générer le HTML directement (pas de template pour éviter les erreurs)
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>CRM Artisans - Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #ffffff;
                    color: #333;
                }}
                
                .header {{
                    background: #ffffff;
                    color: #333;
                    padding: 1rem 2rem;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 1px solid #e1e5e9;
                }}
                
                .header h1 {{
                    font-size: 1.5rem;
                }}
                
                .user-info {{
                    font-size: 0.9rem;
                }}
                
                .container {{
                    max-width: 1200px;
                    margin: 2rem auto;
                    padding: 0 1rem;
                }}
                
                .page-title {{
                    font-size: 1.8rem;
                    color: #333;
                    margin-bottom: 2rem;
                }}
                
                .kpi-section {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 1.5rem;
                    margin-bottom: 2rem;
                }}
                
                .kpi-card {{
                    background: white;
                    padding: 1.5rem;
                    border-radius: 4px;
                    border: 1px solid #e1e5e9;
                }}
                
                .kpi-card h3 {{
                    color: #666;
                    font-size: 0.9rem;
                    margin-bottom: 0.5rem;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .kpi-value {{
                    font-size: 2rem;
                    font-weight: bold;
                    color: #333;
                }}
                
                .actions {{
                    background: white;
                    border: 1px solid #e1e5e9;
                    border-radius: 4px;
                    padding: 1.5rem;
                }}
                
                .actions h3 {{
                    margin-bottom: 1rem;
                    color: #333;
                }}
                
                .btn {{
                    padding: 0.6rem 1.2rem;
                    margin-right: 1rem;
                    background: #333;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    font-size: 0.9rem;
                    display: inline-block;
                    margin-bottom: 0.5rem;
                }}
                
                .btn:hover {{
                    background: #555;
                }}
                
                .btn-secondary {{
                    background: #f8f9fa;
                    color: #333;
                    border: 1px solid #e1e5e9;
                }}
                
                .btn-secondary:hover {{
                    background: #e9ecef;
                }}
                
                @media (max-width: 768px) {{
                    .header {{
                        flex-direction: column;
                        gap: 1rem;
                        text-align: center;
                    }}
                    
                    .container {{
                        padding: 0 0.5rem;
                    }}
                    
                    .kpi-section {{
                        grid-template-columns: 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <header class="header">
                <h1>CRM Artisans</h1>
                <div class="user-info">
                    Connecté : {request.user.username} | <a href="/logout/" style="color: #333;">Déconnexion</a>
                </div>
            </header>

            <div class="container">
                <h1 class="page-title">Tableau de bord</h1>
                
                <!-- Section KPI -->
                <div class="kpi-section">
                    <div class="kpi-card">
                        <h3>Nombre de clients</h3>
                        <div class="kpi-value">{nb_clients}</div>
                    </div>
                    
                    <div class="kpi-card">
                        <h3>Total opérations</h3>
                        <div class="kpi-value">{nb_operations}</div>
                    </div>
                    
                    <div class="kpi-card">
                        <h3>En attente devis</h3>
                        <div class="kpi-value">{nb_en_attente_devis}</div>
                    </div>
                    
                    <div class="kpi-card">
                        <h3>À planifier</h3>
                        <div class="kpi-value">{nb_a_planifier}</div>
                    </div>
                    
                    <div class="kpi-card">
                        <h3>Attente paiement</h3>
                        <div class="kpi-value">{nb_realise}</div>
                    </div>
                </div>

                <!-- Actions -->
                <div class="actions">
                    <h3>Actions rapides</h3>
                    <a href="/admin/core/operation/add/" class="btn">Nouvelle opération</a>
                    <a href="/admin/core/client/add/" class="btn-secondary btn">Nouveau client</a>
                    <a href="/admin/" class="btn-secondary btn">Interface complète</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HttpResponse(html_content)
        
    except Exception as e:
        # En cas d'erreur, retour à la version simple
        return HttpResponse(f"<h1>CRM Artisans</h1><p>Erreur temporaire. <a href='/admin/'>Accéder à l'admin</a></p><p>Erreur : {str(e)}</p>")