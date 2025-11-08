<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Clients – CRM Artisans</title>
  <style>
    :root{
      --bg: #0b1220;
      --card: #0f172a;
      --muted: #94a3b8;
      --text: #e2e8f0;
      --primary: #6366f1; /* indigo */
      --success: #22c55e; /* green */
      --warning: #f59e0b; /* amber */
      --danger: #ef4444; /* red */
      --accent: #8b5cf6; /* violet */
      --ring: rgba(99,102,241,.35);
      --border: rgba(148,163,184,.15);
      --shadow: 0 10px 25px rgba(2,6,23,.3), 0 1px 0 rgba(255,255,255,.03) inset;

      /* Variables pour mode clair - alignées avec Dashboard */
      --bg-light: #f8fafc;
      --card-light: #ffffff;
      --text-light: #1e293b;
      --muted-light: #64748b;
      --border-light: rgba(30,41,59,.12);
      --shadow-light: 0 10px 25px rgba(30,41,59,.08), 0 1px 0 rgba(255,255,255,.8) inset;
    }

    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      background: radial-gradient(1200px 800px at 20% -10%, rgba(99,102,241,.12), transparent 40%),
                  radial-gradient(1000px 600px at 80% 10%, rgba(139,92,246,.12), transparent 40%),
                  var(--bg);
      color: var(--text);
      line-height: 1.5;
    }

    /* Header (identique Dashboard) */
    .header{ 
      position: sticky; top: 0; z-index: 40; 
      backdrop-filter: saturate(180%) blur(8px); 
      background: linear-gradient(180deg, rgba(15,23,42,.85), rgba(15,23,42,.65)); 
      border-bottom: 1px solid var(--border) 
    }
    .header-inner{ 
      max-width:1280px; margin:0 auto; padding:.85rem 1rem; 
      display:flex; align-items:center; gap:1rem; justify-content:space-between 
    }
    .brand{ display:flex; align-items:center; gap:.75rem; font-weight:700; letter-spacing:.2px }
    .logo{ 
      width:34px; height:34px; border-radius:10px; 
      background:linear-gradient(145deg, var(--primary), var(--accent)); 
      box-shadow: var(--shadow); display:grid; place-items:center 
    }
    .logo svg{ width:18px; height:18px; color:white }
    .nav{ display:flex; gap:.25rem; align-items:center }
    .nav a{ 
      text-decoration:none; color:var(--muted); padding:.55rem .8rem; 
      border-radius:10px; border:1px solid transparent 
    }
    .nav a:hover{ color:var(--text); background:rgba(148,163,184,.08); border-color:var(--border) }
    .nav a.active{ 
      color:white; background:rgba(99,102,241,.18); 
      border-color: rgba(99,102,241,.35); box-shadow: 0 0 0 2px var(--ring) 
    }
    .user{ display:flex; align-items:center; gap:.75rem; color:var(--muted); font-size:.95rem }
    .user form button{ 
      background:none; border:none; color:var(--muted); cursor:pointer; 
      text-decoration:underline; font:inherit 
    }

    /* Main */
    .container{ max-width:1280px; margin: 2rem auto; padding: 0 1rem }
    .page-title{ 
      font-size: clamp(1.4rem, 2.4vw, 2rem); font-weight:800; 
      letter-spacing:.2px; margin-bottom:.25rem 
    }
    .subtitle{ color:var(--muted); margin:0 0 1.25rem }

    /* Cards/sections */
    .section{ 
      background: linear-gradient(180deg, rgba(2,6,23,.6), rgba(2,6,23,.4)); 
      border:1px solid var(--border); border-radius:16px; padding:1rem; 
      box-shadow: var(--shadow); margin-top:1rem 
    }
    .section-header{ 
      display:flex; align-items:center; justify-content:space-between; gap:1rem; 
      padding:.4rem .35rem .9rem; border-bottom:1px dashed var(--border) 
    }
    .section-title{ display:flex; gap:.6rem; align-items:center; font-size:1.05rem; font-weight:700 }
    .badge{ 
      font-size:.75rem; color:var(--muted); padding:.15rem .5rem; 
      border-radius:999px; border:1px solid var(--border); 
      background: rgba(148,163,184,.08) 
    }

    /* Toolbar & buttons */
    .toolbar{ display:flex; gap:.5rem; flex-wrap:wrap }
    .btn{ 
      display:inline-flex; align-items:center; gap:.5rem; padding:.55rem .8rem; 
      border-radius:10px; border:1px solid var(--border); 
      background:rgba(148,163,184,.07); color:var(--text); 
      text-decoration:none; cursor:pointer; font:inherit 
    }
    .btn:hover{ background:rgba(148,163,184,.12) }
    .btn.primary{ 
      background:linear-gradient(180deg, rgba(99,102,241,.18), rgba(99,102,241,.12)); 
      border-color: rgba(99,102,241,.35); color: white 
    }
    .btn.danger{ 
      background: linear-gradient(180deg, rgba(239,68,68,.15), rgba(239,68,68,.1)); 
      border-color: rgba(239,68,68,.35); color: white 
    }
    .btn.sm{ padding:.4rem .6rem; border-radius:8px }

    /* Search - Version compacte */
    .search-compact{ display:flex; gap:.75rem; align-items:end; flex-wrap:wrap }
    .search-compact .field{ flex: 1; min-width: 250px }
    .search-compact .field .label{ margin-bottom: .4rem }
    .input{ 
      width:100%; padding:.65rem .8rem; border-radius:10px; 
      border:1px solid var(--border); background: rgba(2,6,23,.35); 
      color: var(--text); font:inherit 
    }
    .input::placeholder{ color: rgba(226,232,240,.55) }
    .input:focus{ 
      outline:none; box-shadow: 0 0 0 2px var(--ring); 
      border-color: rgba(99,102,241,.35) 
    }

    /* Table */
    .table-wrap{ overflow:auto; border-radius:12px; border:1px solid var(--border) }
    table{ width:100%; border-collapse: collapse; min-width: 980px }
    thead th{ 
      position:sticky; top:0; background: rgba(15,23,42,.9); backdrop-filter: blur(6px); 
      color:var(--muted); text-transform:uppercase; letter-spacing:.08rem; 
      font-size:.75rem; text-align:left; padding:.9rem .85rem; 
      border-bottom:1px solid var(--border) 
    }
    tbody td{ padding:.9rem .85rem; border-bottom:1px dashed var(--border); vertical-align: top }
    tbody tr:hover{ background: rgba(148,163,184,.05) }

    .client-id{ font-weight:700; color: var(--primary) }
    .client-name{ font-weight:600 }
    .muted{ color: var(--muted) }
    .nowrap{ white-space:nowrap }
    .chip{ 
      display:inline-flex; align-items:center; gap:.35rem; padding:.2rem .55rem; 
      border-radius:999px; font-size:.78rem; border:1px solid var(--border); 
      color: var(--muted); background: rgba(148,163,184,.08) 
    }
    .chip.tag{ 
      color:#c084fc; border-color: rgba(192,132,252,.35); 
      background: rgba(192,132,252,.08) 
    }

    .btn-view{ 
      display:inline-flex; align-items:center; gap:.35rem; padding:.4rem .7rem; 
      border-radius:8px; border:1px solid rgba(99,102,241,.35); 
      background: rgba(99,102,241,.15); color:white; text-decoration:none; font-size:.8rem 
    }
    .btn-view:hover{ box-shadow: 0 0 0 2px var(--ring) }

    /* Responsive: table -> cartes */
    @media (max-width: 780px){
      .search-compact{ flex-direction: column; align-items: stretch }
      .search-compact .field{ min-width: auto }
      .table-wrap{ border:none }
      table{ display:block }
      thead{ display:none }
      tbody{ display:grid; gap:.75rem }
      tbody tr{ 
        display:grid; gap:.45rem; border:1px solid var(--border); 
        border-radius:12px; padding:.85rem; background: rgba(2,6,23,.5) 
      }
      tbody td{ padding:.15rem 0; border:none }
      tbody td[data-label]{ color:var(--muted); font-size:.78rem }
    }

    /* Light mode - Aligné avec Dashboard */
    @media (prefers-color-scheme: light){
      :root{ 
        --bg: var(--bg-light); 
        --card: var(--card-light); 
        --text: var(--text-light); 
        --muted: var(--muted-light); 
        --border: var(--border-light); 
        --shadow: var(--shadow-light);
      }
      
      body{ 
        background: radial-gradient(1200px 800px at 20% -10%, rgba(99,102,241,.05), transparent 40%), 
                    radial-gradient(1000px 600px at 80% 10%, rgba(139,92,246,.05), transparent 40%), 
                    var(--bg) 
      }
      
      .header{ 
        background: linear-gradient(180deg, rgba(255,255,255,.9), rgba(255,255,255,.8));
        backdrop-filter: saturate(180%) blur(8px);
        border-bottom: 1px solid var(--border);
      }
      
      .section{ 
        background: var(--card); 
        border: 1px solid var(--border);
        box-shadow: var(--shadow);
      }
      
      .table-wrap{ 
        background: var(--card); 
        border: 1px solid var(--border) 
      }
      
      thead th{ 
        background: rgba(248,250,252,.95); 
        backdrop-filter: blur(6px);
        color: var(--muted) 
      }
      
      .input{ 
        background: #fff; 
        border-color: var(--border); 
        color: var(--text) 
      }
      .input::placeholder{ color: rgba(100,116,139,.6) }
      
      .nav a{ color: var(--muted) }
      .nav a:hover{ color: var(--text) }
      .nav a.active{ 
        color: var(--primary); 
        background: rgba(99,102,241,.08); 
        border-color: rgba(99,102,241,.2) 
      }
      
      .user{ color: var(--muted) }
      .user form button{ color: var(--muted) }
      
      .btn{ 
        background: rgba(148,163,184,.06); 
        color: var(--text);
        border: 1px solid var(--border);
      }
      .btn:hover{ background: rgba(148,163,184,.1) }
      
      .btn.primary{ 
        background: rgba(99,102,241,.1); 
        border-color: rgba(99,102,241,.2);
        color: var(--primary);
      }
      
      .btn.danger{ 
        background: rgba(239,68,68,.1); 
        border-color: rgba(239,68,68,.2);
        color: #dc2626;
      }
      
      .client-id{ color: var(--primary) }
      
      .chip{ 
        color: var(--muted);
        border: 1px solid var(--border);
        background: rgba(148,163,184,.04);
      }
      
      .chip.tag{ 
        color: #7c3aed; 
        border-color: rgba(124,58,237,.25); 
        background: rgba(124,58,237,.06);
      }
      
      .btn-view{ 
        background: rgba(99,102,241,.1); 
        border-color: rgba(99,102,241,.2);
        color: var(--primary);
      }
      
      tbody tr{ background: transparent }
      tbody tr:hover{ background: rgba(148,163,184,.03) }
      
      @media (max-width:780px){ 
        tbody tr{ 
          background: rgba(248,250,252,.8);
          border: 1px solid var(--border);
        } 
      }
    }
  </style>
