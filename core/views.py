from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

@login_required
def dashboard(request):
    return HttpResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>CRM Artisans</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #333; }}
            .nav {{ margin: 20px 0; }}
            .nav a {{ margin-right: 20px; padding: 10px; background: #f0f0f0; text-decoration: none; color: #333; }}
        </style>
    </head>
    <body>
        <h1>CRM Artisans - Tableau de bord</h1>
        <p>Utilisateur connecté : <strong>{request.user.username}</strong></p>
        
        <div class="nav">
            <a href="/admin/">Interface d'administration</a>
            <a href="/logout/">Déconnexion</a>
        </div>
        
        <h3>Votre CRM est opérationnel !</h3>
        <p>Utilisez l'interface d'administration pour :</p>
        <ul>
            <li>Gérer vos clients</li>
            <li>Créer des opérations</li>
            <li>Ajouter des interventions</li>
            <li>Consulter l'historique</li>
        </ul>
    </body>
    </html>
    """)