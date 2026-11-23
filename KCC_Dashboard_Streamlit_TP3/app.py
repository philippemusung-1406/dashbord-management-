import matplotlib
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime

# ==============================================================================
# 1. CONFIGURATION DE LA PAGE & STYLE INDUSTRIEL KCC S.A.
# ==============================================================================
st.set_page_config(
    page_title="KCC S.A. | Pilotage & Fiabilisation des Transformateurs MT",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Palette Corporate Industriel : Bleu Marine, Ardoise, Cuivre/Ambre */
    .main {
        background-color: #F4F6F9;
    }
    .stApp header {
        background-color: #0F2537;
    }
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border-left: 5px solid #0F2537;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.90rem !important;
        font-weight: 600 !important;
        color: #4A5568 !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        color: #0F2537 !important;
    }
    .banner-header {
        background: linear-gradient(90deg, #0F2537 0%, #1B3B5A 70%, #B85D19 100%);
        padding: 20px 28px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(15, 37, 55, 0.15);
    }
    .banner-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    .banner-header p {
        margin: 5px 0 0 0;
        font-size: 0.95rem;
        color: #E2E8F0;
    }
    .section-card {
        background-color: #FFFFFF;
        padding: 18px;
        border-radius: 8px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        margin-bottom: 16px;
    }
    .kpi-target {
        font-size: 0.8rem;
        color: #718096;
        margin-top: -8px;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. CHARGEMENT, NETTOYAGE & CALCUL DU SCORE DE RISQUE (PROCÉDURE P02 & P09)
# ==============================================================================
@st.cache_data
def load_and_process_data(file_source):
    df = pd.read_excel(file_source)
    
    # Nettoyage des noms de colonnes (suppression des espaces superflus comme 'date ' ou 'aspet _gen')
    df.columns = df.columns.str.strip()
    
    # Harmonisation des colonnes texte
    text_cols = ['transfo_id', 'aspet _gen', 'niveau_huile(°c)', 'relais_buchh', 'buchings']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            if col != 'transfo_id':
                df[col] = df[col].str.lower()
                
    df['date'] = pd.to_datetime(df['date'])
    df['mois'] = df['date'].dt.to_period('M').astype(str)
    
    # Extraction du secteur / zone à partir de l'identifiant du transformateur
    def extract_zone(tid):
        if 'KTO' in tid:
            return 'Kamoto (KTO)'
        elif 'DI' in tid:
            return 'Dikuluwe / Mashamba (DI)'
        elif 'SKM' in tid:
            return 'SKM'
        elif 'LPH' in tid:
            return 'Luilu / LPH'
        else:
            return 'Autres Installations'
            
    df['secteur'] = df['transfo_id'].apply(extract_zone)
    
    # --------------------------------------------------------------------------
    # CALCUL DYNAMIQUE DU SCORE DE RISQUE (Procédure P09 - Maintenance Prédictive)
    # Échelle sur 100 points :
    # - Niveau d'huile (30 pts) : rouge=30, jaune=15, vert=0
    # - Relais Buchholz (25 pts) : fuite=25, sale=10, propre=0
    # - Bushings / Traversées (20 pts) : fuite=20, propre=0
    # - Température d'huile (15 pts) : >55°C=15, 45-55°C=8, <45°C=0
    # - Silicagel % intégrité (10 pts) : <50%=10, 50-70%=5, >70%=0
    # --------------------------------------------------------------------------
    score_huile = df['niveau_huile(°c)'].map({'rouge': 30, 'jaune': 15, 'vert': 0}).fillna(0)
    score_buchh = df['relais_buchh'].map({'fuite': 25, 'sale': 10, 'propre': 0}).fillna(0)
    score_bushings = df['buchings'].map({'fuite': 20, 'propre': 0}).fillna(0)
    
    score_temp = np.where(df['temp_huile(°c)'] >= 55, 15,
                 np.where(df['temp_huile(°c)'] >= 45, 8, 0))
                 
    score_silicagel = np.where(df['silicagel(%)'] < 50, 10,
                      np.where(df['silicagel(%)'] <= 70, 5, 0))
                      
    df['score_risque'] = score_huile + score_buchh + score_bushings + score_temp + score_silicagel
    
    # Qualification de la gravité (Procédure P08 : Critique, Majeure, Mineure, Conforme)
    def classify_severity(row):
        if row['niveau_huile(°c)'] == 'rouge' or row['relais_buchh'] == 'fuite' or row['temp_huile(°c)'] >= 60 or row['score_risque'] >= 50:
            return 'Critique'
        elif row['niveau_huile(°c)'] == 'jaune' or row['buchings'] == 'fuite' or row['score_risque'] >= 25:
            return 'Majeure'
        elif row['aspet _gen'] == 'sale' or row['relais_buchh'] == 'sale' or row['silicagel(%)'] <= 70 or row['score_risque'] > 0:
            return 'Mineure'
        else:
            return 'Conforme'
            
    df['statut_anomalie'] = df.apply(classify_severity, axis=1)
    df['est_conforme'] = (df['statut_anomalie'] == 'Conforme').astype(int)
    df['a_fuite'] = ((df['relais_buchh'] == 'fuite') | (df['buchings'] == 'fuite')).astype(int)
    
    # Classement par criticité de puissance/impact (Procédure P02)
    df['criticite_equipement'] = np.where(df['puissance(kva)'] >= 1600, 'Critique (≥1600 kVA)',
                                 np.where(df['puissance(kva)'] >= 1000, 'Important (1000-1250 kVA)', 'Standard (<1000 kVA)'))
    
    return df

# ==============================================================================
# 3. BARRE LATÉRALE : SOURCE DYNAMIQUE & FILTRES INTERACTIFS
# ==============================================================================
with st.sidebar:
    st.markdown("### ⚡ KCC S.A. · Maintenance MT")
    st.caption("Projet de Fiabilisation (Déc. 2026 – Nov. 2027) | Master 2 Data Science · UDBL")
    st.divider()
    
    st.markdown("#### 📂 Source des Données (Temps Réel)")
    uploaded_file = st.file_uploader(
        "Importer un fichier Excel GMAO (.xlsx)",
        type=["xlsx"],
        help="Chargez un fichier mis à jour pour recalculer instantanément tous les KPI et alertes (Procédure P04 / P09)."
    )
    
    if uploaded_file is not None:
        df_raw = load_and_process_data(uploaded_file)
        st.success("✅ Dataset chargé dynamiquement !")
    else:
        try:
            df_raw = load_and_process_data("transfo_dataset .xlsx")
            st.info("ℹ️ Dataset par défaut : `transfo_dataset .xlsx`")
        except FileNotFoundError:
            st.error("❌ Fichier `transfo_dataset .xlsx` introuvable. Veuillez importer votre fichier Excel ci-dessus.")
            st.stop()
            
    st.divider()
    st.markdown("#### 🔍 Filtres de Pilotage")
    
    # Filtre Période
    min_date = df_raw['date'].min().date()
    max_date = df_raw['date'].max().date()
    date_range = st.date_input(
        "Période d'inspection",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    # Filtre Secteur
    secteurs = sorted(df_raw['secteur'].unique())
    selected_secteurs = st.multiselect("Secteurs d'exploitation", secteurs, default=secteurs)
    
    # Filtre Criticité équipement (P02)
    criticites = ['Critique (≥1600 kVA)', 'Important (1000-1250 kVA)', 'Standard (<1000 kVA)']
    selected_criticite = st.multiselect("Criticité Transformateur (P02)", criticites, default=criticites)
    
    # Filtre Transformateur spécifique
    transfos_dispo = sorted(df_raw['transfo_id'].unique())
    selected_transfos = st.multiselect("Transformateur(s) spécifique(s)", transfos_dispo, default=[])

# Application des filtres
if len(date_range) == 2:
    start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    mask = (df_raw['date'] >= start_d) & (df_raw['date'] <= end_d)
else:
    mask = pd.Series(True, index=df_raw.index)

mask &= df_raw['secteur'].isin(selected_secteurs)
mask &= df_raw['criticite_equipement'].isin(selected_criticite)
if selected_transfos:
    mask &= df_raw['transfo_id'].isin(selected_transfos)

df = df_raw[mask].copy()

if df.empty:
    st.warning("⚠️ Aucune donnée ne correspond aux filtres sélectionnés. Veuillez élargir votre sélection.")
    st.stop()

# ==============================================================================
# 4. EN-TÊTE EXÉCUTIF & SIMULATION DE SEUILS (PROCÉDURE P09)
# ==============================================================================
st.markdown("""
<div class="banner-header">
    <h1>⚡ Tableau de Bord de Fiabilisation des Transformateurs MT — KCC S.A.</h1>
    <p>Pilotage Opérationnel, Maintenance Prédictive (P09) & Suivi de la Performance (P12) · Élaboré par Musung Kambwandj Philippe</p>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 5. INDICATEURS CLÉS DE PERFORMANCE (KPI - TP1, TP2 & TP3)
# ==============================================================================
# Calcul des 6 KPI majeurs
nb_transfos_actifs = df['transfo_id'].nunique()
nb_transfos_parc = df_raw['transfo_id'].nunique()
taux_couverture_audit = (nb_transfos_actifs / nb_transfos_parc) * 100  # P01 (Cible 100%)

taux_conformite = (df['est_conforme'].mean()) * 100  # Santé globale check-list F02
taux_fuites = (df['a_fuite'].mean()) * 100  # TP1 Slide 13 : Taux de fuites d'huile (Buchholz + Bushings)
temp_moyenne = df['temp_huile(°c)'].mean()  # Thermique moyenne
silicagel_moyen = df['silicagel(%)'].mean()  # Protection contre l'humidité (P05)

# Dernier état connu par transformateur pour les alertes actives
latest_df = df.sort_values('date').groupby('transfo_id', as_index=False).last()
nb_alertes_critiques = (latest_df['statut_anomalie'] == 'Critique').sum()
score_risque_moyen = latest_df['score_risque'].mean()

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric(
        label="1. Parc Audité (P01)",
        value=f"{nb_transfos_actifs} / {nb_transfos_parc}",
        delta=f"{taux_couverture_audit:.1f}% (Cible: 100%)"
    )
with col2:
    st.metric(
        label="2. Conformité Check-list (F02)",
        value=f"{taux_conformite:.1f}%",
        delta=f"{taux_conformite - 90:.1f}% vs Cible 90%"
    )
with col3:
    st.metric(
        label="3. Taux de Fuites d'Huile",
        value=f"{taux_fuites:.1f}%",
        delta="Critique (Bushings/Buchholz)",
        delta_color="inverse"
    )
with col4:
    st.metric(
        label="4. Alertes Critiques Actives (P08)",
        value=f"{nb_alertes_critiques} Transfos",
        delta=f"Score Risque Moy: {score_risque_moyen:.1f}/100",
        delta_color="inverse" if nb_alertes_critiques > 0 else "normal"
    )
with col5:
    st.metric(
        label="5. Température Huile Moy.",
        value=f"{temp_moyenne:.1f} °C",
        delta=f"Max: {df['temp_huile(°c)'].max()} °C"
    )
with col6:
    st.metric(
        label="6. Intégrité Silicagel (P05)",
        value=f"{silicagel_moyen:.1f} %",
        delta="Cible Stock & État ≥ 80%"
    )

st.markdown("---")

# ==============================================================================
# 6. ONGLETS MÉTIERS ALIGNÉS SUR LES 4 OUTILS DU MANAGEMENT (TP3)
# ==============================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Vue Exécutive & Tendances (P12)",
    "🚨 Maintenance Prédictive & Alertes (P08 / P09)",
    "🔧 Diagnostic Composants & Check-list (F02 / P03)",
    "📋 Plan Stratégique, Procédures & Export (TP1 / TP2)"
])

# ------------------------------------------------------------------------------
# ONGLET 1 : VUE EXÉCUTIVE & TENDANCES MENSUELLES (REVUE MENSUELLE P12)
# ------------------------------------------------------------------------------
with tab1:
    c1, c2 = st.columns([1.4, 1])
    
    with c1:
        st.subheader("Évolution Mensuelle de la Conformité et des Anomalies (Revue P12)")
        monthly_trend = df.groupby('mois').agg(
            Inspections=('transfo_id', 'count'),
            Taux_Conformite=('est_conforme', lambda x: x.mean() * 100),
            Taux_Fuites=('a_fuite', lambda x: x.mean() * 100),
            Temp_Moy=('temp_huile(°c)', 'mean')
        ).reset_index()
        
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=monthly_trend['mois'], y=monthly_trend['Taux_Conformite'],
            mode='lines+markers+text', name='Taux de Conformité (%)',
            text=[f"{v:.1f}%" for v in monthly_trend['Taux_Conformite']],
            textposition="top center",
            line=dict(color='#0F2537', width=3)
        ))
        fig_trend.add_trace(go.Scatter(
            x=monthly_trend['mois'], y=monthly_trend['Taux_Fuites'],
            mode='lines+markers', name="Taux de Fuites d'Huile (%)",
            line=dict(color='#D9534F', width=2.5, dash='dash')
        ))
        fig_trend.add_hline(y=90, line_dash="dot", line_color="#2E7D32", annotation_text="Cible Préventif/Conformité (90%)")
        fig_trend.update_layout(
            height=380,
            margin=dict(l=20, r=20, t=30, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis_title="Pourcentage (%)",
            xaxis_title="Mois d'inspection",
            plot_bgcolor="white"
        )
        st.plotly_chart(fig_trend, use_container_width=True)
        
    with c2:
        st.subheader("Répartition de l'État du Parc (Dernier Relevé)")
        status_counts = latest_df['statut_anomalie'].value_counts().reset_index()
        status_counts.columns = ['Statut', 'Nombre']
        color_map = {
            'Conforme': '#2E7D32',
            'Mineure': '#F0AD4E',
            'Majeure': '#E67E22',
            'Critique': '#C0392B'
        }
        fig_donut = px.pie(
            status_counts, values='Nombre', names='Statut', hole=0.52,
            color='Statut', color_discrete_map=color_map
        )
        fig_donut.update_traces(textinfo='percent+value', textfont_size=13)
        fig_donut.update_layout(
            height=380,
            margin=dict(l=20, r=20, t=30, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_donut, use_container_width=True)
        
    st.subheader("Performance par Secteur d'Exploitation et Niveau de Criticité (P02)")
    sect_perf = latest_df.groupby(['secteur', 'criticite_equipement']).agg(
        Nb_Transfos=('transfo_id', 'count'),
        Score_Risque_Moyen=('score_risque', 'mean'),
        Puissance_Totale_kVA=('puissance(kva)', 'sum')
    ).reset_index()
    
    fig_bar_sect = px.bar(
        sect_perf, x='secteur', y='Nb_Transfos', color='criticite_equipement',
        barmode='stack', text_auto=True,
        color_discrete_map={
            'Critique (≥1600 kVA)': '#0F2537',
            'Important (1000-1250 kVA)': '#2B6CB0',
            'Standard (<1000 kVA)': '#90CDF4'
        },
        labels={'secteur': "Secteur d'exploitation", 'Nb_Transfos': 'Nombre de Transformateurs', 'criticite_equipement': 'Classe Criticité (P02)'}
    )
    fig_bar_sect.update_layout(height=340, plot_bgcolor="white", margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_bar_sect, use_container_width=True)

# ------------------------------------------------------------------------------
# ONGLET 2 : MAINTENANCE PRÉDICTIVE & SCORING DE RISQUE (PROCÉDURE P09 & P08)
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("🎯 Simulateur de Seuils d'Alerte Prédictive (Procédure P09)")
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        seuil_score = st.slider("Seuil d'alerte Score de Risque (/100)", min_value=10, max_value=80, value=30, step=5)
    with col_s2:
        seuil_temp = st.slider("Seuil d'alerte Température Huile (°C)", min_value=35, max_value=65, value=48, step=1)
    with col_s3:
        seuil_silicagel = st.slider("Seuil minimal Silicagel (%)", min_value=30, max_value=90, value=65, step=5)
        
    # Filtrage dynamique selon les seuils du simulateur
    alertes_df = latest_df[
        (latest_df['score_risque'] >= seuil_score) |
        (latest_df['temp_huile(°c)'] >= seuil_temp) |
        (latest_df['silicagel(%)'] <= seuil_silicagel)
    ].sort_values(by=['score_risque', 'temp_huile(°c)'], ascending=False)
    
    st.info(f"🔔 **{len(alertes_df)} transformateur(s)** dépassent actuellement vos seuils configurés et nécessitent un Ordre de Travail (F05) selon la procédure P08.")
    
    col_p1, col_p2 = st.columns([1.2, 1])
    with col_p1:
        st.markdown("**Top 15 des Transformateurs par Score de Risque (Dernier relevé)**")
        top_risk = latest_df.sort_values('score_risque', ascending=False).head(15)
        fig_risk = px.bar(
            top_risk, x='score_risque', y='transfo_id', orientation='h',
            color='statut_anomalie',
            color_discrete_map={'Critique': '#C0392B', 'Majeure': '#E67E22', 'Mineure': '#F0AD4E', 'Conforme': '#2E7D32'},
            text='score_risque',
            labels={'score_risque': 'Score de Risque (/100)', 'transfo_id': 'Transformateur', 'statut_anomalie': 'Gravité (P08)'}
        )
        fig_risk.add_vline(x=seuil_score, line_dash="dash", line_color="#C0392B", annotation_text=f"Seuil ({seuil_score})")
        fig_risk.update_layout(yaxis={'categoryorder': 'total ascending'}, height=440, plot_bgcolor="white")
        st.plotly_chart(fig_risk, use_container_width=True)
        
    with col_p2:
        st.markdown("**Matrice Thermique vs Dégradation Silicagel**")
        fig_scatter = px.scatter(
            latest_df, x='temp_huile(°c)', y='silicagel(%)',
            size='puissance(kva)', color='statut_anomalie',
            hover_name='transfo_id',
            hover_data=['secteur', 'score_risque', 'niveau_huile(°c)', 'relais_buchh', 'buchings'],
            color_discrete_map={'Critique': '#C0392B', 'Majeure': '#E67E22', 'Mineure': '#F0AD4E', 'Conforme': '#2E7D32'},
            labels={'temp_huile(°c)': "Température Huile (°C)", 'silicagel(%)': "État Silicagel (%)"}
        )
        fig_scatter.add_vline(x=seuil_temp, line_dash="dot", line_color="red")
        fig_scatter.add_hline(y=seuil_silicagel, line_dash="dot", line_color="orange")
        fig_scatter.update_layout(height=440, plot_bgcolor="white")
        st.plotly_chart(fig_scatter, use_container_width=True)
        
    st.markdown("### 📋 Liste Prioritaire des Interventions à Déclencher (Formulaire F04 / F05)")
    cols_display = ['date', 'transfo_id', 'secteur', 'puissance(kva)', 'statut_anomalie', 'score_risque', 'niveau_huile(°c)', 'temp_huile(°c)', 'silicagel(%)', 'relais_buchh', 'buchings']
    st.dataframe(
        alertes_df[cols_display].style.background_gradient(subset=['score_risque'], cmap='OrRd'),
        use_container_width=True,
        hide_index=True
    )

# ------------------------------------------------------------------------------
# ONGLET 3 : DIAGNOSTIC DES COMPOSANTS & CHECK-LIST F02 (PROCÉDURE P03 & P05)
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("Analyse Détaillée des Points de Contrôle de la Check-list F02")
    
    c_comp1, c_comp2, c_comp3, c_comp4 = st.columns(4)
    
    with c_comp1:
        st.markdown("**1. Niveau d'Huile**")
        oil_counts = df['niveau_huile(°c)'].value_counts().reset_index()
        oil_counts.columns = ['État', 'Relevés']
        fig_oil = px.bar(oil_counts, x='État', y='Relevés', color='État',
                         color_discrete_map={'vert': '#2E7D32', 'jaune': '#F0AD4E', 'rouge': '#C0392B'}, text_auto=True)
        fig_oil.update_layout(height=280, showlegend=False, plot_bgcolor="white", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_oil, use_container_width=True)
        
    with c_comp2:
        st.markdown("**2. Relais Buchholz**")
        buchh_counts = df['relais_buchh'].value_counts().reset_index()
        buchh_counts.columns = ['État', 'Relevés']
        fig_buchh = px.bar(buchh_counts, x='État', y='Relevés', color='État',
                           color_discrete_map={'propre': '#2E7D32', 'sale': '#F0AD4E', 'fuite': '#C0392B'}, text_auto=True)
        fig_buchh.update_layout(height=280, showlegend=False, plot_bgcolor="white", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_buchh, use_container_width=True)
        
    with c_comp3:
        st.markdown("**3. Traversées (Bushings)**")
        bush_counts = df['buchings'].value_counts().reset_index()
        bush_counts.columns = ['État', 'Relevés']
        fig_bush = px.bar(bush_counts, x='État', y='Relevés', color='État',
                          color_discrete_map={'propre': '#2E7D32', 'fuite': '#C0392B'}, text_auto=True)
        fig_bush.update_layout(height=280, showlegend=False, plot_bgcolor="white", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_bush, use_container_width=True)
        
    with c_comp4:
        st.markdown("**4. Aspect Général (Corrosion/Propreté)**")
        asp_counts = df['aspet _gen'].value_counts().reset_index()
        asp_counts.columns = ['État', 'Relevés']
        fig_asp = px.bar(asp_counts, x='État', y='Relevés', color='État',
                         color_discrete_map={'propre': '#2E7D32', 'sale': '#F0AD4E'}, text_auto=True)
        fig_asp.update_layout(height=280, showlegend=False, plot_bgcolor="white", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_asp, use_container_width=True)
        
    st.divider()
    st.subheader("🔎 Fiche Individuelle & Historique d'un Transformateur (Procédure P01 / P04)")
    selected_unit = st.selectbox("Sélectionner un transformateur pour inspecter son historique complet :", sorted(df['transfo_id'].unique()))
    unit_df = df[df['transfo_id'] == selected_unit].sort_values('date')
    
    u_last = unit_df.iloc[-1]
    uc1, uc2, uc3, uc4, uc5 = st.columns(5)
    uc1.metric("Puissance Nominale", f"{u_last['puissance(kva)']} kVA")
    uc2.metric("Tension (Pri / Sec)", f"{u_last['tension_pri(v)']}V / {u_last['tension_sec(v)']}V")
    uc3.metric("Secteur", u_last['secteur'])
    uc4.metric("Score Risque Actuel", f"{u_last['score_risque']} / 100")
    uc5.metric("Statut Actuel", u_last['statut_anomalie'])
    
    fig_unit = go.Figure()
    fig_unit.add_trace(go.Scatter(x=unit_df['date'], y=unit_df['temp_huile(°c)'], mode='lines+markers', name='Température Huile (°C)', line=dict(color='#C0392B')))
    fig_unit.add_trace(go.Scatter(x=unit_df['date'], y=unit_df['silicagel(%)'], mode='lines+markers', name='Silicagel (%)', line=dict(color='#2B6CB0')))
    fig_unit.update_layout(height=320, title=f"Évolution Température & Silicagel — {selected_unit}", plot_bgcolor="white")
    st.plotly_chart(fig_unit, use_container_width=True)

# ------------------------------------------------------------------------------
# ONGLET 4 : PLAN STRATÉGIQUE (TP1), PROCÉDURES (TP2) & EXPORT RAPPORT (F10)
# ------------------------------------------------------------------------------
with tab4:
    col_m1, col_m2 = st.columns([1.3, 1])
    
    with col_m1:
        st.subheader("📅 Feuille de Route des 10 Actions du Plan de Fiabilisation (TP1)")
        plan_data = pd.DataFrame([
            {"Action": "1. Inventaire et audit complet des transformateurs", "Procédure": "P01", "Pilote": "RM / CE / TE", "Échéance": "31/12/2026", "Cible KPI": "100% audités", "Avancement (%)": round(taux_couverture_audit, 1)},
            {"Action": "2. Classement des transformateurs par criticité", "Procédure": "P02", "Pilote": "RM / COO", "Échéance": "31/01/2027", "Cible KPI": "100% classés", "Avancement (%)": 100.0},
            {"Action": "3. Plan de maintenance préventive standard", "Procédure": "P03", "Pilote": "RM / COO / PL", "Échéance": "28/02/2027", "Cible KPI": "Préventif ≥ 90%", "Avancement (%)": round(taux_conformite, 1)},
            {"Action": "4. Numérisation des inspections dans la GMAO", "Procédure": "P04", "Pilote": "RM / TG", "Échéance": "31/03/2027", "Cible KPI": "Saisie ≥ 95%", "Avancement (%)": 96.5},
            {"Action": "5. Constitution du stock de pièces critiques", "Procédure": "P05 / P13", "Pilote": "RM / MG / ACH", "Échéance": "31/03/2027", "Cible KPI": "Dispo ≥ 95%", "Avancement (%)": round(silicagel_moyen, 1)},
            {"Action": "6. Formation et habilitation des techniciens", "Procédure": "P06", "Pilote": "RM / FOR / HSE", "Échéance": "30/04/2027", "Cible KPI": "100% formés", "Avancement (%)": 85.0},
            {"Action": "7. Contrôles approfondis (huile, thermographie)", "Procédure": "P07 / P11", "Pilote": "RM / COO / ACH", "Échéance": "31/05/2027", "Cible KPI": "Parc critique couvert", "Avancement (%)": 60.0},
            {"Action": "8. Tableau de bord et maintenance prédictive", "Procédure": "P09", "Pilote": "RM / AD / TG", "Échéance": "30/06/2027", "Cible KPI": "Tableau de bord actif", "Avancement (%)": 100.0},
            {"Action": "9. Actions correctives sur transformateurs prioritaires", "Procédure": "P08 / P10", "Pilote": "RM / COO / SUP", "Échéance": "30/09/2027", "Cible KPI": "Anomalies critiques = 0", "Avancement (%)": round(max(0, 100 - (nb_alertes_critiques / max(1, nb_transfos_actifs) * 100)), 1)},
            {"Action": "10. Revue mensuelle KPI et comité trimestriel", "Procédure": "P12 / P14", "Pilote": "DIR / RM / CG", "Échéance": "30/11/2027", "Cible KPI": "12 rapports F10 émis", "Avancement (%)": 90.0}
        ])
        st.dataframe(
            plan_data.style.bar(subset=['Avancement (%)'], color='#2B6CB0', vmin=0, vmax=100),
            use_container_width=True,
            hide_index=True
        )
        
    with col_m2:
        st.subheader("📤 Export du Rapport Mensuel (Formulaire F10 - P12)")
        st.markdown("""
        Générez instantanément l'extraction consolidée pour la **Revue Mensuelle des KPI (F10)** et le **Comité Trimestriel (F11)** :
        - Synthèse des scores de risque par transformateur
        - Liste des anomalies critiques et majeures à traiter (F04)
        - Suivi d'avancement des 10 actions stratégiques
        """)
        
        def generate_excel_report():
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                latest_df.to_excel(writer, sheet_name='Etat_Parc_P09', index=False)
                alertes_df.to_excel(writer, sheet_name='Alertes_Prioritaires_F04', index=False)
                plan_data.to_excel(writer, sheet_name='Suivi_Plan_10_Actions', index=False)
            return output.getvalue()
            
        st.download_button(
            label="📥 Télécharger le Rapport Mensuel Consolidé (.xlsx)",
            data=generate_excel_report(),
            file_name=f"KCC_Rapport_Mensuel_F10_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        st.divider()
        st.markdown("**Rappel Gouvernance & Sécurité (P10)**")
        st.success("🛡️ **Ambition Zéro Accident :** Toute intervention sur un transformateur en alerte nécessite obligatoirement une **Autorisation de travail et fiche de consignation (F06)** validée par le Responsable HSE.")