</head>
<body>
  <header class="header">
    <div class="header-inner">
      <div class="brand">
        <div class="logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 14.5 12 4l8 10.5-8 5.5-8-5.5Z" stroke="currentColor" stroke-width="1.6"/>
          </svg>
        </div>
        <span>CRM Artisans</span>
      </div>
      <nav class="nav" aria-label="Navigation principale">
        <a href="{% url 'dashboard' %}">Accueil</a>
        <a href="{% url 'operations' %}">Opérations</a>
        <a href="{% url 'clients' %}" class="active">Clients</a>
      </nav>
      <div class="user">
        <span>{{ user.username }}</span>
        <form method="post" action="{% url 'logout' %}">
          {% csrf_token %}
          <button type="submit" title="Se déconnecter">Déconnexion</button>
        </form>
      </div>
    </div>
  </header>

  <main class="container">
    <h1 class="page-title">Gestion des clients</h1>
    <p class="subtitle">{{ total_clients }} client(s) trouvé(s)</p>

    <!-- Recherche -->
    <section class="section" aria-labelledby="search-title">
      <div class="section-header">
        <h2 class="section-title" id="search-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14Zm9 17-4.35-4.35" stroke="currentColor" stroke-width="1.6"/></svg>
          Recherche
        </h2>
      </div>
      <form method="GET" style="padding:.3rem .4rem .6rem">
        <div class="search-compact">
          <div class="field">
            <label class="label" for="recherche-input">Terme de recherche</label>
            <input class="input" id="recherche-input" type="text" name="recherche" value="{{ recherche }}" placeholder="Nom, prénom, email, téléphone, ville, adresse…">
          </div>
          <button type="submit" class="btn primary">Rechercher</button>
          <a href="{% url 'clients' %}" class="btn">Effacer</a>
        </div>
      </form>
    </section>

    <!-- Liste des clients -->
    <section class="section" aria-labelledby="clients-title">
      <div class="section-header">
        <h2 class="section-title" id="clients-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm7 9H5a2 2 0 0 1-2-2v-1a6 6 0 0 1 6-6h6a6 6 0 0 1 6 6v1a2 2 0 0 1-2 2Z" stroke="currentColor" stroke-width="1.6"/></svg>
          Clients <span class="badge">{{ total_clients }}</span>
        </h2>
        <div class="toolbar" aria-label="Filtres rapides">
          {% if filtre_ville %}<span class="chip tag">Ville: {{ filtre_ville }}</span>{% endif %}
          {% if filtre_tag %}<span class="chip tag">Tag: {{ filtre_tag }}</span>{% endif %}
          <a href="{% url 'client_create' %}" class="btn primary">Nouveau client</a>
        </div>
      </div>

      {% if clients %}
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Id Client</th>
              <th>Nom / Prénom</th>
              <th>Contact</th>
              <th>Adresse</th>
              <th>Ville</th>
              <th>Dernière opération</th>
              <th>Prochaine opération</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {% for client in clients %}
            <tr>
              <td class="client-id" data-label="Id">{{ client.id_client }}</td>
              <td data-label="Nom">
                <div class="client-name">{{ client.nom }} {{ client.prenom }}</div>
              </td>
              <td data-label="Contact">
                <div class="muted">
                  <a class="nowrap" href="tel:{{ client.telephone }}">{{ client.telephone }}</a><br>
                  {% if client.email %}
                    <small><a href="mailto:{{ client.email }}">{{ client.email }}</a></small>
                  {% endif %}
                </div>
              </td>
              <td data-label="Adresse"><small class="muted">{{ client.adresse|truncatechars:40 }}</small></td>
              <td data-label="Ville">{{ client.ville }}</td>
              <td data-label="Dernière op.">
                {% if client.derniere_op %}
                  <div class="muted">
                    <div>{{ client.derniere_op.type_prestation|truncatechars:24 }}</div>
                    <div class="nowrap">{{ client.derniere_op.date_creation|date:"d/m/Y" }}</div>
                  </div>
                {% else %}
                  <span class="muted">Aucune</span>
                {% endif %}
              </td>
              <td data-label="Prochaine op.">
                {% if client.prochaine_op %}
                  <div>
                    <div class="client-name">{{ client.prochaine_op.type_prestation|truncatechars:24 }}</div>
                    <div class="muted nowrap">
                      {% if client.prochaine_op.date_prevue %}
                        {{ client.prochaine_op.date_prevue|date:"d/m H:i" }}
                      {% else %}
                        <span class="chip">Non planifiée</span>
                      {% endif %}
                    </div>
                  </div>
                {% else %}
                  <span class="muted">Aucune</span>
                {% endif %}
              </td>
              <td data-label="Actions">
                <a href="{% url 'client_detail' client.id %}" class="btn-view" title="Voir le profil client">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 5C7 5 3.73 8.11 2 12c1.73 3.89 5 7 10 7s8.27-3.11 10-7c-1.73-3.89-5-7-10-7Zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8Z" stroke="currentColor" stroke-width="1.6"/></svg>
                  Voir
                </a>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
        <div class="section" style="text-align:center">
          <p style="color:var(--muted); padding:1rem">Aucun client ne correspond à votre recherche.</p>
          <div class="toolbar" style="justify-content:center; padding-bottom:.5rem">
            <a href="{% url 'client_create' %}" class="btn primary">Créer le premier client</a>
          </div>
        </div>
      {% endif %}
    </section>

    <!-- Pagination -->
    {% if page_obj %}
      <section class="section" style="display:flex; justify-content:space-between; align-items:center">
        <span class="muted">Page {{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
        <div class="toolbar">
          {% if page_obj.has_previous %}
            <a class="btn" href="?page={{ page_obj.previous_page_number }}&recherche={{ recherche }}">Précédent</a>
          {% endif %}
          {% if page_obj.has_next %}
            <a class="btn" href="?page={{ page_obj.next_page_number }}&recherche={{ recherche }}">Suivant</a>
          {% endif %}
        </div>
      </section>
    {% endif %}
  </main>

{% if messages %}
{% for message in messages %}
<div class="alert {{ message.tags }}">
  {{ message }}
</div>
{% endfor %}

<script>
setTimeout(function() {
  document.querySelectorAll('.alert').forEach(el => el.remove());
}, 3000); // 3 secondes
</script>
{% endif %}
</body>
</html>