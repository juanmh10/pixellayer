# Exposição do Servidor Local MCP (PixelLayer)

O **PixelLayer** (`pixellayer`) é projetado para rodar como um servidor local baseado em `stdio`, comunicando-se diretamente com o cliente/agente MCP.

> 🌐 **Deseja executar o PixelLayer remotamente em uma VPS ou Nuvem (Cloud)?**  
> Consulte o guia dedicado em [`docs/cloud_vps_deploy.md`](cloud_vps_deploy.md) com requisitos de hardware, passo a passo com Docker e Systemd, alertas de segurança e configurações de SSH Bridge e SSE.

---

## 1. Modos de Inicialização Local

### Usando `uv` (Recomendado)
```bash
uv run python -m src.mcp_server
```

### Usando ambiente virtual Python (`venv`)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m src.mcp_server
```

---

## 2. Configuração de Clientes MCP

Configure o **PixelLayer** no seu assistente ou ambiente de agente de IA preferido. Substitua `<path-to-pixellayer>` pelo caminho do repositório clonado e `<path-to-workspaces>` pelos diretórios autorizados para leitura e escrita de imagens.

### 2.1. Antigravity CLI (AGY)
**Arquivo de Configuração:** `~/.gemini/config/mcp_config.json` (JSON)

```json
{
  "mcpServers": {
    "pixellayer": {
      "command": "<path-to-pixellayer>/.venv/bin/python",
      "args": [
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "<path-to-pixellayer>",
        "PIXELLAYER_ALLOWED_WORKSPACES": "<path-to-workspaces>",
        "PIXELLAYER_LOG_DIR": "<path-to-pixellayer>/logs",
        "PIXELLAYER_MODEL_TTL": "300"
      }
    }
  }
}
```

*Ou utilizando `uv`:*
```json
{
  "mcpServers": {
    "pixellayer": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "<path-to-pixellayer>",
        "python",
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "PIXELLAYER_ALLOWED_WORKSPACES": "<path-to-workspaces>"
      }
    }
  }
}
```

### 2.2. Codex CLI
**Arquivo de Configuração:** `~/.codex/config.toml` (TOML)

```toml
[mcp_servers.pixellayer]
command = "<path-to-pixellayer>/.venv/bin/python"
args = ["-m", "src.mcp_server"]
startup_timeout_sec = 30.0
tool_timeout_sec = 120.0

[mcp_servers.pixellayer.env]
PYTHONPATH = "<path-to-pixellayer>"
PIXELLAYER_ALLOWED_WORKSPACES = "<path-to-workspaces>"
PIXELLAYER_LOG_DIR = "<path-to-pixellayer>/logs"
PIXELLAYER_MODEL_TTL = "300"
```

### 2.3. Claude Code
**Arquivo de Configuração:** `.mcp.json` (na raiz do projeto de trabalho) ou `~/.claude.json` (global)

```json
{
  "mcpServers": {
    "pixellayer": {
      "command": "<path-to-pixellayer>/.venv/bin/python",
      "args": [
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "<path-to-pixellayer>",
        "PIXELLAYER_ALLOWED_WORKSPACES": "<path-to-workspaces>",
        "PIXELLAYER_LOG_DIR": "<path-to-pixellayer>/logs",
        "PIXELLAYER_MODEL_TTL": "300"
      }
    }
  }
}
```

*Ou configure diretamente via linha de comando no Claude Code:*
```bash
claude mcp add pixellayer <path-to-pixellayer>/.venv/bin/python -m src.mcp_server -e PYTHONPATH=<path-to-pixellayer> -e PIXELLAYER_ALLOWED_WORKSPACES=<path-to-workspaces>
```

### 2.4. OpenCode
**Arquivo de Configuração:** `~/.config/opencode/opencode.json` (ou `opencode.json` na raiz do projeto)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "pixellayer": {
      "type": "local",
      "command": [
        "<path-to-pixellayer>/.venv/bin/python",
        "-m",
        "src.mcp_server"
      ],
      "environment": {
        "PYTHONPATH": "<path-to-pixellayer>",
        "PIXELLAYER_ALLOWED_WORKSPACES": "<path-to-workspaces>",
        "PIXELLAYER_LOG_DIR": "<path-to-pixellayer>/logs",
        "PIXELLAYER_MODEL_TTL": "300"
      },
      "enabled": true,
      "timeout": 120000
    }
  }
}
```

