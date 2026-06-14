# freebox-proxy

Proxy HTTP léger qui gère l'authentification Freebox OS et expose des endpoints JSON simples pour [Homepage](https://gethomepage.dev/) (widget `customapi`) ou n'importe quel autre client.

Inclut un watchdog de connectivité qui redémarre automatiquement la Freebox en cas de coupure internet prolongée.

## Contexte

L'API Freebox OS exige un flow d'authentification à trois étapes : obtention d'un `app_token` (approuvé manuellement sur l'écran LCD), récupération d'un challenge, puis calcul d'une signature HMAC-SHA1 pour ouvrir une session valide 10 minutes. Homepage ne peut pas gérer ce mécanisme nativement, d'où ce proxy.

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Statut du service, état d'enregistrement, liste des endpoints |
| `GET /connection` | État de la connexion, débits down/up (Mbps), bande passante (Gbps), IP publique |
| `GET /system` | Températures CPU/Switch, RPM ventilateur, uptime, version firmware |
| `GET /ftth` | Données fibre : présence SFP, puissance RX/TX |
| `GET /connection/full` | Connexion + système + FTTH en un seul appel (utile pour Homepage) |
| `GET /watchdog` | État du watchdog et sa configuration |
| `GET /reboot` | Déclenche un redémarrage manuel de la Freebox |
| `GET /register` | Démarre l'enregistrement initial |
| `GET /register/status` | Vérifie si l'autorisation a été accordée sur l'écran LCD |
| `GET /register/reset` | Supprime le token pour recommencer l'enregistrement |

La documentation complète des schémas de réponse est dans [`openapi.yaml`](openapi.yaml) (importable sur [editor.swagger.io](https://editor.swagger.io) sans installation).

## Démarrage rapide

### 1. Configurer l'environnement

```bash
cp .env.example .env
# Adapter les valeurs si nécessaire (le fichier est commenté)
```

### 2. Déployer avec Docker Compose

```yaml
services:
  freebox-proxy:
    image: ghcr.io/<your-github-user>/freebox-proxy:latest
    container_name: freebox-proxy
    restart: unless-stopped
    env_file: .env
    network_mode: host
    volumes:
      - freebox_data:/data

volumes:
  freebox_data:
```

`network_mode: host` est nécessaire : le ping du watchdog et les appels vers `mafreebox.freebox.fr` requièrent un accès direct au réseau local.

### 3. Enregistrer le proxy (une seule fois)

1. Ouvrir `http://<host>:5656/register`
2. Approuver la demande sur l'écran LCD de la Freebox
3. Confirmer avec `http://<host>:5656/register/status`

Pour activer le redémarrage automatique, activer la permission **"Modification des réglages"** dans l'interface Freebox (Paramètres > Gestion des accès > Applications).

### 4. Utiliser dans Homepage

```yaml
- Freebox:
    widget:
      type: customapi
      url: "http://<host>:5656/connection"
      mappings:
        - field:
            result: rate_down_mbps
          label: Download
          format: number
          suffix: " Mbps"
        - field:
            result: rate_up_mbps
          label: Upload
          format: number
          suffix: " Mbps"
```

## Watchdog

Le watchdog ping les IPs définies dans `WATCHDOG_CHECK_IPS` à intervalle régulier. Après `WATCHDOG_FAILURES_BEFORE_REBOOT` échecs consécutifs, il vérifie que la Freebox est joignable en LAN (pour distinguer une coupure internet d'une panne d'alimentation) avant d'envoyer la commande de redémarrage. Un cooldown de `WATCHDOG_COOLDOWN` secondes s'applique ensuite.

L'état en temps réel est visible sur `GET /watchdog`.

## Build local

```bash
docker build -t freebox-proxy .
docker run --network host -v freebox_data:/data freebox-proxy
```

L'image Docker est également construite et publiée sur GHCR automatiquement par GitHub Actions au merge d'une PR vers la branche `build`.
