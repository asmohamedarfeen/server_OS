# Arfeen Cloud Deployment Architecture
## How Arfeen Cloud Controls the Entire Server

**Version:** 1.0

**Purpose**
This document explains how Arfeen Cloud will be deployed on the Ubuntu Server and how it will control the entire server without replacing Ubuntu itself.

---

# Overview

Arfeen Cloud is **not** the operating system.

Ubuntu Server remains the operating system.

Docker remains the container runtime.

Arfeen Cloud becomes the **Management Layer** above Ubuntu.

```
+------------------------------------------------------+
|                  Web Browser                         |
+------------------------------------------------------+
                    │
                    ▼
+------------------------------------------------------+
|                 Arfeen Cloud                         |
|              (Web Dashboard)                         |
+------------------------------------------------------+
                    │
        Internal REST API / WebSocket
                    │
                    ▼
+------------------------------------------------------+
|             Arfeen Cloud Backend                     |
+------------------------------------------------------+
                    │
        Docker SDK / Linux API / SSH / System API
                    │
                    ▼
+------------------------------------------------------+
| Ubuntu Server + Docker + System Services             |
+------------------------------------------------------+
```

The dashboard never talks directly to Linux.

Everything passes through the backend.

---

# Deployment Method

Arfeen Cloud itself will run inside Docker.

```
Ubuntu

↓

Docker

↓

Arfeen Cloud
```

Advantages

- Easy updates
- Easy backup
- Easy rollback
- Easy migration
- Isolated from the operating system

---

# Initial Installation

The installer script performs:

```
Install Docker

↓

Create Docker Network

↓

Create Volumes

↓

Start PostgreSQL

↓

Start Redis

↓

Start Backend

↓

Start Frontend

↓

Start Reverse Proxy

↓

Done
```

Everything becomes available from

```
https://server-ip
```

or

```
https://your-domain
```

---

# Components

## 1. Dashboard

Purpose

Professional Web UI

Responsibilities

- Login
- Dashboard
- Monitoring
- Application Management
- Database Management
- Settings

Technology

Next.js

---

## 2. Backend

Purpose

The Brain of Arfeen Cloud.

Responsibilities

- Execute commands
- Manage Docker
- Manage applications
- Read server information
- Authentication
- APIs

Technology

FastAPI

---

## 3. PostgreSQL

Stores

Applications

Deployments

Users

Logs Metadata

Settings

Projects

Configurations

---

## 4. Redis

Stores

Queues

Sessions

Background Tasks

Cache

---

## 5. Reverse Proxy

Responsibilities

HTTPS

SSL

Routing

Subdomains

Security

Recommended

Traefik

or

Nginx

---

# Communication

```
Dashboard

↓

Backend API

↓

Docker SDK

↓

Docker Engine

↓

Container
```

No Docker CLI is used from the browser.

Everything goes through Docker SDK.

---

# Server Control

The backend has permission to communicate with Docker.

```
/var/run/docker.sock
```

will be mounted into the backend container.

Example

```
Backend

↓

Docker SDK

↓

Create Container
```

instead of

```
docker run
```

This is exactly how Portainer works internally.

---

# Monitoring

Backend continuously reads

```
CPU

RAM

Disk

Network

Temperature

Docker

Services
```

using

Python

psutil

Docker SDK

Linux APIs

The frontend refreshes every few seconds.

---

# Deploying an Application

User clicks

```
New Application
```

↓

Select

GitHub

or

ZIP

↓

Backend receives request

↓

Framework Detection

↓

Generate Dockerfile

(if required)

↓

Build Image

↓

Create Container

↓

Create Network

↓

Create Volume

↓

Create Reverse Proxy

↓

Start Application

↓

Return Logs

↓

Application Live

---

# Framework Detection

Backend automatically detects

```
FastAPI

Flask

Django

React

Vue

Angular

Next.js

Node.js

Spring Boot

Go

PHP

Static Website
```