---

## 3. Variáveis de Ambiente Suportadas

O servidor aceita variáveis com prefixo `PIXELLAYER_` (ou retrocompatíveis com `IMGCUT_`):

| Variável | Padrão | Descrição |
|---|---|---|
| `PIXELLAYER_DEFAULT_MODEL` | `birefnet-general` | Modelo inicial padrão para remoção de fundo. |
| `PIXELLAYER_MODEL_TTL` | `300` | Tempo de vida em segundos antes de descarregar modelos inativos da memória. |
| `PIXELLAYER_MODELS_CACHE` | `<repo_root>/models_cache` | Diretório onde os pesos das redes neurais são armazenados. |
| `PIXELLAYER_ALLOWED_WORKSPACES` | `""` (Livre/Aviso) | Lista separada por `;` de diretórios autorizados para leitura e escrita. |
| `PIXELLAYER_LOG_DIR` | `<repo_root>/logs` | Pasta de saída para os arquivos de log. |
| `PIXELLAYER_LOG_FILE` | `<repo_root>/logs/pixellayer.log` | Caminho do arquivo de log da aplicação. |
| `PIXELLAYER_DEVICE` | `auto` | Dispositivo de inferência: `auto`, `cpu`, `cuda`, `mps`. |
| `PIXELLAYER_MAX_PIXELS` | `50000000` | Limite de segurança de pixels para mitigar ataques de descompressão (Pixel Flood). |

---

## 4. Cuidados Críticos na Execução MCP

1. **Nunca utilize `print()`**: O protocolo MCP stdio utiliza a saída padrão (`stdout`) para troca de mensagens JSON-RPC. Qualquer texto não estruturado enviado para `stdout` corrompe a comunicação com o cliente.
2. **Logs em `stderr` e em arquivo**: Toda a telemetria do servidor é canalizada para `sys.stderr` e para `logs/pixellayer.log`.
3. **Paths Relativos**: Clientes MCP devem enviar caminhos relativos ao workspace configurado, garantindo interoperabilidade entre sistemas Linux, macOS e WSL/Windows.

---

## 5. Permissões, Segurança e Sandbox do Modelo

Para proteger a integridade do sistema operacional e da máquina onde o servidor MCP executa, as seguintes salvaguardas são aplicadas por padrão:

### 5.1. Restrição de Escopo (Workspace Jail & Anti-Path Traversal)
- O modelo só tem autorização para processar caminhos dentro das pastas definidas em `PIXELLAYER_ALLOWED_WORKSPACES`.
- Qualquer tentativa de evasão de diretório (ex: `../../etc/passwd`, `../../.ssh/id_rsa`, `C:\Windows\...`) é interceptada e bloqueada com exceção estruturada `SECURITY_ERROR`.

### 5.2. Zero Vazamento de Paths do Sistema e Credenciais
- **Anti-Leak de Paths Absolutos**: Todas as respostas MCP retornam caminhos relativos ao workspace (`output/imagem.png`), nunca caminhos absolutos de diretórios de sistema do host.
- **Nenhum Acesso a Tokens ou Redes**: As ferramentas MCP expostas são estritamente de processamento de imagem (`remove_background`, `vectorize_image`, etc.). O modelo não possui ferramentas para executar comandos shell, invocar chamadas de rede arbitrárias ou inspecionar variáveis de ambiente/arquivos `.env`.

### 5.3. Prevenção de Negação de Serviço (DoS) e OOM
- **Limite de Pixels (`PIXELLAYER_MAX_PIXELS`)**: Imagens com resolução descomprimida anômala (Pixel Flooding) são rejeitadas antes da alocação na GPU/CPU.
- **Descarregamento Automático (*Zero Idle*)**: Os pesos de redes neurais carregados na GPU são descarregados automaticamente após `PIXELLAYER_MODEL_TTL` (5 minutos) sem uso.

