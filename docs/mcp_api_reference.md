# Especificação Completa do MCP & Referência da API (PixelLayer)

> Protocolo: **Model Context Protocol (MCP)**  
> Transporte: **stdio** (JSON-RPC 2.0 sobre canais padrão `stdin`/`stdout`)  
> Framework: **FastMCP (`mcp[cli]`)**  
> Formato de Dados: **Pydantic v2 (Path-Only)**

---

## 1. Arquitetura do Protocolo MCP no PixelLayer

O **PixelLayer** (`pixellayer`) atua como um servidor MCP local que conecta assistentes inteligentes e LLMs ao poder computacional de processamento de imagens local.

### 1.1. Princípio Path-Only (Zero Token Bloat)
- O protocolo MCP tradicional transporta mensagens texto e JSON.
- O **PixelLayer NUNCA** envia nem recebe imagens como Base64, strings de bytes ou arrays numéricos.
- O cliente envia uma referência de caminho relativo (ou absoluto validado) do arquivo no disco (`image_path`).
- O servidor executa a transformação e devolve uma estrutura JSON contendo o caminho do arquivo gerado (`file_path`) e seus metadados (`width`, `height`, `file_size_bytes`, `reduction_percent`).
- Isso garante economia massiva na janela de contexto de tokens do LLM e alta performance de I/O.

### 1.2. Ciclo de Vida Zero-Idle
- O servidor sobe em menos de 1 segundo sem pré-carregar nenhum modelo pesado na memória RAM ou VRAM.
- Chamadas de descoberta (`list_models`, `get_model_info`) não alocam GPU.
- O primeiro comando de inferência (`remove_background` ou `batch_process`) dispara o carregamento da rede neural selecionada em segundo plano.
- Um temporizador de TTL (padrão de 300 segundos) descarrega o modelo automaticamente caso fique ocioso.

---

## 2. Ferramentas Disponíveis na API MCP

### 2.1. `remove_background`
Remove o fundo de uma imagem usando inteligência artificial com canal alfa ARGB de 32 bits.

#### Assinatura da Função:
```python
def remove_background(
    image_path: str,
    model: str = "birefnet-general",
    output_path: str | None = None,
    output_format: str = "png",
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_path` | `string` | *(obrigatório)* | Caminho do arquivo de imagem a ser processado. |
| `model` | `string` | `"birefnet-general"` | Modelo de segmentação neural. Opções: `birefnet-general`, `birefnet-portrait`, `birefnet-matting`, `birefnet-hr`, `rmbg-2.0`, `isnet-general`. |
| `output_path` | `string` ou `null` | `null` | Caminho de saída desejado. Se nulo, salva no mesmo diretório com sufixo `_nobg`. |
| `output_format` | `string` | `"png"` | Formato de saída: `"png"` ou `"webp"`. |

#### Exemplo de Resposta (JSON):
```json
{
  "success": true,
  "image": {
    "file_path": "output/foto_nobg.png",
    "format": "png",
    "width": 1280,
    "height": 720,
    "file_size_bytes": 412500,
    "file_size_human": "402.8 KB"
  },
  "model_used": "birefnet-general",
  "processing_time_ms": 1150,
  "original_size_bytes": 980200,
  "reduction_percent": 57.92
}
```

---

### 2.2. `batch_remove_background`
Remove o fundo de múltiplas imagens em uma única invocação, mantendo o modelo aquecido e economizando turnos de mensagens e tokens.

#### Assinatura da Função:
```python
def batch_remove_background(
    image_paths: list[str],
    model: str = "birefnet-general",
    output_dir: str | None = None,
    output_format: str = "png",
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_paths` | `list[string]` | *(obrigatório)* | Lista de caminhos relativos ao workspace das imagens. |
| `model` | `string` | `"birefnet-general"` | Modelo de IA para segmentação. |
| `output_dir` | `string` ou `null` | `null` | Diretório onde salvar as imagens processadas. |
| `output_format` | `string` | `"png"` | `"png"` ou `"webp"`. |

---

### 2.3. `crop_image`
Recorta a imagem geometricamente via coordenadas ou apara automaticamente bordas vazias (*autocrop*).

#### Assinatura da Função:
```python
def crop_image(
    image_path: str,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    box: list[int] | None = None,
    autocrop: bool = False,
    output_path: str | None = None,
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_path` | `string` | *(obrigatório)* | Caminho da imagem de entrada. |
| `x`, `y` | `integer` ou `null` | `null` | Coordenadas do canto superior esquerdo do recorte. |
| `width`, `height` | `integer` ou `null` | `null` | Largura e altura da região de corte. |
| `box` | `list[int]` ou `null` | `null` | Coordenadas explícitas `[left, top, right, bottom]`. |
| `autocrop` | `boolean` | `false` | Se `true`, detecta limites de conteúdo e apara margens transparentes/sólidas. |
| `output_path` | `string` ou `null` | `null` | Caminho do arquivo de saída. |

---

### 2.4. `convert_format`
Converte arquivos entre PNG, WebP e JPEG preservando canais alfa quando suportado.

