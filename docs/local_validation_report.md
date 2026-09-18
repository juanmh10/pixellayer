# Relatório de Validação Local e Homologação MCP (PixelLayer)

> **Status:** Aprovado  
> **Data:** 17 de Setembro de 2026  
> **Servidor MCP:** `pixellayer`  
> **Protocolo:** Model Context Protocol (MCP) via stdio  
> **Framework:** FastMCP (`mcp[cli]`)

---

## 1. Objetivo e Escopo

Este documento consolida os testes de ponta a ponta e a validação do servidor local **PixelLayer** (`pixellayer`) utilizando chamadas reais disparadas diretamente pelo harness de agentes de IA sobre as imagens de teste da pasta `input/`.

O ciclo validou:
1. Comunicação estrita baseada em caminhos de arquivos (*Path-Only*).
2. Carregamento sob demanda (*lazy-loading*) com descarregamento automático por inatividade (*Zero-Idle*).
3. Qualidade da remoção de fundo com canal alfa ARGB de 32 bits puro (transparência real).
4. Vetorização matricial para SVG via `vtracer` com preset padrão `logo`.
5. Compatibilidade e padronização de configurações nos 4 principais clientes de agentes locais: **Antigravity CLI (AGY)**, **Codex CLI**, **Claude Code** e **OpenCode**.

---

## 2. Resultados das Chamadas MCP em Produção Local

### 2.1. Teste de Remoção de Fundo (`remove_background`)

- **Comando MCP Invocado:**
  ```json
  {
    "name": "remove_background",
    "arguments": {
      "image_path": "input/to-cut.png",
      "model": "birefnet-general",
      "output_format": "png"
    }
  }
  ```
- **Resposta MCP Obtida:**
  ```json
  {
    "success": true,
    "image": {
      "file_path": "input/to-cut_nobg.png",
      "format": "png",
      "width": 1448,
      "height": 1086,
      "file_size_bytes": 2442819,
      "file_size_human": "2.3 MB"
    },
    "model_used": "birefnet-general",
    "processing_time_ms": 9583,
    "original_size_bytes": 2213741,
    "reduction_percent": -10.35
  }
  ```
- **Auditoria do Arquivo Gerado (`input/to-cut_nobg.png`):**
  - **Modo de Cor:** `RGBA` (32-bit com canal alfa completo).
  - **Dimensões:** `1448 x 1086` px (resolução nativa 100% preservada, sem downscale).
  - **Extremos do Canal Alfa (min, max):** `(0, 255)` — confirma a presença de pixels perfeitamente transparentes (0) e totalmente opacos (255) sem máscaras residuais ou preenchimento de fundo.

---

### 2.2. Teste de Vetorização para SVG (`vectorize_image`)

- **Comando MCP Invocado:**
  ```json
  {
    "name": "vectorize_image",
    "arguments": {
      "image_path": "input/carro-to-svg.png",
      "detail_level": "logo",
      "color_mode": "color"
    }
  }
  ```
- **Resposta MCP Obtida:**
  ```json
  {
    "success": true,
    "svg_path": "input/carro-to-svg_vector.svg",
    "svg_size_bytes": 2021486,
    "svg_size_human": "1.9 MB",
    "original_size_bytes": 1800486,
    "path_count": 1770,
    "processing_time_ms": 2878
  }
  ```
- **Auditoria do Arquivo Gerado (`input/carro-to-svg_vector.svg`):**
  - **Validade do Documento:** SVG XML válido, gerado por motor `vtracer`.
  - **Curvas e Caminhos:** 1.770 paths vetoriais com controle de ruído do preset `logo`.
  - **Tamanho:** 1.9 MB com curvas suaves e sem perdas de definição em qualquer nível de zoom.

---

## 3. Homologação das Configurações de Clientes de IA

O sistema de resolução de variáveis de ambiente foi unificado em `src/utils/config.py` através da função `_get_env()`. Todas as variáveis de ambiente agora aceitam prioritariamente o prefixo `PIXELLAYER_*`, mantendo retrocompatibilidade total com `IMGCUT_*`.

| Cliente | Arquivo de Configuração | Formato | Status |
|---|---|---|---|
| **Antigravity CLI (AGY)** | `~/.gemini/config/mcp_config.json` | JSON (`mcpServers.pixellayer`) | **Homologado & Ativo** |
| **Codex CLI** | `~/.codex/config.toml` | TOML (`[mcp_servers.pixellayer]`) | **Homologado & Ativo** |
| **Claude Code** | `~/.claude.json` / `.mcp.json` | JSON (`mcpServers.pixellayer`) | **Homologado & Ativo** |
| **OpenCode** | `~/.config/opencode/opencode.json` | JSON (`mcp.pixellayer`) | **Homologado & Ativo** |

---

## 4. Garantias de Qualidade e Segurança (Quality Gates)

1. **Testes Automatizados:**
   - Suíte de testes `pytest` executada: **93 testes passaram** (100% de sucesso).
   - Cobertura: Contratos Pydantic v2, segurança contra Path Traversal, processadores de imagem, modelos neurais e integração FastMCP.
2. **Auditoria de Segurança e Segredos:**
   - Verificação com `scripts/audit.py` e `gitleaks`: zero credenciais expostas.
   - Verificação estrita de *Zero Hardcoded Absolute Paths*: nenhum caminho de sistema (`/home/...` ou `C:\...`) versionado no repositório Git.
3. **Comunicação Segura stdio:**
   - `stdout` estritamente reservado para JSON-RPC do protocolo MCP.
   - Logs de telemetria direcionados para `stderr` e para `logs/pixellayer.log`.
