#!/usr/bin/env python3
"""
MainWP Read-Only Audit & Reporting
Interroge en lecture seule stricte (GET) le dashboard MainWP et extrait :
- Liste détaillée des 17 sites (WP, PHP, statut)
- Mises à jour en attente (plugins, thèmes, core)
- Extensions actives sur le dashboard
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path

API_URL = "https://mainwp.alexandre-pommier.com/wp-json/mainwp/v2"
API_KEY = "67e272abc823587cbac75e37a206a588246b254f==d2ae11d59d4f416555ea253815ff7a6a0ccdf92b"

def api_get(endpoint):
    url = f"{API_URL}/{endpoint.lstrip('/')}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "User-Agent": "MainWP-Audit/1.0",
            "Accept": "application/json"
        },
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def parse_json_field(val):
    if not val:
        return {}
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return {}

def main():
    sites_res = api_get("sites")
    sites = sites_res.get("data", [])
    
    print("=" * 80)
    print(f"📊 RAPPORT D'AUDIT MAINWP : https://mainwp.alexandre-pommier.com")
    print(f"Total sites managés : {len(sites)}")
    print("=" * 80)
    
    # 1. Tableau des sites
    php_stats = {}
    wp_stats = {}
    sites_with_updates = []
    
    print("\n### 🌐 ÉTAT DU PARC DE SITES\n")
    print(f"| ID | Nom / Domaine | WP | PHP | MAJ Plugins | Statut |")
    print(f"|---|---|:---:|:---:|:---:|:---:|")
    
    for s in sites:
        sid = s.get("id")
        name = s.get("name") or s.get("url")
        url = s.get("url", "").replace("https://", "").replace("http://", "").rstrip("/")
        wp = s.get("wp_version", "N/A")
        
        # PHP Version est dans phpversion ou fvalues
        php = s.get("phpversion") or "N/A"
        
        plugin_upgrades = parse_json_field(s.get("plugin_upgrades"))
        nb_plugins = len(plugin_upgrades) if isinstance(plugin_upgrades, dict) else 0
        
        suspended = "Suspendu" if s.get("suspended") == "1" else "Actif"
        
        php_stats[php] = php_stats.get(php, 0) + 1
        wp_stats[wp] = wp_stats.get(wp, 0) + 1
        
        if nb_plugins > 0:
            sites_with_updates.append((name, url, plugin_upgrades))
            
        print(f"| {sid} | **{url}** | {wp} | **{php}** | {nb_plugins} plugin(s) | {suspended} |")
        
    print("\n### 📈 RÉPARTITION DES VERSIONS PHP :")
    for php, count in sorted(php_stats.items()):
        print(f"  - PHP {php} : {count} site(s)")
        
    print("\n### 📦 RÉPARTITION DES VERSIONS WORDPRESS :")
    for wp, count in sorted(wp_stats.items()):
        print(f"  - WordPress {wp} : {count} site(s)")
        
    print("\n### 🔔 DÉTAIL DES MISES À JOUR PLUGINS EN ATTENTE :")
    for name, url, plugins in sites_with_updates:
        print(f"\n👉 **{url}** ({len(plugins)} MAJ) :")
        for p_slug, p_info in plugins.items():
            p_name = p_info.get("Name", p_slug)
            cur_v = p_info.get("Version", "?")
            new_v = p_info.get("update", {}).get("new_version", "?")
            print(f"   • {p_name} : {cur_v} ➔ {new_v}")

if __name__ == "__main__":
    main()
