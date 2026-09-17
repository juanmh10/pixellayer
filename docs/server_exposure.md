# Exposição do Servidor Local MCP

O **img-cut** é projetado para rodar como um servidor local baseado em `stdio`, comunicando-se diretamente com o cliente/agente MCP.

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

### Configuração com Caminhos Relativos e Portáteis (`mcp-config.json`)

Para integrar o servidor em clientes como Claude Desktop, Antigravity, Cursor ou extensões MCP do VS Code, utilize as configurações abaixo adaptando apenas a variável de ambiente do workspace conforme a pasta do seu projeto atual.

#### Exemplo Padrão Portátil:
```json
{
  "mcpServers": {
    "img-cut": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        ".",
        "python",
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "IMGCUT_ALLOWED_WORKSPACES": "."
      }
    }
  }
}
```

#### Exemplo para Claude Desktop ou Antigravity CLI:
```json
{
  "mcpServers": {
    "img-cut": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "${workspaceFolder}",
        "python",
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "IMGCUT_ALLOWED_WORKSPACES": "${workspaceFolder}",
        "IMGCUT_LOG_DIR": "${workspaceFolder}/logs",
        "IMGCUT_MODEL_TTL": "300"
      }
    }
  }
}
```

#### Exemplo para Codex CLI (`~/.codex/config.toml`):
```toml
[mcp_servers.img-cut]
command = "<path-to-repo>/.venv/bin/python"
args = ["-m", "src.mcp_server"]
startup_timeout_sec = 30.0
tool_timeout_sec = 120.0

[mcp_servers.img-cut.env]
PYTHONPATH = "<path-to-repo>"
IMGCUT_ALLOWED_WORKSPACES = "<path-to-workspaces>"
IMGCUT_LOG_DIR = "<path-to-repo>/logs"
IMGCUT_MODEL_TTL = "300"
```

---

## 3. Variáveis de Ambiente Suportadas

| Variável | Padrão | Descrição |
|---|---|---|
| `IMGCUT_DEFAULT_MODEL` | `birefnet-general` | Modelo inicial padrão para remoção de fundo. |
| `IMGCUT_MODEL_TTL` | `300` | Tempo de vida em segundos antes de descarregar modelos inativos da memória. |
| `IMGCUT_MODELS_CACHE` | `<repo_root>/models_cache` | Diretório onde os pesos das redes neurais são armazenados. |
| `IMGCUT_ALLOWED_WORKSPACES` | `""` (Livre/Aviso) | Lista separada por `;` de diretórios autorizados para leitura e escrita. |
| `IMGCUT_LOG_DIR` | `<repo_root>/logs` | Pasta de saída para os arquivos de log. |
| `IMGCUT_LOG_FILE` | `<repo_root>/logs/img-cut.log` | Caminho do arquivo de log da aplicação. |
| `IMGCUT_DEVICE` | `auto` | Dispositivo de inferência: `auto`, `cpu`, `cuda`, `mps`. |
| `IMGCUT_MAX_PIXELS` | `50000000` | Limite de segurança de pixels para mitigar ataques de descompressão (Pixel Flood). |

---

## 4. Cuidados Críticos na Execução MCP

1. **Nunca utilize `print()`**: O protocolo MCP stdio utiliza a saída padrão (`stdout`) para troca de mensagens JSON-RPC. Qualquer texto não estruturado enviado para `stdout` corrompe a comunicação com o cliente.
2. **Logs em `stderr` e em arquivo**: Toda a telemetria do servidor é canalizada para `sys.stderr` e para `logs/img-cut.log`.
3. **Paths Relativos**: Clientes MCP devem enviar caminhos relativos ao workspace configurado, garantindo interoperabilidade entre sistemas Linux, macOS e WSL/Windows.

---

## 5. Permissões, Segurança e Sandbox do Modelo

Para proteger a integridade do sistema operacional e da máquina onde o servidor MCP executa, as seguintes salvaguardas são aplicadas por padrão:

### 5.1. Restrição de Escopo (Workspace Jail & Anti-Path Traversal)
- O modelo só tem autorização para processar caminhos dentro das pastas definidas em `IMGCUT_ALLOWED_WORKSPACES`.
- Qualquer tentativa de evasão de diretório (ex: `../../etc/passwd`, `../../.ssh/id_rsa`, `C:\Windows\...`) é interceptada e bloqueada com exceção estruturada `SECURITY_ERROR`.

### 5.2. Zero Vazamento de Paths do Sistema e Credenciais
- **Anti-Leak de Paths Absolutos**: Todas as respostas MCP retornam caminhos relativos ao workspace (`output/imagem.png`), nunca caminhos absolutos de diretórios de sistema do host.
- **Nenhum Acesso a Tokens ou Redes**: As ferramentas MCP expostas são estritamente de processamento de imagem (`remove_background`, `vectorize_image`, etc.). O modelo não possui ferramentas para executar comandos shell, invocar chamadas de rede arbitrárias ou inspecionar variáveis de ambiente/arquivos `.env`.

### 5.3. Prevenção de Negação de Serviço (DoS) e OOM
- **Limite de Pixels (`IMGCUT_MAX_PIXELS`)**: Imagens com resolução descomprimida anômala (Pixel Flooding) são rejeitadas antes da alocação na GPU/CPU.
- **Descarregamento Automático (*Zero Idle*)**: Os pesos de redes neurais carregados na GPU são descarregados automaticamente após `IMGCUT_MODEL_TTL` (5 minutos) sem uso.

