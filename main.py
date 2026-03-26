from google.cloud import bigquery
import pandas as pd
import numpy as np
from email.mime.text import MIMEText
from datetime import datetime
import smtplib

# ============================================================
# LOGIQUE METIER – IDENTIQUE À TON SCRIPT ORIGINAL
# ============================================================

def d3(x1, y1, z1, x2, y2, z2):
    return np.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)

def proximite_spatiale(df):
    df = df.drop_duplicates(subset=["spot"])
    cleaned = df.to_dict("records")

    if len(cleaned) < 2:
        return False, [], {}, []

    distances = {}
    proches = set()
    recap = [{"spot": r["spot"], "x": r["x"], "y": r["y"], "z": r["z"]} for r in cleaned]

    for i in range(len(cleaned)):
        for j in range(i + 1, len(cleaned)):
            a, b = cleaned[i], cleaned[j]
            dist = d3(a["x"], a["y"], a["z"], b["x"], b["y"], b["z"])

            pair = " ↔ ".join(sorted([str(a["spot"]), str(b["spot"])]))
            distances[pair] = round(dist, 2)

            if dist <= 35:
                proches.add(a["spot"])
                proches.add(b["spot"])

    return len(proches) >= 2, list(proches), distances, recap

def seq_consecutives(progs):
    progs = sorted(list(set(progs)))
    if len(progs) < 2:
        return False, []

    groups = []
    cur = [progs[0]]

    for i in range(1, len(progs)):
        if progs[i] == progs[i - 1] + 1:
            cur.append(progs[i])
        else:
            if len(cur) >= 2:
                groups.append(cur)
            cur = [progs[i]]

    if len(cur) >= 2:
        groups.append(cur)

    return len(groups) > 0, groups

# ============================================================
# REQUÊTE BIGQUERY – REMPLACE TA PARTIE OUTLOOK / CSV
# ============================================================

QUERY = """
SELECT *
FROM `irn-71490-lab-57.Welding_PLS_SR.DataModel_Results_FRMCA_deriveprocess_description`
WHERE DeriveProcess = 'Dérive process sévère : vérifier en US la qualité du PSR'
"""

def load_bigquery():
    client = bigquery.Client()
    return client.query(QUERY).to_dataframe()

def load_refpsr():
    client = bigquery.Client()
    df = client.query("""
        SELECT 
            CAST(Spotname AS STRING) AS spot,
            CAST(X_Linx AS FLOAT64) AS x,
            CAST(Y_Linx AS FLOAT64) AS y,
            CAST(Z_Linx AS FLOAT64) AS z
        FROM `irn-71490-lab-57.Welding_PLS_SR.ref_psr_linx_welding`
    """).to_dataframe()
    df = df.drop_duplicates(subset=["spot", "x", "y", "z"])
    return df

# ============================================================
# TRAITEMENT METIER – IDENTIQUE À TA VERSION PYTHON
# ============================================================

def traitement(df_raw, df_ref):

    results = []

    for (robot, pji), g in df_raw.groupby(["UaiLabel", "pji"]):

        psr_ids = sorted(list(set(g["Spotname"].astype(str))))
        progs = sorted(list(set(g["progNo"])))

        df_coords = df_ref[df_ref["spot"].isin(psr_ids)].dropna()

        # CAS 1 : AU MOINS 2 COORDONNÉES
        if len(df_coords) >= 2:
            ok, proches, distances, recap = proximite_spatiale(df_coords)

            results.append({
                "Robot": robot,
                "PJI": pji,
                "Décision": "⚠️ CONTRÔLE US INDISPENSABLE" if ok else "✓ Pas de contrôle US",
                "Détail": f"Proximité : {proches}" if ok else "Distances OK"
            })

        else:
            ok, groups = seq_consecutives(progs)
            results.append({
                "Robot": robot,
                "PJI": pji,
                "Décision": "⚠️ CONTRÔLE US INDISPENSABLE" if ok else "✓ Ignoré (Pas de 3D/Séquence)",
                "Détail": f"Séquences : {groups}" if ok else "Pas d'alerte séquence"
            })

    return results

# ============================================================
# ENVOI DU MAIL – FORMATE LA SYNTHESE
# ============================================================

def send_mail(records):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    rows = "".join([
        f"<tr><td>{r['Robot']}</td><td>{r['PJI']}</td><td>{r['Décision']}</td><td>{r['Détail']}</td></tr>"
        for r in records
    ])

    html = f"""
    <h2>Rapport US automatique - Cloud Run</h2>
    <p>Généré le {timestamp}</p>
    <table border='1' cellspacing='0' cellpadding='6'>
        <tr><th>Robot</th><th>PJI</th><th>Décision</th><th>Détail</th></tr>
        {rows}
    </table>
    """

    msg = MIMEText(html, "html")
    msg["Subject"] = "Rapport US Cloud Run"
    msg["From"] = "noreply@googlecloud.com"
    msg["To"] = "ousama.abou-el-faraj-extern@renault.com"

    with smtplib.SMTP("smtp.sendgrid.net", 587) as smtp:
        smtp.starttls()
        smtp.login("apikey", "<SENDGRID_KEY>")
        smtp.send_message(msg)

# ============================================================
# HANDLER CLOUD RUN
# ============================================================

def main(request):

    df_raw = load_bigquery()
    df_ref = load_refpsr()

    results = traitement(df_raw, df_ref)

    df_res = pd.DataFrame(results)
    df_res["is_alert"] = df_res["Décision"].str.contains("⚠️")
    df_res = df_res.sort_values(["Robot", "PJI", "is_alert"], ascending=[True, True, False])
    df_res = df_res.drop_duplicates(subset=["Robot", "PJI"], keep="first")

    final_list = df_res[~df_res["Décision"].str.contains("Ignoré")].to_dict("records")

    if final_list:
        send_mail(final_list)

    return "OK", 200
