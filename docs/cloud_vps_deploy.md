# Guia de Deploy em Nuvem, VPS e Conexão Remota (PixelLayer MCP)

> **PixelLayer** (`pixellayer`) é um servidor Model Context Protocol (MCP) para processamento de imagens potencializado por inteligência artificial (remoção de fundo, conversão de formatos, otimização, redimensionamento e vetorização SVG).
> 
> Este documento fornece todos os **requisitos mínimos**, **passo a passo detalhado**, **avisos críticos de segurança** e **recomendações arquiteturais** para executar o PixelLayer remotamente em servidores virtuais privados (VPS) ou provedores de nuvem (Cloud Providers).

---

## 🧭 Índice

1. [Visão Geral e Arquitetura Remota](#1-visão-geral-e-arquitetura-remota)
2. [Requisitos Mínimos e Recomendados de Sistema](#2-requisitos-mínimos-e-recomendados-de-sistema)
3. [⚠️ Avisos Críticos e Cuidados Fundamentais](#3-️-avisos-críticos-e-cuidados-fundamentais)
   - [3.1. O Paradigma "Path-Only" e o Filesystem Remoto (Crítico!)](#31-o-paradigma-path-only-e-o-filesystem-remoto-crítico)
   - [3.2. Risco de Exposição Pública Sem Autenticação (DoS e Segurança)](#32-risco-de-exposição-pública-sem-autenticação-dos-e-segurança)
   - [3.3. Gerenciamento de Memória, OOM (Out Of Memory) e Swap](#33-gerenciamento-de-memória-oom-out-of-memory-e-swap)
   - [3.4. Persistência de Cache de Modelos (`models_cache/`)](#34-persistência-de-cache-de-modelos-models_cache)
   - [3.5. Confinamento em Workspaces Autorizados](#35-confinamento-em-workspaces-autorizados)
4. [Passo a Passo de Instalação e Deploy](#4-passo-a-passo-de-instalação-e-deploy)
   - [Opção 1: VPS Linux Nativa com Systemd e uv (Recomendado para VPS)](#opção-1-vps-linux-nativa-com-systemd-e-uv-recomendado-para-vps)
   - [Opção 2: Containerização com Docker e Docker Compose](#opção-2-containerização-com-docker-e-docker-compose)
   - [Opção 3: Provedores de Cloud com GPU Dedicada (RunPod, AWS, GCP, Vast.ai)](#opção-3-provedores-de-cloud-com-gpu-dedicada-runpod-aws-gcp-vastai)
5. [Recomendações para Conectar o Agente MCP Remotamente](#5-recomendações-para-conectar-o-agente-mcp-remotamente)
   - [Abordagem A: SSH Stdio Bridge (Máxima Segurança, Zero Portas Abertas)](#abordagem-a-ssh-stdio-bridge-máxima-segurança-zero-portas-abertas)
   - [Abordagem B: Rede Privada Mesh (Tailscale / WireGuard)](#abordagem-b-rede-privada-mesh-tailscale--wireguard)
   - [Abordagem C: Reverse Proxy Seguro com HTTPS e Bearer Token (Caddy / Nginx)](#abordagem-c-reverse-proxy-seguro-com-https-e-bearer-token-caddy--nginx)
   - [Abordagem D: Cloudflare Tunnel (Zero Trust)](#abordagem-d-cloudflare-tunnel-zero-trust)
6. [Estratégias para Lidar com o Filesystem Remoto (Sincronização de Imagens)](#6-estratégias-para-lidar-com-o-filesystem-remoto-sincronização-de-imagens)
7. [Checklist de Validação e Troubleshooting](#7-checklist-de-validação-e-troubleshooting)

---

## 1. Visão Geral e Arquitetura Remota

Por padrão, servidores MCP locais executam na mesma máquina que o cliente de IA (como Claude Code, Antigravity CLI, Cursor, Codex ou VS Code), utilizando transporte `stdio`.

No entanto, hospedar o **PixelLayer em uma VPS ou Nuvem** oferece vantagens operacionais expressivas:
- **Liberação de Recursos Locais**: Remove a carga de inferência de redes neurais pesadas (como BiRefNet e RMBG) da máquina de desenvolvimento local.
- **Aceleração por Hardware Dedicado**: Permite usufruir de GPUs potentes (ex: NVIDIA T4, L4, A10G, RTX 3060/4060) em servidores na nuvem, acelerando o recorte de fundo de ~4 segundos (CPU) para ~150-300 milissegundos (GPU).
- **Servidor Centralizado para Times e Pipelines CI/CD**: Um único servidor MCP remoto pode atender múltiplos desenvolvedores ou robôs de automação assíncrona.

```
+-------------------------------------------------------------------------+
| Máquina Local do Desenvolvedor (Laptop / Desktop)                       |
|                                                                         |
|  +---------------------------+        +------------------------------+  |
|  | Agente de IA (Claude/AGY) |        | Workspace Local de Imagens   |  |
|  +-------------+-------------+        +--------------+---------------+  |
+----------------|-------------------------------------|------------------+
                 | (MCP Protocol: SSH ou SSE/HTTPS)    | (Sync: Mutagen / SSHFS)
                 |                                     |
+----------------v-------------------------------------v------------------+
| Servidor Nuvem / VPS (Ubuntu / Debian / Docker)                         |
|                                                                         |
|  +---------------------------+        +------------------------------+  |
|  | PixelLayer MCP Server     |<------>| Workspace Confinado Remoto   |  |
|  | (FastMCP: stdio ou SSE)   |        | (/opt/pixellayer/workspace)  |  |
|  +-------------+-------------+        +------------------------------+  |
|                |                                                        |
|  +-------------v-------------+        +------------------------------+  |
|  | PyTorch Engine (CPU/CUDA) |<------>| Cache Local de Modelos       |  |
|  | BiRefNet, RMBG, IS-Net    |        | (models_cache/)              |  |
|  +---------------------------+        +------------------------------+  |
+-------------------------------------------------------------------------+
```

---

## 2. Requisitos Mínimos e Recomendados de Sistema

A carga de trabalho do PixelLayer envolve processamento raster (Pillow/OpenCV), vetorização (vtracer) e inferência em redes convolucionais profundas e transformadores de visão (PyTorch).

### 2.1. Tabela de Dimensionamento de Hardware

| Componente | Perfil Mínimo (CPU-Only / Testes) | Perfil Recomendado (CPU Produção) | Perfil de Alta Performance (GPU Dedicada) |
|---|---|---|---|
| **vCPU** | 2 vCPUs (x86_64 ou ARM64) | 4 vCPUs | 4+ vCPUs |
| **Memória RAM** | 4 GB + 4 GB Swap configurado | 8 GB RAM | 16 GB RAM |
| **Placa de Vídeo (GPU)** | Nenhuma (Inferência via CPU) | Nenhuma | 1x NVIDIA com 4 GB+ VRAM (T4, L4, RTX 3060/4060, A10G) |
| **VRAM Mínima** | N/A | N/A | 4 GB dedicados (ideal: 8 GB+) |
| **Armazenamento SSD** | 20 GB livres | 30 GB livres (NVMe) | 40+ GB livres (NVMe) |
| **Sistema Operacional** | Linux Ubuntu 22.04 / 24.04 LTS ou Debian 12 | Linux Ubuntu 22.04 / 24.04 LTS | Ubuntu 22.04 LTS com Drivers NVIDIA 535+ e CUDA 12.x |
| **Runtime Python** | Python 3.11 ou 3.12 (via `uv`) | Python 3.11 ou 3.12 | Python 3.11 ou 3.12 + PyTorch com suporte CUDA |

### 2.2. Consumo de VRAM por Família de Modelos

Ao carregar os modelos na GPU, o consumo aproximado de VRAM é:
- **`isnet-general`**: ~500 MB VRAM (modelo ultra-leve, ideal para GPUs de baixo custo).
- **`birefnet-general` / `birefnet-portrait`**: ~1.8 GB a 2.2 GB VRAM.
- **`birefnet-matting` / `birefnet-hr`**: ~2.5 GB a 3.5 GB VRAM (dependendo da resolução da imagem de entrada).
- **`rmbg-2.0`**: ~1.8 GB a 2.1 GB VRAM.

> 💡 **Nota de Economia (*Zero Idle*)**: Graças à arquitetura do PixelLayer, os modelos permanecem na memória apenas durante o processamento e são **descarregados automaticamente** após o tempo de inatividade configurado em `PIXELLAYER_MODEL_TTL` (padrão: 300 segundos / 5 minutos). Quando ocioso, o servidor consome menos de **90 MB de RAM** e **0% de VRAM**.

### 2.3. Dependências de Sistema Operacional (Linux)

O processador gráfico do OpenCV e do Pillow requer bibliotecas de suporte do sistema operacional. Certifique-se de instalar:
```bash
sudo apt update && sudo apt install -y \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    libgomp1
```

---

## 3. ⚠️ Avisos Críticos e Cuidados Fundamentais

Antes de colocar o servidor em produção na nuvem, leia atentamente as seguintes diretrizes para evitar falhas graves de operação ou segurança.

---

### 3.1. O Paradigma "Path-Only" e o Filesystem Remoto (Crítico!)

> 🚨 **Este é o detalhe mais importante para o usuário que deseja utilizar o MCP de forma remota!**

1. **Sem Base64**: Por design fundamental, o PixelLayer **não envia nem recebe bytes de imagem em base64** via protocolo MCP. O transporte trafega apenas metadados JSON e **caminhos de arquivo** (`file_path`). Isso é vital para não esgotar o limite de tokens da janela de contexto do LLM.
2. **Localização do Disco**: As ferramentas (`remove_background`, `optimize_image`, `vectorize_image`, etc.) leem e gravam imagens no **disco do servidor onde o PixelLayer está rodando**, e não na máquina local do cliente.
3. **O Erro Clássico**: Se o cliente MCP local enviar um comando solicitando o processamento de `input/minha_foto.png`, o PixelLayer buscará esse arquivo na VPS. Se a imagem estiver apenas no laptop do desenvolvedor, o servidor retornará `FILE_NOT_FOUND`.

#### Como Resolver o Acesso aos Arquivos?
Você deve adotar uma das 3 arquiteturas recomendadas descritas na [Seção 6](#6-estratégias-para-lidar-com-o-filesystem-remoto-sincronização-de-imagens):
- **Opção A (Recomendada)**: Sincronização contínua de workspace via **Mutagen** ou **SSHFS**.
- **Opção B (Nativa Cloud)**: Agente e servidor executando juntos na VPS (via terminal SSH, VS Code Remote SSH ou Devcontainer).
- **Opção C**: Armazenamento compartilhado via bucket S3 montado no servidor ou volume NFS.

---

### 3.2. Risco de Exposição Pública Sem Autenticação (DoS e Segurança)

> 🛑 **NUNCA execute o FastMCP com `host 0.0.0.0` exposto diretamente para a internet sem autenticação!**

- O protocolo FastMCP nativo em modo SSE ou HTTP não inclui autenticação por token ou controle de taxa de requisições por padrão.
- Se você abrir a porta `8000` publicamente para o mundo:
  - Qualquer bot na internet poderá invocar inferências de IA, consumindo 100% da sua CPU/GPU (**Ataque de Negação de Serviço / DoS**).
  - Um terceiro malicioso poderia ler ou sobrescrever imagens contidas dentro dos diretórios autorizados em `PIXELLAYER_ALLOWED_WORKSPACES`.
- **Como Proteger**:
  1. Utilizar **SSH Stdio Bridge** (porta HTTP nem sequer é aberta).
  2. Ou vincular ao IP de uma rede privada mesh (**Tailscale** ou **WireGuard**).
  3. Ou colocar atrás de um **Reverse Proxy (Caddy ou Nginx)** exigindo cabeçalho `Authorization: Bearer <seu-token>` e HTTPS obrigatório.

---

### 3.3. Gerenciamento de Memória, OOM (Out Of Memory) e Swap

- Ao rodar em servidores **sem GPU**, o PyTorch utiliza a memória RAM do sistema para carregar os pesos da rede neural e alocar tensores intermediários durante o processamento de imagens de alta resolução.
- Se a sua VPS possui apenas **2 GB ou 4 GB de RAM** e **não possui partição Swap**, o kernel do Linux acionará o **OOM-Killer** (*Out Of Memory Killer*), finalizando o processo do Python de forma abrupta com `Killed` ou código de saída `137`.
- **Mitigações Obrigatórias**:
  - Em VPS de 4 GB RAM, crie um arquivo Swap de 4 GB a 8 GB (veja comandos no passo a passo).
  - Mantenha `PIXELLAYER_MODEL_TTL=300` (ou menor, ex: `120`) para liberar memória rapidamente após o uso.
  - O parâmetro de segurança `PIXELLAYER_MAX_PIXELS=50000000` (padrão de 50 Megapixels) já vem ativado para barrar imagens descomprimidas gigantes (*Pixel Flood Attacks*).

---

### 3.4. Persistência de Cache de Modelos (`models_cache/`)

- Na primeira requisição de remoção de fundo com um modelo (ex: `birefnet-general`), o PixelLayer realiza o download automático dos pesos a partir do Hugging Face Hub (aproximadamente **1.5 GB a 2.5 GB** de download).
- Se você utiliza **containers Docker** ou instâncias de nuvem efêmeras (como RunPod Spot ou instâncias descartáveis) **sem mapeamento de volume persistente**, o download será refeito a cada reinicialização, causando atrasos de minutos e consumo desnecessário de tráfego de rede.
- **Solução**: Sempre aponte `PIXELLAYER_MODELS_CACHE` para um diretório permanente ou monte um volume Docker em `/app/models_cache`.

---

### 3.5. Confinamento em Workspaces Autorizados

- O PixelLayer possui proteção estrita contra *Path Traversal* através da função `resolve_safe_path()`.
- Por padrão, se a variável `PIXELLAYER_ALLOWED_WORKSPACES` não for definida, o servidor permite apenas caminhos relativos ao diretório atual de execução (`Path.cwd()`).
- Em servidores remotos, configure explicitamente a variável apontando para o diretório de trabalho onde as imagens serão processadas:
  ```bash
  export PIXELLAYER_ALLOWED_WORKSPACES="/opt/pixellayer/workspace;/dados/imagens"
  ```
- Tentativas de acessar diretórios fora da lista autorizada (ex: `../../etc/passwd` ou `/var/log`) serão barradas com erro `SECURITY_ERROR`.

---

## 4. Passo a Passo de Instalação e Deploy

Escolha uma das opções abaixo de acordo com a sua infraestrutura:

---

### Opção 1: VPS Linux Nativa com Systemd e uv (Recomendado para VPS)

Esta abordagem é a mais leve, consome menos memória que containers Docker e utiliza o `systemd` para garantir reinício automático em caso de reboot ou falha.

#### Passo 1.1: Atualizar o Sistema e Instalar Dependências
Conecte-se à sua VPS via SSH e instale os pacotes básicos:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git build-essential libgl1 libglib2.0-0 libgomp1 python3-pip
```

#### Passo 1.2: Configurar Memória Swap (Essencial para VPS <= 4 GB RAM)
Se a sua máquina possui 4 GB de RAM ou menos, ative 4 GB de Swap:
```bash
# Verificar se já existe swap ativo
free -h

# Criar e habilitar 4GB de swap caso não exista
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Tornar permanente entre reinicializações
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

#### Passo 1.3: Instalar o Gerenciador `uv`
O `uv` gerencia ambientes virtuais e dependências Python com velocidade até 10x superior ao pip tradicional:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

#### Passo 1.4: Criar Usuário de Serviço Dedicado
Por segurança, nunca execute serviços em segundo plano como `root`:
```bash
sudo useradd -m -s /bin/bash pixellayer
sudo mkdir -p /opt/pixellayer
sudo chown -R pixellayer:pixellayer /opt/pixellayer
```

#### Passo 1.5: Clonar o Repositório e Sincronizar Dependências
Execute como o usuário `pixellayer`:
```bash
sudo -u pixellayer -i
cd /opt/pixellayer
git clone https://github.com/seu-usuario/pixellayer.git .

# Instalar o uv no perfil do usuário pixellayer se necessário
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.cargo/env

# Sincronizar dependências do projeto
uv sync

# Criar pastas de persistência de logs, cache de modelos e workspace
mkdir -p logs models_cache workspace
exit
```

#### Passo 1.6: Criar o Arquivo de Variáveis de Ambiente
Crie o arquivo `/etc/pixellayer/pixellayer.env`:
```bash
sudo mkdir -p /etc/pixellayer
sudo tee /etc/pixellayer/pixellayer.env > /dev/null << 'EOF'
# Configurações do PixelLayer
PIXELLAYER_DEFAULT_MODEL=birefnet-general
PIXELLAYER_MODEL_TTL=300
PIXELLAYER_MODELS_CACHE=/opt/pixellayer/models_cache
PIXELLAYER_ALLOWED_WORKSPACES=/opt/pixellayer/workspace
PIXELLAYER_LOG_DIR=/opt/pixellayer/logs
PIXELLAYER_LOG_FILE=/opt/pixellayer/logs/pixellayer.log
PIXELLAYER_DEVICE=auto
PIXELLAYER_MAX_PIXELS=50000000

# Configurações do Servidor de Transporte
PIXELLAYER_TRANSPORT=stdio
PIXELLAYER_HOST=127.0.0.1
PIXELLAYER_PORT=8000

# Proteção contra DNS Rebinding e Cabeçalhos Host Autorizados
PIXELLAYER_ALLOWED_HOSTS=127.0.0.1:*;localhost:*;[::1]:*
PIXELLAYER_ENABLE_DNS_REBINDING=true
EOF

sudo chmod 600 /etc/pixellayer/pixellayer.env
sudo chown -R pixellayer:pixellayer /etc/pixellayer
```

> 💡 **Dica de Transporte**: Se você for conectar o agente via **SSH Bridge** (mais seguro), deixe `PIXELLAYER_TRANSPORT=stdio`. Se for utilizar **SSE com Reverse Proxy (Caddy/Nginx)**, altere para `PIXELLAYER_TRANSPORT=sse`.

#### Passo 1.7: Configurar o Serviço Systemd (Para Modo SSE / HTTP)
Se você for expor o serviço via SSE/HTTP localmente para um proxy reverso, registre a unidade do `systemd` em `/etc/systemd/system/pixellayer.service`. Note que o executável lê os parâmetros diretamente do `pixellayer.env`, permitindo alterar transporte e portas sem editar a unit:
```bash
sudo tee /etc/systemd/system/pixellayer.service > /dev/null << 'EOF'
[Unit]
Description=PixelLayer AI Image Processing MCP Server
After=network.target

[Service]
Type=simple
User=pixellayer
Group=pixellayer
WorkingDirectory=/opt/pixellayer
EnvironmentFile=/etc/pixellayer/pixellayer.env
ExecStart=/opt/pixellayer/.venv/bin/python -m src.mcp_server
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Isolamento e Limites de Recursos
MemoryMax=7G
CPUQuota=350%

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pixellayer
sudo systemctl start pixellayer
```

Verifique o status do serviço e o endpoint de health check:
```bash
sudo systemctl status pixellayer

# Testar health check local (retorna HTTP 200 sem carregar pesos de IA)
curl -s http://127.0.0.1:8000/health | jq .
# Esperado: {"status": "healthy", "service": "pixellayer", "version": "0.1.0"}

# Acompanhar logs em tempo real:
journalctl -u pixellayer -f
```

---

### Opção 2: Containerização com Docker e Docker Compose

O deploy com Docker padroniza o ambiente e isola todas as dependências em containers descartáveis com volumes persistentes.

#### Passo 2.1: Estrutura do Dockerfile
Um `Dockerfile` otimizado está disponível na raiz do repositório com suporte a `uv.lock`, multi-stage, usuário não-root (UID 1000) e health check:
```dockerfile
FROM python:3.11-slim

# Instalar dependências gráficas essenciais do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instalar o uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Criar usuário sem privilégios de root
RUN useradd -m -u 1000 pixellayer
WORKDIR /app

# Copiar arquivos de dependências e lockfile para cache de camadas determinístico
COPY pyproject.toml uv.lock* README.md ./
RUN chown -R pixellayer:pixellayer /app

USER pixellayer

# Instalar dependências de produção no ambiente virtual do container
RUN uv sync --frozen --no-dev --no-install-project

# Copiar código-fonte da aplicação
COPY --chown=pixellayer:pixellayer src/ ./src/

# Instalar o pacote do projeto
RUN uv sync --frozen --no-dev

# Criar diretórios de persistência
RUN mkdir -p /app/models_cache /app/logs /app/workspace

# Configurações padrão de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PIXELLAYER_MODELS_CACHE=/app/models_cache \
    PIXELLAYER_ALLOWED_WORKSPACES=/app/workspace \
    PIXELLAYER_LOG_DIR=/app/logs \
    PIXELLAYER_HOST=0.0.0.0 \
    PIXELLAYER_PORT=8000 \
    PIXELLAYER_TRANSPORT=sse

EXPOSE 8000

# Health check para garantir prontidão do serviço
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Executar servidor MCP via SSE
CMD ["python", "-m", "src.mcp_server", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
```

#### Passo 2.2: Execução com Docker Compose
Antes de subir os containers, crie as pastas no host e ajuste as permissões para o UID 1000 (`pixellayer`):
```bash
mkdir -p models_cache logs workspace
sudo chown -R 1000:1000 models_cache logs workspace
```

O arquivo `docker-compose.yml` pré-configurado:
```yaml
services:
  pixellayer:
    build: .
    container_name: pixellayer-mcp
    restart: unless-stopped
    # Amarre na porta 127.0.0.1 para que o container NÃO fique aberto na internet pública!
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./models_cache:/app/models_cache
      - ./logs:/app/logs
      - ./workspace:/app/workspace
    environment:
      - PIXELLAYER_TRANSPORT=sse
      - PIXELLAYER_HOST=0.0.0.0
      - PIXELLAYER_PORT=8000
      - PIXELLAYER_DEVICE=auto
      - PIXELLAYER_ALLOWED_WORKSPACES=/app/workspace
      - PIXELLAYER_MODEL_TTL=300
      - PIXELLAYER_MAX_PIXELS=50000000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

Para subir o serviço em segundo plano:
```bash
docker compose up -d
docker compose logs -f

# Verificar se o container está saudável
docker compose ps
```

#### Passo 2.3: Suporte a GPU NVIDIA no Docker
Caso o servidor possua placa de vídeo NVIDIA e o pacote `nvidia-container-toolkit` instalado, adicione o bloco de GPU no `docker-compose.yml` (ou use `-f docker-compose.gpu.yml`):
```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

---

### Opção 3: Provedores de Cloud com GPU Dedicada (RunPod, AWS, GCP, Vast.ai)

Se você utiliza plataformas especializadas em GPU para processar centenas ou milhares de imagens por dia:

1. **Escolha de Imagem Base**: Selecione templates prontos com **Ubuntu 22.04 + PyTorch 2.x + CUDA 12.x** (ex: `runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04`).
2. **Armazenamento de Rede Persistente (Network Volume)**:
   - Configure um volume de rede anexado (ex: `/workspace/`).
   - Clone o repositório dentro do volume e defina:
     ```bash
     export PIXELLAYER_MODELS_CACHE="/workspace/models_cache"
     export PIXELLAYER_ALLOWED_WORKSPACES="/workspace"
     ```
3. **Verificação de Aceleração**:
   - Confirme se a GPU está visível:
     ```bash
     python3 -c "import torch; print('CUDA Ativo:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
     ```
   - O PixelLayer detectará automaticamente a GPU (`PIXELLAYER_DEVICE=auto`) e realizará as inferências com aceleração de hardware.

---

## 5. Recomendações para Conectar o Agente MCP Remotamente

Existem quatro métodos comprovados para conectar seu assistente de IA local ao PixelLayer na nuvem:

---

### Abordagem A: SSH Stdio Bridge (Máxima Segurança, Zero Portas Abertas)

> 🌟 **Esta é a solução mais recomendada para a maioria dos desenvolvedores.**

Neste modelo, o seu cliente MCP local (Claude Code, Antigravity CLI, Cursor, etc.) conecta-se ao servidor através de uma sessão SSH criptografada e executa o comando `python -m src.mcp_server`.

**Vantagens**:
- Nenhuma porta web é aberta no firewall da VPS (apenas a porta 22 do SSH).
- Autenticação nativa e inviolável por chaves criptográficas SSH (`id_ed25519`).
- O servidor roda em modo `stdio`, idêntico à execução local.

#### Passo A.1: Configurar Chave SSH no Laptop
Adicione um alias simples no seu `~/.ssh/config` local:
```ssh-config
Host pixellayer-vps
    HostName 198.51.100.25
    User pixellayer
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Teste a conexão manual:
```bash
ssh pixellayer-vps "echo 'Conexao OK'"
```

#### Passo A.2: Configurar nos Agentes MCP

##### 1. Claude Code (`~/.claude.json` ou `.mcp.json`):
```json
{
  "mcpServers": {
    "pixellayer": {
      "command": "ssh",
      "args": [
        "-T",
        "pixellayer-vps",
        "cd /opt/pixellayer && /opt/pixellayer/.venv/bin/python -m src.mcp_server"
      ],
      "env": {
        "PIXELLAYER_ALLOWED_WORKSPACES": "/opt/pixellayer/workspace"
      }
    }
  }
}
```

##### 2. Antigravity CLI (`~/.gemini/config/mcp_config.json`):
```json
{
  "mcpServers": {
    "pixellayer": {
      "command": "ssh",
      "args": [
        "-T",
        "pixellayer-vps",
        "cd /opt/pixellayer && /opt/pixellayer/.venv/bin/python -m src.mcp_server"
      ]
    }
  }
}
```

##### 3. Codex CLI (`~/.codex/config.toml`):
```toml
[mcp_servers.pixellayer]
command = "ssh"
args = ["-T", "pixellayer-vps", "cd /opt/pixellayer && /opt/pixellayer/.venv/bin/python -m src.mcp_server"]
startup_timeout_sec = 60.0
tool_timeout_sec = 180.0
```

##### 4. OpenCode (`~/.config/opencode/opencode.json`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "pixellayer": {
      "type": "local",
      "command": [
        "ssh",
        "-T",
        "pixellayer-vps",
        "cd /opt/pixellayer && /opt/pixellayer/.venv/bin/python -m src.mcp_server"
      ],
      "enabled": true,
      "timeout": 180000
    }
  }
}
```

##### 5. Cursor / Windsurf / VS Code (`.cursor/mcp.json` ou `~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "pixellayer": {
      "command": "ssh",
      "args": [
        "-T",
        "pixellayer-vps",
        "cd /opt/pixellayer && /opt/pixellayer/.venv/bin/python -m src.mcp_server"
      ]
    }
  }
}
```

---

### Abordagem B: Rede Privada Mesh (Tailscale / WireGuard)

Se você prefere conexões HTTP/SSE contínuas sem abrir portas para a internet pública, conecte sua máquina local e a VPS em uma rede mesh com **Tailscale**:

1. Instale o Tailscale na VPS: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
2. Instale o Tailscale na sua máquina local.
3. Na VPS, configure o PixelLayer para escutar especificamente no IP da interface Tailscale:
   ```bash
   export PIXELLAYER_TRANSPORT=sse
   export PIXELLAYER_HOST="100.x.y.z" # IP atribuído pelo Tailscale à VPS
   export PIXELLAYER_PORT=8000
   ```
4. No seu agente MCP local, configure a URL direta:
   ```json
   {
     "mcpServers": {
       "pixellayer": {
         "url": "http://100.x.y.z:8000/sse"
       }
     }
   }
   ```
> ✅ **Segurança**: Somente dispositivos autenticados na sua rede Tailscale conseguem alcançar a porta `8000`.

---

### Abordagem C: Reverse Proxy Seguro com HTTPS e Bearer Token (Caddy / Nginx)

Caso precise disponibilizar o endpoint MCP na web através de um domínio público (ex: `https://mcp.seudominio.com/sse`):

> ⚠️ **Atenção Crítica: Proteção contra DNS Rebinding (Evitando Erro HTTP 421)**  
> O FastMCP implementa validação estrita do cabeçalho `Host` para impedir ataques de DNS rebinding. Quando rodando localmente em `127.0.0.1:8000`, ele aceita por padrão apenas requisições cujo `Host` coincida com `127.0.0.1:*` ou `localhost:*`.  
> Ao configurar seu Reverse Proxy (Caddy ou Nginx), garanta que o cabeçalho `Host` repassado ao upstream seja `127.0.0.1:8000`, **OU** defina a variável de ambiente no servidor:  
> `PIXELLAYER_ALLOWED_HOSTS="mcp.seudominio.com;mcp.seudominio.com:*"` (ou passe `--allowed-hosts mcp.seudominio.com`).

#### Exemplo com Caddy (Com Certificado SSL Automático Let's Encrypt)
Crie o arquivo `/etc/caddy/Caddyfile`:
```caddy
mcp.seudominio.com {
    # Health check público para monitoramento de uptime
    handle /health {
        reverse_proxy 127.0.0.1:8000 {
            header_up Host 127.0.0.1:8000
        }
    }

    # Endpoints do protocolo MCP protegidos por Bearer Token
    handle {
        @unauthorized {
            not header Authorization "Bearer <SEU_TOKEN_SECRETO_AQUI>"
        }
        respond @unauthorized "Unauthorized: Token Invalido" 401

        # Proxy para o FastMCP local sem buffer de SSE
        reverse_proxy 127.0.0.1:8000 {
            flush_interval -1
            header_up Host 127.0.0.1:8000
        }
    }
}
```

#### Exemplo com Nginx (SSL Certbot Let's Encrypt)
Crie o arquivo `/etc/nginx/sites-available/pixellayer`:
```nginx
server {
    listen 443 ssl http2;
    server_name mcp.seudominio.com;

    ssl_certificate /etc/letsencrypt/live/mcp.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.seudominio.com/privkey.pem;

    # Health check público
    location = /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host 127.0.0.1:8000;
    }

    # Endpoints MCP com Bearer Token obrigatório
    location / {
        if ($http_authorization != "Bearer <SEU_TOKEN_SECRETO_AQUI>") {
            return 401 '{"error": "Unauthorized: Missing or invalid MCP Bearer Token"}\n';
        }

        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;

        proxy_set_header Connection '';
        proxy_set_header Host 127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Exemplos de Configuração do Cliente MCP Remoto com Autenticação

##### 1. Claude Code (`~/.claude.json` ou `.mcp.json`):
```json
{
  "mcpServers": {
    "pixellayer": {
      "url": "https://mcp.seudominio.com/sse",
      "headers": {
        "Authorization": "Bearer <SEU_TOKEN_SECRETO_AQUI>"
      }
    }
  }
}
```

##### 2. Cursor / Windsurf / VS Code (`.cursor/mcp.json` ou `~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "pixellayer": {
      "url": "https://mcp.seudominio.com/sse",
      "headers": {
        "Authorization": "Bearer <SEU_TOKEN_SECRETO_AQUI>"
      }
    }
  }
}
```

##### 3. OpenCode (`~/.config/opencode/opencode.json`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "pixellayer": {
      "type": "remote",
      "url": "https://mcp.seudominio.com/sse",
      "headers": {
        "Authorization": "Bearer <SEU_TOKEN_SECRETO_AQUI>"
      },
      "enabled": true,
      "timeout": 180000
    }
  }
}
```

---

### Abordagem D: Cloudflare Tunnel (Zero Trust)

O **Cloudflare Tunnel (`cloudflared`)** cria uma conexão de saída criptografada da sua VPS para os servidores da Cloudflare, permitindo expor o serviço com proteção WAF e autenticação de perímetro sem abrir portas no firewall da VPS.

1. Instale o cliente `cloudflared` na VPS.
2. Crie um túnel apontando para `http://127.0.0.1:8000`.
3. Configure regras de política no **Cloudflare Zero Trust** exigindo validação de Service Token no cabeçalho HTTP.

---

## 6. Estratégias para Lidar com o Filesystem Remoto (Sincronização de Imagens)

Lembre-se: o PixelLayer processa arquivos no disco da VPS. Se você deseja editar e chamar o MCP a partir do seu laptop, use uma das seguintes estratégias:

### Estratégia 1: Mutagen (Sincronização Bidirecional em Tempo Real) - 🌟 Altamente Recomendada

O **Mutagen** é uma ferramenta de sincronização de arquivos de nível profissional que replica alterações entre o laptop e a VPS via SSH em milissegundos:

1. Instale o Mutagen no seu computador:
   ```bash
   # macOS
   brew install mutagen-io/mutagen/mutagen
   # Linux / WSL
   curl -Lo mutagen.tar.gz https://github.com/mutagen-io/mutagen/releases/latest/download/mutagen_linux_amd64.tar.gz
   ```
2. Inicie a sincronização da pasta de imagens do seu projeto com o workspace da VPS:
   ```bash
   mutagen sync create \
     --name=pixellayer-sync \
     --sync-mode=two-way-resolved \
     ./imagens \
     pixellayer-vps:/opt/pixellayer/workspace/imagens
   ```
3. **Fluxo de Trabalho**:
   - Você salva uma imagem em `./imagens/foto.jpg` no seu laptop.
   - O Mutagen espelha para a VPS em 0.1 segundo.
   - Seu agente chama o MCP remoto com caminho `imagens/foto.jpg`.
   - O PixelLayer processa na GPU da VPS e gera `imagens/foto_nobg.png`.
   - O Mutagen baixa imediatamente `imagens/foto_nobg.png` para seu laptop.
   - **Experiência 100% transparente!**

### Estratégia 2: Ambiente de Desenvolvimento Totalmente Remoto (Cloud-Native)

Em vez de sincronizar arquivos, execute o próprio ambiente de trabalho na VPS:
- Conecte o **VS Code Remote SSH** ou o **Cursor SSH** na VPS.
- Abra o terminal integrado e rode o seu agente de IA (como `claude` ou `antigravity-cli`) diretamente no servidor remoto.
- Os caminhos de arquivos já estarão no mesmo filesystem da máquina onde a GPU e o PixelLayer executam.

### Estratégia 3: Montagem de Diretório via SSHFS

Monte a pasta remota da VPS como uma pasta local no seu computador:
```bash
mkdir -p ~/mnt/pixellayer
sshfs pixellayer-vps:/opt/pixellayer/workspace ~/mnt/pixellayer -o reconnect,ServerAliveInterval=15
```

---

## 7. Checklist de Validação e Troubleshooting

Antes de liberar o servidor para uso da equipe, execute as seguintes verificações:

### 7.1. Checklist Rápido de Pré-Deploy
- [ ] O firewall permite apenas tráfego necessário (porta SSH 22, e porta 443 apenas se usar Caddy/Nginx).
- [ ] A porta `8000` está amarrada em `127.0.0.1` e **NÃO** está acessível publicamente via IP direto.
- [ ] O Swap de 4 GB+ foi configurado se a máquina tiver 4 GB ou menos de RAM.
- [ ] O diretório `models_cache/` reside em disco persistente.
- [ ] O `PIXELLAYER_ALLOWED_WORKSPACES` reflete exatamente a pasta compartilhada de trabalho.
- [ ] Os pacotes do sistema `libgl1` e `libglib2.0-0` foram instalados.

### 7.2. Diagnósticos de Falhas Comuns

| Sintoma / Erro | Causa Mais Provável | Ação Corretiva |
|---|---|---|
| **Processo finalizado com `Killed` ou código `137`** | OOM-Killer do Linux encerrou o Python por falta de RAM durante o download ou carga do modelo. | Configure 4 GB a 8 GB de memória Swap (`mkswap` / `swapon`) ou aumente a RAM da VPS para 8 GB. |
| **`FILE_NOT_FOUND` ao processar imagem** | O caminho enviado não existe no disco da VPS (dilema do filesystem remoto). | Utilize o **Mutagen** para sincronizar as imagens ou confirme se o arquivo foi enviado para a VPS antes de chamar a ferramenta. |
| **`SECURITY_ERROR: Access denied: path outside authorized workspaces`** | O caminho está fora das pastas permitidas. | Verifique se a variável `PIXELLAYER_ALLOWED_WORKSPACES` inclui o diretório de entrada e saída. |
| **Erro HTTP 421 `Invalid Host header`** | Mecanismo de segurança contra DNS Rebinding do FastMCP rejeitando o cabeçalho `Host` encaminhado pelo proxy reverso. | Configure `proxy_set_header Host 127.0.0.1:8000;` no Nginx, `header_up Host 127.0.0.1:8000` no Caddy, ou adicione o domínio em `PIXELLAYER_ALLOWED_HOSTS="mcp.seudominio.com;mcp.seudominio.com:*"`. |
| **`Permission denied` em volumes Docker (`logs/` ou `models_cache/`)** | O container executa sob o usuário não-root `pixellayer` (UID 1000) e os diretórios no host foram criados pelo root. | Execute no host: `sudo chown -R 1000:1000 models_cache logs workspace`. |
| **Erro `libGL.so.1: cannot open shared object file`** | Dependência nativa do OpenCV ausente no Linux. | Execute `sudo apt install -y libgl1 libglib2.0-0` na VPS. |
| **Timeout de requisição no primeiro uso do modelo** | O modelo está sendo baixado do Hugging Face pela primeira vez (~2 GB). | Aguarde a conclusão do download inicial. O arquivo ficará salvo em `models_cache/` e as próximas chamadas serão imediatas. |
| **Desconexão repentina no streaming SSE** | Proxy reverso (Nginx/Caddy/Cloudflare) aplicando buffering no stream HTTP. | Desative o buffer no proxy (`flush_interval -1` no Caddy, `proxy_buffering off;` no Nginx). |
| **Inferência lenta mesmo com GPU instalada** | PyTorch não compilado com suporte CUDA ou drivers desatualizados. | Teste `torch.cuda.is_available()`. Se retornar `False`, reinstale o PyTorch compatível com sua versão de CUDA (`pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`). |
| **Health Check falhando em orquestradores (K8s/Docker)** | Orquestrador tentando acessar endpoint MCP com autenticação Bearer ou protocolo incorreto. | Aponte a verificação de liveness/readiness para o endpoint HTTP nativo `GET /health`, que responde 200 OK instantaneamente sem exigir autenticação ou carregar modelos. |

---

## 8. Arquivos e Modelos Prontos para Uso

O repositório inclui modelos de configuração prontos para acelerar o seu deploy:
- [`Dockerfile`](../Dockerfile): Imagem Docker de produção baseada em Debian slim com suporte a uv e usuário não-root.
- [`docker-compose.yml`](../docker-compose.yml): Orquestração para containers com mapeamento de volumes persistentes.
- [`deploy/pixellayer.service`](../deploy/pixellayer.service): Arquivo de unidade pronto para o Systemd.
- [`deploy/pixellayer.env.example`](../deploy/pixellayer.env.example): Modelo de variáveis de ambiente de produção.
- [`deploy/Caddyfile`](../deploy/Caddyfile): Configuração pronta do Caddy com HTTPS automático e autenticação Bearer Token.
- [`deploy/nginx-pixellayer.conf`](../deploy/nginx-pixellayer.conf): Configuração de proxy reverso Nginx otimizado para Server-Sent Events (SSE).
