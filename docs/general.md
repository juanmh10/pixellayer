# Documentação Geral do Projeto img-cut

## 1. O que é o img-cut?

O **img-cut** é um servidor local baseado no **Model Context Protocol (MCP)**, desenvolvido em Python, que disponibiliza ferramentas avançadas de processamento e manipulação de imagens potencializadas por inteligência artificial para assistentes de programação e agentes de IA (como Claude, Antigravity, VS Code Copilot, Cursor).

O principal diferencial do projeto é o processamento estritamente local com carregamento sob demanda (*lazy-loading*), além da política **Path-Only**: nenhum byte em base64 trafega pelas mensagens do protocolo MCP, evitando estouro de janelas de contexto e garantindo alta performance.

---

## 2. Principais Funcionalidades

### 2.1. Remoção Inteligente de Fundo (`remove_background`)
- Segmentação de fundo via redes neurais com canal alfa ARGB de 32 bits limpo, sem preenchimento artificial.
- Suporte a múltiplos modelos selecionáveis:
  - `birefnet-general`: Modelo padrão de alto nível para uso geral.
  - `birefnet-portrait`: Otimizado para pessoas e retratos.
  - `birefnet-matting`: Focado em bordas complexas, transparências e pelos/cabelos finos.
  - `birefnet-hr`: Para imagens de alta resolução.
  - `rmbg-2.0`: Modelo BRIA para uso comercial.
  - `isnet-general`: Modelo leve para processamento ágil.

### 2.2. Conversão de Formatos (`convert_format`)
- Conversão bidirecional entre PNG, WebP e JPEG.
- Controle fino de qualidade (1-100) e compressão sem perdas (*lossless* para WebP).
- Preservação nativa do canal de transparência em formatos compatíveis.

### 2.3. Otimização de Imagens (`optimize_image`)
- Redução de tamanho de arquivo com base em presets (`lossless`, `light`, `medium`, `aggressive`) ou por meta explícita de peso em kilobytes (`target_size_kb`).
- Limpeza opcional de metadados EXIF para privacidade e economia de bytes.

### 2.4. Redimensionamento Inteligente (`resize_image`)
- Redimensionamento com preservação de proporção nos modos `fit` (enquadrar), `fill` (preencher com corte), `exact` ou por percentual de escala.
- Algoritmos de reamostragem de alta precisão (Lanczos, Bicubic, Bilinear, Nearest).

### 2.5. Vetorização Raster-para-SVG (`vectorize_image`)
- Conversão de matriz de pixels em curvas vetoriais SVG através do motor `vtracer`.
- Controle de nível de detalhes (`low`, `medium`, `high`) e suporte a modo colorido ou binário (preto e branco).

### 2.6. Processamento em Lote / Pipeline (`batch_process`)
- Encadeamento de múltiplas etapas de transformação sequencial de imagem em uma única chamada de ferramenta (ex: recortar fundo -> redimensionar -> converter para WebP -> otimizar), com limpeza automática de arquivos intermediários.

### 2.7. Inspeção e Gestão de Modelos (`list_models`, `get_model_info`)
- Listagem dos modelos disponíveis, tempo de TTL e status de memória sem disparar download ou alocação em GPU/VRAM.

---

## 3. Arquitetura do Sistema

```
                        +----------------------------+
                        |  AI Coding Agent (Claude,  |
                        |     Antigravity, etc.)     |
                        +--------------+-------------+
                                       |
                              MCP stdio Transport
                                       |
                        +--------------v-------------+
                        |      src.mcp_server        |
                        | (FastMCP Tool Registration)|
                        +--------------+-------------+
                                       |
                 +---------------------+---------------------+
                 |                                           |
    +------------v-------------+                +------------v------------+
    |   src.contracts (Schemas)|                | src.utils (Safe Path,   |
    |      Pydantic v2 I/O     |                |  Config, Logging)       |
    +--------------------------+                +------------+------------+
                                                             |
                        +----------------------------+       |
                        |        src.engine          <-------+
                        | (Processors & Model Regist)|
                        +--------------+-------------+
                                       |
               +-----------------------+-----------------------+
               |                                               |
  +------------v-------------+                    +------------v------------+
  |    ML Model Wrappers     |                    |    Image Processors     |
  | (BiRefNet, RMBG, IS-Net) |                    | (PIL, vtracer, etc.)    |
  |  Lazy-load + TTL Unload  |                    +-------------------------+
  +--------------------------+
```

---

## 4. Política de Caminhos e Segurança (No Absolute Paths)

- O projeto veta caminhos absolutos atrelados à máquina do desenvolvedor (ex: `/home/...` ou `C:\Users\...`).
- Toda entrada é resolvida através de `resolve_safe_path()` contra o diretório de execução atual ou caminhos especificados na variável de ambiente `IMGCUT_ALLOWED_WORKSPACES`.
- Qualquer tentativa de evasão (*path traversal*) para fora dos limites seguros dispara uma exceção `SecurityError`.

---

## 5. Estrutura de Pastas Operacionais

- `docs/`: Documentações técnicas, guias de ferramentas e de exposição do servidor.
- `logs/`: Arquivos de log de execução da aplicação (ex: `logs/img-cut.log`).
- `trash/`: Destino de arquivos temporários descartados, relatórios antigos e saídas obsoletas.
- `models_cache/`: Diretório de pesos locais baixados das redes neurais (ignorado pelo versionamento Git).
