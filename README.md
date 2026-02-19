# freebox-proxy

Proxy léger pour exposer l'API Freebox OS à [Homepage](https://gethomepage.dev/) via le widget `customapi`.

## Pourquoi ?

L'API Freebox nécessite un flow d'authentification HMAC-SHA1 (app_token → challenge → session_token) que Homepage ne peut pas gérer nativement. Ce proxy gère l'auth et expose des endpoints JSON simples.

## Endpoints

| Endpoint | Description |
|---|---|
| `/connection` | État connexion, débit down/up (Mbps), bande passante (Gbps), IP |
| `/system` | Températures CPU/Switch, ventilateur RPM, uptime, firmware |
| `/ftth` | Info fibre optique (SFP, puissance) |
| `/connection/full` | Toutes les infos combinées |
| `/register` | Enregistrement initial auprès de la Freebox |
| `/register/status` | Vérifier le statut d'enregistrement |

## Setup

### 1. Déployer

```yaml
# docker-compose.yml
services:
  freebox-proxy:
    image: ghcr.io/calaxo/freebox-proxy:latest
    container_name: freebox-proxy
    restart: unless-stopped
    ports:
      - "5656:5656"
    volumes:
      - freebox_data:/data
    network_mode: host
```

### 2. Enregistrer (une seule fois)

1. Ouvrir `http://<host>:5656/register`
2. Approuver sur l'écran LCD de la Freebox
3. Vérifier avec `http://<host>:5656/register/status`

### 3. Utiliser dans Homepage

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
```

## Build

L'image Docker est construite automatiquement par GitHub Actions lors d'un merge vers la branche `build` et publiée sur GHCR.