using

```
package.json

requirements.txt

pyproject.toml

pom.xml

go.mod

etc.
```

---

# Updating an Application

```
GitHub Push

↓

Webhook

↓

Git Pull

↓

Docker Build

↓

Stop Old Container

↓

Start New Container

↓

Health Check

↓

Traffic Switch

↓

Done
```

Zero manual work.

---

# ZIP Deployment

```
Upload ZIP

↓

Extract

↓

Detect Framework

↓

Build

↓

Deploy
```

---

# Docker Management

Dashboard

↓

List Containers

↓

Start

↓

Stop

↓

Restart

↓

Delete

↓

Terminal

↓

Logs

↓

Volumes

↓

Networks

Everything happens without opening SSH.

---

# Database Management

User clicks

```
Create Database
```

↓

Choose

PostgreSQL

MySQL

Redis

MongoDB

↓

Docker Container Created

↓

Credentials Generated

↓

Ready

---

# File Manager

Backend communicates with Linux

using

```
pathlib

os

shutil
```

Functions

Upload

Download

Rename

Delete

Move

Copy

Permissions

---

# Terminal

Browser

↓

WebSocket

↓

Backend

↓

Linux PTY

↓

Ubuntu Shell

Similar to

VS Code Terminal

---

# Logs

Backend collects

Application Logs

Docker Logs

Deployment Logs

System Logs

and streams them through WebSockets.

---

# Reverse Proxy

Automatically creates

```
app.local

↓

Container
```

or

```
poster.example.com

↓

Container
```

SSL certificates generated automatically.

---

# Security

Authentication

↓

JWT

↓

Backend Validation

↓

Permission Check

↓

Action

The frontend never executes commands directly.

---

# Storage Layout

```
/opt/arfeen-cloud

backend/

frontend/

docker/

scripts/

configs/

plugins/

logs/

storage/

backups/

database/

volumes/
```

---

# Docker Containers

```
Frontend

Backend

PostgreSQL

Redis

Traefik

Prometheus

Grafana (temporary)

Loki

Watchtower
```

Every component runs independently.

---

# APIs

Example

```
GET

/api/server

/api/docker

/api/apps

/api/storage

/api/databases

/api/logs

/api/terminal

/api/settings
```

---

# Application Lifecycle

```
Create

↓

Build

↓

Deploy

↓

Run

↓

Monitor

↓

Update

↓

Rollback

↓

Delete
```

---

# Why Docker Instead of Installing Everything?

Because Docker provides

- Isolation
- Easy updates
- Version control
- Rollback
- Backup
- Portability

If Ubuntu fails,

Install Ubuntu again

↓

Install Docker

↓

Restore volumes

↓

Everything works again.

---

# Recovery Plan

If the server crashes

```
Install Ubuntu

↓

Install Docker

↓

Clone Arfeen Cloud

↓

Restore PostgreSQL

↓

Restore Docker Volumes

↓

Start Stack

↓

Everything Returns
```

Target recovery time:
Less than 30 minutes.

---

# Future Improvements

- Plugin Marketplace
- Kubernetes Support
- Multiple Servers
- Load Balancer
- Backup Engine
- Notification Engine
- AI Deployment Engine
- Object Storage
- Secrets Manager
- Container Registry

---

# Final Goal

Arfeen Cloud should become the **only interface** required to manage the server.

Instead of using:

- Docker CLI
- SSH
- Portainer
- Grafana
- Nginx Proxy Manager
- Multiple dashboards

The user opens a single URL:

```
https://your-server
```

From there, they can:

- Deploy applications
- Manage Docker
- Create databases
- View logs
- Monitor the server
- Browse files
- Open a terminal
- Configure networking
- Manage SSL
- Control every service

without ever leaving the platform.

---

# Design Principle

> **Ubuntu runs the server. Docker runs the services. Arfeen Cloud runs everything else.**