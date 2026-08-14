#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Récupère la position live COROS côté serveur (GitHub Action) et écrit live.json.
Aucune dépendance externe (stdlib uniquement).

Env attendus :
  COROS_ID  = valeur 'id'  du lien de partage COROS (.../share/sport-live?id=...&key=...)
  COROS_KEY = valeur 'key' du lien de partage COROS

Sortie : live.json = {"lat":..,"lon":..,"ts":..,"updated":..}
         ou {"status":"expired"} / {"status":"waiting"} selon l'état.

Ne fait jamais échouer le job (exit 0) : en cas de pépin réseau on n'écrit rien,
le fichier précédent reste en place.
"""
import os, sys, json, time, gzip
import urllib.request

QHOST = "fastfloweu.coros.com"   # hôte EU / regionId=3 (adapter si autre région)
TIMEOUT = 30

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gh-action-coros", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()

def write(obj):
    with open("live.json", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    print("live.json ->", obj)

def main():
    cid = os.environ.get("COROS_ID", "").strip()
    key = os.environ.get("COROS_KEY", "").strip()
    if not cid or not key:
        print("COROS_ID / COROS_KEY manquants (secrets).", file=sys.stderr)
        return  # exit 0 : rien à écrire

    # 1) API de découverte : id+key -> métadonnées + URL du fichier de position .gz
    qurl = "https://%s/sport/live/query?id=%s&key=%s&t=%d" % (QHOST, cid, key, int(time.time()*1000))
    try:
        data = json.loads(get(qurl).decode("utf-8", "replace"))
    except Exception as e:
        print("query KO:", e, file=sys.stderr); return
    tr = (data.get("data") or {}).get("sportLiveTrip")
    if not tr:
        print("pas de sportLiveTrip:", data.get("message")); return
    if tr.get("expired") == 1:
        write({"status": "expired", "updated": int(time.time())}); return
    lst = tr.get("locationFileList") or []
    if not lst:
        write({"status": "waiting", "updated": int(time.time())}); return

    # 2) fichier de position (dernier de la liste) -> dernier point
    gz_url = lst[-1].get("fileUrl")
    if not gz_url:
        print("fileUrl absent"); return
    gz_url += ("&" if "?" in gz_url else "?") + "t=%d" % int(time.time()*1000)
    try:
        raw = get(gz_url)
    except Exception as e:
        print("gz KO:", e, file=sys.stderr); return
    # .gz réellement compressé ? (magie 1f 8b) sinon texte brut
    if len(raw) >= 2 and raw[0] == 0x1f and raw[1] == 0x8b:
        try:
            text = gzip.decompress(raw).decode("utf-8", "replace")
        except Exception:
            text = raw.decode("utf-8", "replace")
    else:
        text = raw.decode("utf-8", "replace")

    # points séparés par ';' ; chaque point = lon*1e7,lat*1e7,ts_unix,...
    pts = [p for p in text.strip().split(";") if p.strip()]
    if not pts:
        write({"status": "waiting", "updated": int(time.time())}); return
    f = pts[-1].split(",")
    try:
        lon = float(f[0]) / 1e7
        lat = float(f[1]) / 1e7
        ts = int(float(f[2]))
    except Exception as e:
        print("parse point KO:", e, pts[-1], file=sys.stderr); return

    write({"lat": round(lat, 6), "lon": round(lon, 6), "ts": ts, "updated": int(time.time())})

if __name__ == "__main__":
    main()