#### Assinatura da Função:
```python
def convert_format(
    image_path: str,
    target_format: str,
    quality: int = 90,
    lossless: bool = False,
    output_path: str | None = None,
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_path` | `string` | *(obrigatório)* | Caminho do arquivo de imagem. |
| `target_format` | `string` | *(obrigatório)* | `"png"`, `"webp"` ou `"jpeg"`. |
| `quality` | `integer` | `90` | Qualidade da compressão com perdas (1 a 100). |
| `lossless` | `boolean` | `false` | Se verdadeiro, utiliza compressão sem perdas (WebP apenas). |
| `output_path` | `string` ou `null` | `null` | Caminho do arquivo de saída. |

---

### 2.3. `optimize_image`
Otimiza imagens reduzindo o peso do arquivo através de compressão e limpeza de metadados EXIF.

#### Assinatura da Função:
```python
def optimize_image(
    image_path: str,
    level: str = "medium",
    target_size_kb: int | None = None,
    strip_metadata: bool = True,
    output_path: str | None = None,
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_path` | `string` | *(obrigatório)* | Caminho da imagem. |
| `level` | `string` | `"medium"` | Preset: `"lossless"`, `"light"`, `"medium"`, `"aggressive"`. |
| `target_size_kb` | `integer` ou `null` | `null` | Meta de tamanho em KB (ajusta qualidade iterativamente). |
| `strip_metadata` | `boolean` | `true` | Remove metadados EXIF e dados auxiliares da imagem. |
| `output_path` | `string` ou `null` | `null` | Caminho de destino. |

---

### 2.4. `resize_image`
Redimensiona imagens com múltiplos algoritmos de interpolação e preservação de proporção.

#### Assinatura da Função:
```python
def resize_image(
    image_path: str,
    width: int | None = None,
    height: int | None = None,
    scale_percent: float | None = None,
    mode: str = "fit",
    resample: str = "lanczos",
    output_path: str | None = None,
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_path` | `string` | *(obrigatório)* | Caminho da imagem. |
| `width` | `integer` ou `null` | `null` | Largura alvo em pixels. |
| `height` | `integer` ou `null` | `null` | Altura alvo em pixels. |
| `scale_percent` | `float` ou `null` | `null` | Percentual de escala (ex: `50` para metade do tamanho). |
| `mode` | `string` | `"fit"` | `"fit"` (enquadra preservando proporção), `"fill"` (preenche e recorta), `"exact"`, `"percentage"`. |
| `resample` | `string` | `"lanczos"` | Algoritmo: `"lanczos"`, `"bicubic"`, `"bilinear"`, `"nearest"`. |
| `output_path` | `string` ou `null` | `null` | Caminho de saída. |

---

### 2.5. `vectorize_image`
Converte imagens rasterizadas para vetores SVG limpos através do motor `vtracer` com pré-filtragem de ruído de anti-aliasing.

#### Assinatura da Função:
```python
def vectorize_image(
    image_path: str,
    detail_level: str = "logo",
    color_mode: str = "color",
    output_path: str | None = None,
) -> dict[str, Any]
```

#### Parâmetros:
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `image_path` | `string` | *(obrigatório)* | Imagem de entrada. |
| `detail_level` | `string` | `"logo"` | Nível de detalhe: `"logo"` (recomendado/padrão para logos/ícones, curvas suaves e sem ruído de transparência), `"medium"`, `"high"`, `"low"`. |
| `color_mode` | `string` | `"color"` | `"color"` (preserva cores originais) ou `"binary"` (preto e branco). |
| `output_path` | `string` ou `null` | `null` | Caminho do arquivo SVG resultante. |

---

### 2.6. `batch_process`
Encadeia operações sequenciais em pipeline atômico com limpeza automática de artefatos temporários.

#### Assinatura da Função:
```python
def batch_process(
    image_path: str,
    steps: list[dict[str, Any]],
    output_path: str | None = None,
) -> dict[str, Any]
```

#### Exemplo de Chamada:
```json
{
  "image_path": "images/banner.jpg",
  "steps": [
    {
      "operation": "remove_background",
      "params": { "model": "birefnet-general" }
    },
    {
      "operation": "resize_image",
      "params": { "width": 800, "mode": "fit" }
    },
    {
      "operation": "convert_format",
      "params": { "target_format": "webp", "quality": 85 }
    }
  ]
}
```

---

### 2.7. `list_models` & `get_model_info`
Inspeção leve do catálogo de redes neurais.

#### Exemplos:
- `list_models()`: Retorna lista com ID, nome, descrição, status de carregamento e TTL de todos os modelos.
- `get_model_info(model_id="rmbg-2.0")`: Retorna detalhes do modelo especificado.

---

## 3. Formato Padrão de Resposta e Erros

### Resposta de Sucesso:
```json
{
  "success": true,
  "image": {
    "file_path": "caminho/resultado.png",
    "format": "png",
    "width": 1024,
    "height": 1024,
    "file_size_bytes": 204800,
    "file_size_human": "200.0 KB"
  }
}
```

### Resposta de Erro Estruturado:
```json
{
  "success": false,
  "error": "SECURITY_ERROR",
  "message": "Path '...' is outside of allowed workspaces. Path traversal prevented."
}
```

Códigos de erro possíveis:
- `FILE_NOT_FOUND`
- `UNSUPPORTED_FORMAT`
- `SECURITY_ERROR`
- `MODEL_NOT_FOUND`
- `MODEL_LOAD_ERROR`
- `PROCESSING_ERROR`
- `UNEXPECTED_ERROR`
