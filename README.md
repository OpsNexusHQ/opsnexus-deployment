# OpsNexus Deployment (`opsnexus-deployment`)

[![Release](https://img.shields.io/badge/release-v0.6.0-blue.svg)](https://github.com/OpsNexusHQ/opsnexus-deployment/releases/tag/v0.6.0)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://www.docker.com)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Official deployment infrastructure, Docker Compose configurations, and container setups for deploying **OpsNexus** in production or development environments.

The v0.6.0 tag is a deployment-component milestone for the Docker Compose stack. It is not, by itself, a coordinated platform release; use the [OpsNexus platform compatibility matrix](https://github.com/OpsNexusHQ/opsnexus-docs/blob/main/COMPATIBILITY.md) for supported component combinations.

---

## 🏛️ Production Deployment Topology

```text
Internet / Web Clients
         │
         ▼
 ┌───────────────┐
 │ Reverse Proxy │  (Nginx / Caddy with HTTPS)
 └───────┬───────┘
         │
 ┌───────┴──────────────────────────────────────────────┐
 │               Docker Compose Network                 │
 │                                                      │
 │ ┌───────────────────┐        ┌───────────────────┐   │
 │ │ opsnexus-dashboard│        │  opsnexus-backend │   │
 │ │  (React + Vite)   │        │   (Go Server)     │   │
 │ └───────────────────┘        └─────────┬─────────┘   │
 │                                        │             │
 │                              ┌─────────┴─────────┐   │
 │                              │    PostgreSQL     │   │
 │                              │   (Data Store)    │   │
 │                              └───────────────────┘   │
 └──────────────────────────────────────────────────────┘
                          ▲
                          │ HTTP Telemetry (10s)
               ┌──────────┴──────────┐
               │   opsnexus-agent    │  (Installed on target host)
               └─────────────────────┘
```

---

## 🚀 Quickstart: Docker Compose

### Step 1: Clone Repository
```bash
git clone https://github.com/OpsNexusHQ/opsnexus-deployment.git
cd opsnexus-deployment
```

### Step 2: Configure Environment
Copy `.env.example` to `.env` and set secure passwords:

```bash
cp .env.example .env
```

Example `.env`:
```ini
POSTGRES_USER=opsnexus_user
POSTGRES_PASSWORD=change_this_secure_password
POSTGRES_DB=opsnexus
OPSNEXUS_PORT=8080
OPSNEXUS_TELEMETRY_RETENTION=30
OPSNEXUS_API_AUTH_ENABLED=false
```

### Step 3: Launch Stack
```bash
docker-compose up -d
```

The stack starts:
- **PostgreSQL**: Port `5432` (internal)
- **OpsNexus Backend**: Port `8080`
- **OpsNexus Dashboard**: Port `5173`

---

## 🔐 Security Guidelines

1. **Never commit `.env` files** containing real passwords or secrets to source control.
2. **Enable TLS/HTTPS** in production using Nginx, Caddy, or Traefik as a reverse proxy in front of `OPSNEXUS_PORT`.
3. **Keep `opsnexus-agent` independently installed** on target host machines as a standalone Go binary or systemd service.

---

## 📄 License

Part of the [OpsNexus](https://github.com/OpsNexusHQ) ecosystem. Licensed under the MIT License.
